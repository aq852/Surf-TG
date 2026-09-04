"""RFC 7233 single byte-range parsing and Telegram chunk planning."""

from __future__ import annotations

from dataclasses import dataclass


class RangeNotSatisfiable(ValueError):
    pass


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int
    total: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True)
class ChunkPlan:
    offset: int
    first_cut: int
    last_cut: int
    count: int


def parse_range(value: str | None, file_size: int) -> tuple[ByteRange, bool]:
    if file_size <= 0:
        raise RangeNotSatisfiable("empty file")
    if not value:
        return ByteRange(0, file_size - 1, file_size), False
    if not value.startswith("bytes=") or "," in value:
        raise RangeNotSatisfiable("only one byte range is supported")
    spec = value[6:].strip()
    try:
        start_text, end_text = spec.split("-", 1)
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                raise ValueError
            start, end = max(0, file_size - suffix), file_size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
            if start < 0 or start >= file_size or end < start:
                raise ValueError
            end = min(end, file_size - 1)
    except (TypeError, ValueError) as exc:
        raise RangeNotSatisfiable("invalid byte range") from exc
    return ByteRange(start, end, file_size), True


def plan_chunks(byte_range: ByteRange, chunk_size: int = 1024 * 1024) -> ChunkPlan:
    offset = byte_range.start - (byte_range.start % chunk_size)
    return ChunkPlan(
        offset=offset,
        first_cut=byte_range.start - offset,
        last_cut=(byte_range.end % chunk_size) + 1,
        count=(byte_range.end // chunk_size) - (offset // chunk_size) + 1,
    )
