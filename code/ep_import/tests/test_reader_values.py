from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from ep_import.services.persist import process_job
from ep_import.services.reader import _json_safe_value, read_canonical_sheets

FIXTURES = Path(__file__).parent / "fixtures"

SHEET_HEADERS = {
    "RNP GSM (2G)": [
        "REGION",
        "STATE",
        "SINGLE RAN NAME",
        "*BTS NAME",
        "*GSM CELL NAME",
        "*LAC",
        "*CI",
        "*FREQUENCY OF BCCH",
        "BSC",
        "LAST UPDATE",
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
        "LAST UPDATE",
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
        "LAST UPDATE",
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
        "LAST UPDATE",
    ],
}


def test_json_safe_value_datetime_types():
    assert _json_safe_value(datetime(2026, 8, 13, 10, 30)) == "2026-08-13T10:30:00"
    assert _json_safe_value(date(2026, 8, 13)) == "2026-08-13"
    assert _json_safe_value(time(14, 30, 0)) == "14:30:00"
    assert _json_safe_value(timedelta(hours=1, minutes=30)) == 5400.0


def test_json_safe_value_decimal_and_primitives():
    assert _json_safe_value(Decimal("123.0")) == 123
    assert _json_safe_value(Decimal("12.5")) == 12.5
    assert _json_safe_value("  abc  ") == "abc"
    assert _json_safe_value(None) is None
    assert _json_safe_value(True) is True
    assert _json_safe_value(7) == 7
    assert _json_safe_value(1.5) == 1.5


def _build_workbook_with_last_update(path: Path) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    stamp = datetime(2026, 8, 13, 14, 30, 0)
    rows = {
        "RNP GSM (2G)": ["CO", "AC", "S1", "B1", "C1", 1, 1, 1, "BSC", stamp],
        "RNP UMTS (3G)": [
            "CO",
            "AC",
            "S1",
            "N1",
            "C1",
            1,
            1,
            1,
            1,
            "RNC",
            1,
            1,
            stamp,
        ],
        "RNP LTE (4G)": ["CO", "AC", "S1", "E1", "C1", 1, 1, 1, 1, 1, stamp],
        "RNP NR (5G)": [
            "CO",
            "AC",
            "S1",
            "E1",
            "C1",
            1,
            1,
            "N1",
            1,
            1,
            1,
            stamp,
        ],
    }
    for name, headers in SHEET_HEADERS.items():
        ws = wb.create_sheet(name)
        ws.append(headers)
        ws.append(rows[name])
    wb.save(path)


def test_read_canonical_sheets_coerces_datetime(tmp_path):
    path = tmp_path / "RNP_SRAN_CO_with_dates.xlsx"
    _build_workbook_with_last_update(path)

    data = read_canonical_sheets(path)
    last_update = data["RNP NR (5G)"][0]["LAST UPDATE"]
    assert last_update == "2026-08-13T14:30:00"
    assert isinstance(last_update, str)


@pytest.mark.django_db
def test_process_job_succeeds_with_datetime_column(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    xlsx = tmp_path / "RNP_SRAN_CO_with_dates.xlsx"
    _build_workbook_with_last_update(xlsx)

    job = ImportJob(
        original_filename="RNP_SRAN_CO_with_dates.xlsx",
        status=ImportJobStatus.PENDING,
    )
    with xlsx.open("rb") as fh:
        job.stored_file.save(
            "RNP_SRAN_CO_with_dates.xlsx",
            SimpleUploadedFile(xlsx.name, fh.read()),
        )
    job.save()

    process_job(job)
    job.refresh_from_db()

    assert job.status == ImportJobStatus.SUCCESS
    cell = EpCell.objects.filter(job=job, technology="5G").first()
    assert cell is not None
    assert cell.raw["LAST UPDATE"] == "2026-08-13T14:30:00"


def test_minimal_fixture_still_imports():
    from ep_import.services.importer import import_ep_file

    payload = import_ep_file(FIXTURES / "ep_claro_minimal.xlsx")
    assert payload.counts["5G"] == 2
