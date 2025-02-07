
from dataclasses import dataclass


@dataclass(unsafe_hash=True)
class SearchResult:
    id: str
    text: str
    score: float
    source: str

@dataclass(unsafe_hash=True)
class SerperSearchResult:
    title: str
    link: str
    search_text: str
