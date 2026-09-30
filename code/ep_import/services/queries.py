"""Read models for sites and cells. Authorization stays in the view layer."""

from __future__ import annotations

from django.db.models import Count, Q

from ep_import.models import EpCell, ImportJob
from ep_import.schema import DEFAULT_PAGE_SIZE


def sites_page(
    job: ImportJob,
    technology: str,
    search: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[dict], int]:
    inactive = Q(on_air__iexact="NO") | Q(on_air__iexact="INATIVO")
    qs = EpCell.objects.filter(job=job, technology=technology)
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
    sites_total = grouped.count()
    offset = (page - 1) * page_size
    sites = []
    for site in grouped[offset : offset + page_size]:
        site["status"] = (
            "Inactive" if site["explicit_count"] and site["inactive_count"] == site["cell_count"] else "Active"
        )
        sites.append(site)
    return sites, sites_total


def cell_search(search: str) -> Q:
    query = Q(cell_name__icontains=search)
    for key in ("FrequencyBand", "CARRIER", "DlNarfcn", "EARFCN_DL", "UARFCN DOWNLINK"):
        query |= Q(**{f"raw__{key}__icontains": search})
    return query
