"""Outlook CSV and free-text address parsing.

Vivo RF Check reads the column ``E-mail Address`` from an Outlook export
(windows-1252). UTF-8 is accepted when the file decodes as UTF-8; otherwise
the bytes are read as windows-1252.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

EMAIL_COLUMN = "e-mail address"
MAX_CSV_BYTES = 5 * 1024 * 1024


class CsvFormatError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AddressBatch:
    accepted: list[str]
    invalid: list[str]
    duplicates: int

    @property
    def ignored(self) -> int:
        return len(self.invalid)


def parse_freeform(text: str) -> AddressBatch:
    parts = _split_freeform(text or "")
    return _collect(parts)


def combine_batches(*batches: AddressBatch) -> AddressBatch:
    accepted: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    duplicates = 0
    for batch in batches:
        invalid.extend(batch.invalid)
        duplicates += batch.duplicates
        for address in batch.accepted:
            if address in seen:
                duplicates += 1
                continue
            seen.add(address)
            accepted.append(address)
    return AddressBatch(accepted=accepted, invalid=invalid, duplicates=duplicates)


def invalid_address_message(tokens: list[str]) -> str:
    shown = tokens[:8]
    listed = ", ".join(shown)
    extra = len(tokens) - len(shown)
    if extra:
        listed = f"{listed} e mais {extra}"
    if len(tokens) == 1:
        return f"Endereço inválido: {listed}. Informe um e-mail com @."
    return f"Endereços inválidos: {listed}. Informe e-mails com @."


def parse_outlook_csv(raw: bytes) -> AddressBatch:
    if not raw or not raw.strip():
        raise CsvFormatError("Arquivo CSV vazio.")
    if len(raw) > MAX_CSV_BYTES:
        raise CsvFormatError("Arquivo excede o limite de 5 MB.")

    text = _decode_csv(raw)
    if not text.strip():
        raise CsvFormatError("Arquivo CSV vazio.")

    delimiter = ";" if _header_line(text).count(";") > _header_line(text).count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    column = _email_column(reader.fieldnames)
    if column is None:
        raise CsvFormatError("O CSV não tem a coluna E-mail Address.")

    values = []
    for row in reader:
        cell = row.get(column) or ""
        values.append(cell)
    return _collect(values)


def format_stats(added: int, duplicates: int) -> str:
    return (
        f"{_count_label(added, 'endereço adicionado', 'endereços adicionados')}, "
        f"{_count_label(duplicates, 'repetido', 'repetidos')}."
    )


def _decode_csv(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("windows-1252")


def _header_line(text: str) -> str:
    return text.splitlines()[0] if text else ""


def _email_column(fieldnames: list[str] | None) -> str | None:
    if not fieldnames:
        return None
    for name in fieldnames:
        if name and name.strip().casefold() == EMAIL_COLUMN:
            return name
    return None


def _split_freeform(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks: list[str] = []
    for line in normalized.split("\n"):
        for piece in line.replace(",", ";").split(";"):
            chunks.append(piece)
    return chunks


def _collect(tokens: list[str]) -> AddressBatch:
    accepted: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    duplicates = 0
    for raw in tokens:
        token = raw.strip().strip("\"'")
        token = token.strip()
        if not token:
            continue
        normalized = _normalize(token)
        if normalized is None:
            invalid.append(token)
            continue
        if normalized in seen:
            duplicates += 1
            continue
        seen.add(normalized)
        accepted.append(normalized)
    return AddressBatch(accepted=accepted, invalid=invalid, duplicates=duplicates)


def _normalize(token: str) -> str | None:
    if any(character.isspace() for character in token):
        return None
    if token.count("@") != 1:
        return None
    local, domain = token.split("@")
    if not local or not domain:
        return None
    return token.casefold()


def _count_label(count: int, singular: str, plural: str) -> str:
    word = singular if count == 1 else plural
    return f"{count} {word}"
