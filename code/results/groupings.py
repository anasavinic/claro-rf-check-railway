"""Group consolidated validations by technology, site, and category."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from precheck.services.validator import (
    VALIDATION_STATUS_CONSISTENT,
    VALIDATION_STATUS_FAILED,
    VALIDATION_STATUS_INCONSISTENT,
)
from results.models import ConsolidatedAnalysis, ValidationItem
from results.status import tech_label


@dataclass(frozen=True)
class ValidationGroup:
    key: str
    label: str
    counts: dict[str, int]
    validations: tuple[ValidationItem, ...]


def by_technology(consolidated: ConsolidatedAnalysis) -> tuple[ValidationGroup, ...]:
    return _groups(
        consolidated.validations,
        key_fn=lambda item: item.technology,
        label_fn=lambda key: tech_label(key),
        order=list(consolidated.technologies),
    )


def by_site(consolidated: ConsolidatedAnalysis) -> tuple[ValidationGroup, ...]:
    return _groups(
        consolidated.validations,
        key_fn=lambda item: item.site_name,
        label_fn=lambda key: key,
        order=list(consolidated.sites),
    )


def by_category(consolidated: ConsolidatedAnalysis) -> tuple[ValidationGroup, ...]:
    """Category is the validation code (e.g. ENODEB_ID, CELL_NAME)."""
    return _groups(
        consolidated.validations,
        key_fn=lambda item: item.code or item.label or "UNKNOWN",
        label_fn=lambda key: key,
        order=None,
    )


def _groups(
    validations: tuple[ValidationItem, ...],
    *,
    key_fn,
    label_fn,
    order: list[str] | None,
) -> tuple[ValidationGroup, ...]:
    buckets: dict[str, list[ValidationItem]] = defaultdict(list)
    for item in validations:
        buckets[key_fn(item)].append(item)

    keys = order if order is not None else sorted(buckets.keys())
    # Include any unexpected keys at the end
    for key in buckets:
        if key not in keys:
            keys.append(key)

    groups: list[ValidationGroup] = []
    for key in keys:
        rows = tuple(buckets.get(key) or ())
        if not rows and order is not None:
            continue
        groups.append(
            ValidationGroup(
                key=key,
                label=label_fn(key),
                counts=_counts(rows),
                validations=rows,
            )
        )
    return tuple(groups)


def _counts(rows: tuple[ValidationItem, ...] | list[ValidationItem]) -> dict[str, int]:
    consistent = sum(1 for item in rows if item.status == VALIDATION_STATUS_CONSISTENT)
    inconsistent = sum(1 for item in rows if item.status == VALIDATION_STATUS_INCONSISTENT)
    failed = sum(1 for item in rows if item.status == VALIDATION_STATUS_FAILED)
    return {
        "total": len(rows),
        "consistent": consistent,
        "inconsistent": inconsistent,
        "failed": failed,
        "success": consistent,
        "alert": failed,
        "failure": inconsistent,
    }
