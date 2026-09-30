"""Seekable workbook streams that do not depend on a local filesystem path."""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator


class NonClosing:
    """File wrapper so openpyxl cannot close a stream we still need to rewind."""

    def __init__(self, raw: BinaryIO):
        self._raw = raw

    def read(self, size: int = -1) -> bytes:
        return self._raw.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._raw.seek(offset, whence)

    def tell(self) -> int:
        return self._raw.tell()

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        return None


@contextmanager
def owned_workbook_stream(source: str | Path | BinaryIO) -> Iterator[BinaryIO]:
    """Copy ``source`` into a spool we can rewind between validation and persist."""
    spool = tempfile.SpooledTemporaryFile(max_size=2_621_440)
    try:
        if isinstance(source, (str, Path)):
            with open(source, "rb") as handle:
                shutil.copyfileobj(handle, spool)
        else:
            seek = getattr(source, "seek", None)
            if callable(seek):
                source.seek(0)
            shutil.copyfileobj(source, spool)
        spool.seek(0)
        yield spool
    finally:
        spool.close()


@contextmanager
def open_workbook_handle(stream: BinaryIO) -> Iterator[NonClosing]:
    stream.seek(0)
    try:
        yield NonClosing(stream)
    finally:
        stream.seek(0)


def source_name(source: str | Path | BinaryIO, filename: str | None = None) -> str:
    if filename:
        return filename
    name = getattr(source, "name", None)
    if isinstance(name, str) and name:
        return Path(name).name
    if isinstance(source, (str, Path)):
        return Path(source).name
    return "file.xlsx"


def source_size(source: str | Path | BinaryIO, size: int | None = None) -> int | None:
    if size is not None:
        return size
    if isinstance(source, (str, Path)):
        return Path(source).stat().st_size
    value = getattr(source, "size", None)
    return int(value) if isinstance(value, int) else None
