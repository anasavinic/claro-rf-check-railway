import io
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from ep_import.services.errors import EpImportError
from ep_import.services.importer import import_ep_file
from ep_import.services.persist import process_job
from ep_import.tasks import purge_expired_imports, reconcile_stuck_imports

FIXTURES = Path(__file__).parent / "fixtures"

SHEETS = {
    "RNP GSM (2G)": [
        "STATE",
        "SINGLE RAN NAME",
        "*BTS NAME",
        "*GSM CELL NAME",
        "*LAC",
        "*CI",
        "*FREQUENCY OF BCCH",
        "BSC",
    ],
    "RNP UMTS (3G)": [
        "REGION",
        "STATE",
        "SINGLE RAN NAME",
        "NODEB NAME",
        "CELLNAME",
        "CELL ID",
        "LAC",
        "SAC",
        "RNC ID",
        "RNC NAME",
        "PSCRAMBCODE",
        "UARFCN DOWNLINK",
    ],
    "RNP LTE (4G)": [
        "REGION",
        "STATE",
        "SINGLE RAN NAME",
        "ENODEBNAME",
        "CELL NAME",
        "CELL ID",
        "ENODEB ID",
        "TAC",
        "EARFCN_DL",
        "PCI",
    ],
    "RNP NR (5G)": [
        "REGION",
        "STATE",
        "SINGLE RAN NAME",
        "ENODEB NAME",
        "CELL NAME",
        "gNBId",
        "CellId",
        "FrequencyBand",
        "PhysicalCellId",
        "DlNarfcn",
        "Tracking Area ID",
    ],
}


def _save_workbook(path: Path, mutate=None) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    for name, headers in SHEETS.items():
        ws = wb.create_sheet(name)
        ws.append(headers)
        ws.append(["x"] * len(headers))
    if mutate:
        mutate(wb)
    wb.save(path)


def _job_from(path: Path, tmp_path) -> ImportJob:
    job = ImportJob(original_filename=path.name, status=ImportJobStatus.PENDING)
    job.stored_file.save(path.name, SimpleUploadedFile(path.name, path.read_bytes()))
    job.save()
    return job


@pytest.mark.django_db
def test_rejects_xls_extension(auth_client):
    response = auth_client.post(
        reverse("ep_import:upload"),
        {"file": SimpleUploadedFile("RNP_SRAN_CO.xls", b"PK\x03\x04", content_type="application/vnd.ms-excel")},
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 400
    assert ".xlsx" in response.json()["message"]
    assert ImportJob.objects.count() == 0


def test_rejects_legacy_xls_renamed(tmp_path):
    path = tmp_path / "RNP_SRAN_CO_legacy.xlsx"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32)
    with pytest.raises(EpImportError) as exc:
        import_ep_file(path)
    assert exc.value.issues[0].code == "UNSUPPORTED_XLS"
    assert "Detail" not in exc.value.issues[0].message


def test_rejects_corrupt_package_without_exception_text(tmp_path):
    path = tmp_path / "RNP_SRAN_CO_bad.xlsx"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", "not-xml")
        package.writestr("xl/workbook.xml", "not-a-workbook")
    path.write_bytes(buffer.getvalue())

    with pytest.raises(EpImportError) as exc:
        import_ep_file(path)
    assert exc.value.issues[0].code == "INVALID_WORKBOOK"
    assert "Traceback" not in exc.value.issues[0].message
    assert "Detail" not in exc.value.issues[0].message


def test_rejects_compression_bomb(tmp_path, monkeypatch):
    monkeypatch.setattr("ep_import.services.content.MAX_COMPRESSION_RATIO", 2)
    path = tmp_path / "RNP_SRAN_CO_bomb.xlsx"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", "<Types></Types>")
        package.writestr("xl/workbook.xml", "A" * (2 * 1024 * 1024))
    path.write_bytes(buffer.getvalue())

    with pytest.raises(EpImportError) as exc:
        import_ep_file(path)
    assert exc.value.issues[0].code == "COMPRESSION_RATIO"


@pytest.mark.django_db
def test_missing_site_key_rejects_entire_file(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    path = tmp_path / "RNP_SRAN_CO_missing_site.xlsx"

    def mutate(wb):
        ws = wb["RNP NR (5G)"]
        ws["E2"] = ""  # CELL NAME stays; clear site columns
        ws["C2"] = ""
        ws["D2"] = ""

    _save_workbook(path, mutate)
    job = _job_from(path, tmp_path)
    process_job(job)
    job.refresh_from_db()

    assert job.status == ImportJobStatus.FAILED
    assert any(issue["code"] == "ROW_MISSING_KEY" for issue in job.issues)
    assert job.issues[0]["row"] == 2
    assert EpCell.objects.filter(job=job).count() == 0


@pytest.mark.django_db
def test_duplicate_cell_warns_and_keeps_first(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    path = tmp_path / "RNP_SRAN_CO_dup.xlsx"

    def mutate(wb):
        ws = wb["RNP NR (5G)"]
        ws.append([cell.value for cell in ws[2]])

    _save_workbook(path, mutate)
    job = _job_from(path, tmp_path)
    process_job(job)
    job.refresh_from_db()

    assert job.status == ImportJobStatus.SUCCESS
    dup_issues = [issue for issue in job.issues if issue["code"] == "DUPLICATE_CELL"]
    assert len(dup_issues) == 1
    assert dup_issues[0]["severity"] == "warning"
    assert "ignored" in dup_issues[0]["message"]
    assert job.counts.get("5G") == 1
    assert EpCell.objects.filter(job=job, technology="5G").count() == 1
    assert EpCell.objects.filter(job=job).count() == 4


@pytest.mark.django_db
def test_unexpected_error_is_not_shown(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    source = FIXTURES / "ep_claro_minimal.xlsx"
    job = _job_from(source, tmp_path)

    def explode(*_args, **_kwargs):
        raise RuntimeError("secret-db-password")

    monkeypatch.setattr("ep_import.services.persist.validate_workbook", explode)
    process_job(job)
    job.refresh_from_db()

    assert job.status == ImportJobStatus.FAILED
    assert job.issues[0]["code"] == "UNEXPECTED_ERROR"
    assert "secret-db-password" not in job.issues[0]["message"]


@pytest.mark.django_db
def test_process_job_does_not_require_local_path(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    source = FIXTURES / "ep_claro_minimal.xlsx"
    job = _job_from(source, tmp_path)

    def deny_path(self):
        raise NotImplementedError("remote storage has no path")

    monkeypatch.setattr("django.db.models.fields.files.FieldFile.path", property(deny_path))
    process_job(job)
    job.refresh_from_db()
    assert job.status == ImportJobStatus.SUCCESS


@pytest.mark.django_db
def test_upload_is_idempotent_for_same_bytes(auth_client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    settings.CELERY_TASK_ALWAYS_EAGER = True
    payload = (FIXTURES / "ep_claro_minimal.xlsx").read_bytes()

    def post():
        return auth_client.post(
            reverse("ep_import:upload"),
            {
                "file": SimpleUploadedFile(
                    "RNP_SRAN_CO_minimal.xlsx",
                    payload,
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "technology": "5G",
            },
            HTTP_ACCEPT="application/json",
        )

    first = post()
    second = post()
    assert first.status_code in (200, 202)
    assert second.status_code in (200, 202)
    assert first.json()["job"]["id"] == second.json()["job"]["id"]
    assert ImportJob.objects.count() == 1


@pytest.mark.django_db
def test_purge_expired_removes_file_job_and_cells(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    source = FIXTURES / "ep_claro_minimal.xlsx"
    job = _job_from(source, tmp_path)
    process_job(job)
    job.refresh_from_db()
    assert EpCell.objects.filter(job=job).exists()
    stored = job.stored_file.path

    job.expires_at = timezone.now() - timedelta(days=1)
    job.save(update_fields=["expires_at"])
    assert purge_expired_imports() == 1
    assert ImportJob.objects.filter(pk=job.pk).count() == 0
    assert EpCell.objects.filter(job_id=job.pk).count() == 0
    assert not Path(stored).exists()


@pytest.mark.django_db
def test_reconcile_marks_stuck_processing_failed():
    job = ImportJob.objects.create(
        original_filename="RNP_SRAN_CO.xlsx",
        status=ImportJobStatus.PROCESSING,
        stage="validating",
    )
    ImportJob.objects.filter(pk=job.pk).update(
        created_at=timezone.now() - timedelta(hours=2),
        started_at=timezone.now() - timedelta(hours=2),
    )

    assert reconcile_stuck_imports() == 1
    job.refresh_from_db()
    assert job.status == ImportJobStatus.FAILED
    assert job.issues[0]["code"] == "IMPORT_STUCK"
    assert "Traceback" not in job.issues[0]["message"]


@pytest.mark.django_db
def test_expires_at_is_not_renewed_by_analysis(auth_client):
    from precheck.models import CheckAnalysis, CheckAnalysisStatus
    from precheck.services.analysis import create_check_analysis

    job = ImportJob.objects.create(
        created_by=auth_client.user,
        original_filename="RNP_SRAN_CO.xlsx",
        status=ImportJobStatus.SUCCESS,
        stored_file="ep_imports/test.xlsx",
    )
    original = job.expires_at
    assert original is not None

    create_check_analysis(
        user=auth_client.user,
        job=job,
        site="SITE",
        cells=["CELL"],
        pre_check=True,
        full_check=False,
    )
    job.refresh_from_db()
    assert job.expires_at == original
    assert CheckAnalysis.objects.filter(ep_job=job).count() == 1
    assert CheckAnalysis.objects.get(ep_job=job).status == CheckAnalysisStatus.AWAITING_RETURNS


@pytest.mark.django_db
def test_purge_expired_removes_linked_analyses(tmp_path, settings):
    from precheck.models import CheckAnalysis, CheckAnalysisStatus

    settings.MEDIA_ROOT = tmp_path
    source = FIXTURES / "ep_claro_minimal.xlsx"
    job = _job_from(source, tmp_path)
    process_job(job)
    job.refresh_from_db()
    CheckAnalysis.objects.create(
        ep_job=job,
        site_name="SITE",
        selected_cells=["CELL"],
        pre_check=True,
        status=CheckAnalysisStatus.COMPLETED,
    )

    job.expires_at = timezone.now() - timedelta(days=1)
    job.save(update_fields=["expires_at"])
    assert purge_expired_imports() == 1
    assert ImportJob.objects.filter(pk=job.pk).count() == 0
    assert CheckAnalysis.objects.filter(ep_job_id=job.pk).count() == 0
