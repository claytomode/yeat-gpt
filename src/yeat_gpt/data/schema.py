from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class SongRecord:
    genius_id: int
    title: str
    url: str


@dataclass
class CatalogEntry:
    genius_id: int
    title: str
    url: str
    album: str | None = None
    text: str = ""
    line_count: int = 0
    source: str = "genius"
    scope_kind: str | None = None
    lrclib_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
