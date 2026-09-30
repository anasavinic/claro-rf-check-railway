"""Technology engine protocol for Full Check processing."""

from __future__ import annotations

from typing import Any, Protocol

from precheck.models import CheckAnalysis


class PoscheckEngine(Protocol):
    technology: str

    def supported(self, analysis: CheckAnalysis) -> bool: ...

    def parse_return(self, text: str) -> Any: ...

    def parse_return_bytes(self, payload: bytes) -> Any: ...

    def resolve_expected(self, analysis: CheckAnalysis) -> Any: ...

    def compare(self, expected: Any, extraction: Any) -> Any: ...
