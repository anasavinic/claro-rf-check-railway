"""XLSX package checks: extension, magic bytes, OOXML members, zip-bomb limits."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import BinaryIO

from ep_import.schema import (
    ALLOWED_EXTENSIONS,
    MAX_COMPRESSION_RATIO,
    MAX_UNCOMPRESSED_BYTES,
    MAX_UPLOAD_BYTES,
    MAX_ZIP_ENTRIES,
)
from ep_import.services.errors import (
    EpImportIssue,
    compression_ratio_exceeded,
    file_too_large,
    invalid_extension,
    invalid_xlsx_content,
    uncompressed_too_large,
    unsupported_legacy_xls,
)

XLSX_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0"
OOXML_CONTENT_TYPES = "[Content_Types].xml"
OOXML_WORKBOOK = "xl/workbook.xml"


def validate_upload_file(uploaded) -> list[EpImportIssue]:
    """Validate an uploaded file and rewind it for later storage."""
    name = getattr(uploaded, "name", "") or ""
    size = getattr(uploaded, "size", None)
    issues = validate_file_meta(name, size)
    if issues:
        return issues
    issues = validate_xlsx_package(uploaded, name)
    _rewind(uploaded)
    return issues


def validate_file_meta(filename: str, size_bytes: int | None = None) -> list[EpImportIssue]:
    issues: list[EpImportIssue] = []
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        issues.append(invalid_extension(filename or "file"))
    if size_bytes is not None and size_bytes > MAX_UPLOAD_BYTES:
        issues.append(file_too_large(size_bytes, MAX_UPLOAD_BYTES))
    return issues


def validate_xlsx_package(fileobj: BinaryIO, filename: str) -> list[EpImportIssue]:
    """Reject anything that is not a bounded Office Open XML package."""
    try:
        header = fileobj.read(8)
    except OSError:
        return [invalid_xlsx_content(filename or "file")]
    finally:
        _rewind(fileobj)

    if header.startswith(OLE_MAGIC):
        return [unsupported_legacy_xls(filename or "file")]
    if not header.startswith(XLSX_MAGIC):
        return [invalid_xlsx_content(filename or "file")]

    try:
        with zipfile.ZipFile(fileobj) as package:
            names = package.namelist()
            if len(names) > MAX_ZIP_ENTRIES:
                return [invalid_xlsx_content(filename or "file")]
            if OOXML_CONTENT_TYPES not in names or OOXML_WORKBOOK not in names:
                return [invalid_xlsx_content(filename or "file")]
            return _zip_limits(package)
    except zipfile.BadZipFile:
        return [invalid_xlsx_content(filename or "file")]
    except OSError:
        return [invalid_xlsx_content(filename or "file")]
    finally:
        _rewind(fileobj)


def sha256_file(fileobj: BinaryIO) -> str:
    digest = hashlib.sha256()
    _rewind(fileobj)
    while True:
        chunk = fileobj.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    _rewind(fileobj)
    return digest.hexdigest()


def _zip_limits(package: zipfile.ZipFile) -> list[EpImportIssue]:
    uncompressed = 0
    compressed = 0
    for info in package.infolist():
        uncompressed += info.file_size
        compressed += info.compress_size
        if uncompressed > MAX_UNCOMPRESSED_BYTES:
            return [uncompressed_too_large(MAX_UNCOMPRESSED_BYTES)]
    if compressed > 0 and uncompressed > 1024 * 1024:
        ratio = uncompressed / compressed
        if ratio > MAX_COMPRESSION_RATIO:
            return [compression_ratio_exceeded()]
    return []


def _rewind(fileobj: BinaryIO) -> None:
    seek = getattr(fileobj, "seek", None)
    if callable(seek):
        fileobj.seek(0)
