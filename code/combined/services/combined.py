"""Create and resolve Combined RF checks (multi-technology analyses)."""

from __future__ import annotations

from collections import Counter

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import Count, Q

from ep_import.models import EpCell, ImportJob
from ep_import.services.scripts import (
    FULL_CHECK_ONLY_TECHNOLOGIES,
    ep_cell_id_from_raw,
    generate_full_check_script,
    generate_precheck_script,
)
from precheck.models import CheckAnalysis, CheckAnalysisStatus, CombinedCheck

SESSION_COMBINED_KEY = "combined_check_id"

TECH_OPTIONS = [
    {"id": "2G", "label": "2G", "description": "GSM parameter analysis"},
    {"id": "3G", "label": "3G", "description": "UMTS parameter analysis"},
    {"id": "4G", "label": "4G LTE", "description": "LTE parameter analysis"},
    {"id": "5G", "label": "5G NR", "description": "5G NR parameter analysis"},
]

TECH_LABELS = {item["id"]: item["label"] for item in TECH_OPTIONS}
_SITE_PREFIXES = frozenset("ENUG")


def site_family_keys(names: list[str]) -> dict[str, str]:
    """Group the same station across technologies (ESITE, NSITE, and SITE)."""
    upper = {name: name.strip().upper() for name in names if str(name).strip()}
    raw_core: dict[str, str] = {}
    for name, value in upper.items():
        if len(value) > 4 and value[0] in _SITE_PREFIXES:
            raw_core[name] = value[1:]
        else:
            raw_core[name] = value
    counts = Counter(raw_core.values())
    full_names = set(upper.values())
    keys: dict[str, str] = {}
    for name, core in raw_core.items():
        if counts[core] >= 2 or core in full_names:
            keys[name] = core
        else:
            keys[name] = upper[name]
    return keys


def tech_label(technology: str) -> str:
    return TECH_LABELS.get(technology, technology)


def create_combined_check(
    *,
    user: AbstractBaseUser | None,
    technologies: list[str],
) -> CombinedCheck:
    techs = _normalize_technologies(technologies)
    if len(techs) < 2:
        raise ValueError("Select at least two technologies.")

    has_5g = "5G" in techs
    return CombinedCheck.objects.create(
        created_by=user if getattr(user, "is_authenticated", False) else None,
        technologies=techs,
        site_names=[],
        pre_check=has_5g,
        full_check=True,
        status=CheckAnalysisStatus.DRAFT,
    )


def attach_ep_job(combined: CombinedCheck, job: ImportJob) -> CombinedCheck:
    combined.ep_job = job
    combined.save(update_fields=["ep_job", "updated_at"])
    return combined


def set_sites(combined: CombinedCheck, site_names: list[str]) -> CombinedCheck:
    sites = sorted({str(name).strip() for name in site_names if str(name).strip()})
    if not sites:
        raise ValueError("Select at least one site.")
    if combined.ep_job_id is None:
        raise ValueError("Import an EP file before selecting sites.")
    combined.site_names = sites
    combined.save(update_fields=["site_names", "updated_at"])
    return combined


def sites_across_technologies(
    job: ImportJob,
    technologies: list[str],
    search: str = "",
) -> list[dict]:
    """List sites that have cells in any of the selected technologies."""
    techs = _normalize_technologies(technologies)
    inactive = Q(on_air__iexact="NO") | Q(on_air__iexact="INATIVO")
    qs = EpCell.objects.filter(job=job, technology__in=techs)
    if search:
        qs = qs.filter(site_name__icontains=search)

    grouped = (
        qs.values("site_name")
        .annotate(
            cell_count=Count("id"),
            inactive_count=Count("id", filter=inactive),
            explicit_count=Count("id", filter=~Q(on_air="")),
        )
        .order_by("site_name")
    )

    tech_rows = (
        EpCell.objects.filter(job=job, technology__in=techs)
        .values("site_name", "technology")
        .annotate(count=Count("id"))
    )
    techs_by_site: dict[str, list[str]] = {}
    for row in tech_rows:
        techs_by_site.setdefault(row["site_name"], []).append(row["technology"])

    keys = site_family_keys([site["site_name"] for site in grouped])
    sites: list[dict] = []
    for site in grouped:
        present = sorted(
            techs_by_site.get(site["site_name"], []),
            key=lambda t: techs.index(t) if t in techs else 99,
        )
        if not present:
            continue
        sites.append(
            {
                "site_name": site["site_name"],
                "site_key": keys.get(site["site_name"], site["site_name"].strip().upper()),
                "cell_count": site["cell_count"],
                "technologies": present,
                "status": (
                    "Inactive" if site["explicit_count"] and site["inactive_count"] == site["cell_count"] else "Active"
                ),
            }
        )
    return sites


@transaction.atomic
def materialize_analyses(combined: CombinedCheck) -> list[CheckAnalysis]:
    """Create one CheckAnalysis per (technology, site) for the combined selection."""
    if combined.ep_job_id is None:
        raise ValueError("Import an EP file before generating scripts.")
    sites = [str(s).strip() for s in (combined.site_names or []) if str(s).strip()]
    techs = _normalize_technologies(combined.technologies or [])
    if len(techs) < 2:
        raise ValueError("Select at least two technologies.")
    if not sites:
        raise ValueError("Select at least one site.")

    combined.analyses.all().delete()

    created: list[CheckAnalysis] = []
    for site in sites:
        for tech in techs:
            cells = list(
                EpCell.objects.filter(
                    job_id=combined.ep_job_id,
                    technology=tech,
                    site_name=site,
                )
                .order_by("cell_name")
                .values_list("cell_name", flat=True)
            )
            if not cells:
                continue
            pre_check = bool(combined.pre_check and tech == "5G")
            full_check = bool(combined.full_check)
            if tech in FULL_CHECK_ONLY_TECHNOLOGIES:
                pre_check = False
                full_check = True
            if not pre_check and not full_check:
                continue
            created.append(
                CheckAnalysis.objects.create(
                    created_by=combined.created_by,
                    ep_job_id=combined.ep_job_id,
                    combined_check=combined,
                    technology=tech,
                    site_name=site,
                    selected_cells=cells,
                    pre_check=pre_check,
                    full_check=full_check,
                    status=CheckAnalysisStatus.AWAITING_RETURNS,
                )
            )

    if not created:
        raise ValueError("No cells found for the selected sites and technologies.")

    combined.status = CheckAnalysisStatus.AWAITING_RETURNS
    combined.save(update_fields=["status", "updated_at"])
    return created


def build_scripts(combined: CombinedCheck) -> dict:
    """Build Pre-check / Full Check scripts aggregated and per technology."""
    precheck_parts: list[str] = []
    full_parts: list[str] = []
    by_technology: dict[str, dict[str, str]] = {}

    analyses = list(combined.analyses.select_related("ep_job").order_by("technology", "site_name"))
    for analysis in analyses:
        bucket = by_technology.setdefault(
            analysis.technology,
            {"precheck_script": "", "full_check_script": "", "label": tech_label(analysis.technology)},
        )
        header = f"# --- {tech_label(analysis.technology)} · {analysis.site_name} ---"
        if analysis.pre_check:
            script = generate_precheck_script(
                analysis.technology,
                site_name=analysis.site_name,
                cell_names=analysis.selected_cells or [],
            )
            if script.strip():
                block = f"{header}\n{script.rstrip()}\n"
                precheck_parts.append(block)
                bucket["precheck_script"] = (
                    f"{bucket['precheck_script']}\n{block}".strip() + "\n" if bucket["precheck_script"] else block
                )
        if analysis.full_check:
            script = generate_full_check_script(
                analysis.technology,
                site_name=analysis.site_name,
                cell_names=analysis.selected_cells or [],
                cell_ids=_cell_ids_for_analysis(analysis),
                bsc=_bsc_for_analysis(analysis),
                bts=analysis.site_name,
                enodeb_id=_enodeb_id_for_analysis(analysis),
            )
            if script.strip():
                block = f"{header}\n{script.rstrip()}\n"
                full_parts.append(block)
                bucket["full_check_script"] = (
                    f"{bucket['full_check_script']}\n{block}".strip() + "\n" if bucket["full_check_script"] else block
                )

    return {
        "precheck_script": "\n".join(precheck_parts).rstrip() + ("\n" if precheck_parts else ""),
        "full_check_script": "\n".join(full_parts).rstrip() + ("\n" if full_parts else ""),
        "by_technology": by_technology,
    }


def refresh_combined_status(combined: CombinedCheck) -> str:
    """Set CombinedCheck.status to the worst child status."""
    from poscheck.services.orchestrator import worst_analysis_status

    statuses = list(combined.analyses.values_list("status", flat=True))
    if not statuses:
        return combined.status
    if any(s == CheckAnalysisStatus.PROCESSING for s in statuses):
        combined.status = CheckAnalysisStatus.PROCESSING
    elif any(s == CheckAnalysisStatus.AWAITING_RETURNS for s in statuses):
        combined.status = CheckAnalysisStatus.AWAITING_RETURNS
    elif any(s == CheckAnalysisStatus.DRAFT for s in statuses):
        combined.status = CheckAnalysisStatus.DRAFT
    else:
        combined.status = worst_analysis_status(*statuses)
    combined.save(update_fields=["status", "updated_at"])
    return combined.status


def total_cells(combined: CombinedCheck) -> int:
    return sum(len(a.selected_cells or []) for a in combined.analyses.all())


def _normalize_technologies(technologies: list[str]) -> list[str]:
    allowed = {item["id"] for item in TECH_OPTIONS}
    ordered: list[str] = []
    for tech in technologies:
        value = str(tech or "").upper().strip()
        if value == "5G NR":
            value = "5G"
        if value in allowed and value not in ordered:
            ordered.append(value)
    return ordered


def _cell_ids_for_analysis(analysis: CheckAnalysis) -> list[str]:
    ids: list[str] = []
    cells = EpCell.objects.filter(
        job_id=analysis.ep_job_id,
        technology=analysis.technology,
        site_name=analysis.site_name,
        cell_name__in=analysis.selected_cells or [],
    ).order_by("cell_name")
    for cell in cells:
        value = ep_cell_id_from_raw(cell.raw, analysis.technology)
        if value:
            ids.append(value)
    return ids


def _bsc_for_analysis(analysis: CheckAnalysis) -> str:
    if analysis.technology != "2G":
        return ""
    cell = (
        EpCell.objects.filter(
            job_id=analysis.ep_job_id,
            technology=analysis.technology,
            site_name=analysis.site_name,
            cell_name__in=analysis.selected_cells or [],
        )
        .order_by("cell_name")
        .first()
    )
    if cell is None:
        return ""
    return str((cell.raw or {}).get("BSC") or "").strip()


def _enodeb_id_for_analysis(analysis: CheckAnalysis) -> str:
    if analysis.technology != "4G":
        return ""
    cell = (
        EpCell.objects.filter(
            job_id=analysis.ep_job_id,
            technology=analysis.technology,
            site_name=analysis.site_name,
            cell_name__in=analysis.selected_cells or [],
        )
        .order_by("cell_name")
        .first()
    )
    if cell is None:
        return ""
    value = (cell.raw or {}).get("ENODEB ID")
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text
