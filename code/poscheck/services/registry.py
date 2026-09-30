"""Technology registry for Full Check engines."""

from __future__ import annotations

from poscheck.services.errors import PoscheckError, technology_not_supported
from poscheck.services.tech.base import PoscheckEngine
from poscheck.services.tech.g2.validator import G2FullCheckEngine
from poscheck.services.tech.g3.validator import G3FullCheckEngine
from poscheck.services.tech.g4.validator import G4FullCheckEngine
from poscheck.services.tech.g5.validator import G5FullCheckEngine


def get_engine(technology: str) -> PoscheckEngine:
    tech = (technology or "").upper()
    if tech == "5G":
        return G5FullCheckEngine()
    if tech == "4G":
        return G4FullCheckEngine()
    if tech == "3G":
        return G3FullCheckEngine()
    if tech == "2G":
        return G2FullCheckEngine()
    raise PoscheckError("Execution failure", [technology_not_supported(tech)])
