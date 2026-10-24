"""Connector interface. One class per complaint source; each turns raw rows into the canonical ticket dict.

The canonical ticket has the contract fields (see contract/tickets.json) plus a few extra columns
that carry real signals (for example has_attended_image). Extras are allowed; the API model ignores them.
"""
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any, Iterator

CONTRACT_FIELDS = [
    "ticket_id", "city", "data_quality", "source", "category", "text", "lang", "lat", "lng", "h3", "ward",
    "created_at", "closed_at", "closed_by_hash", "status", "closure_note", "closure_photo_url",
]


class Drop(Exception):
    """Raised by normalise() for a row we deliberately exclude. The message is the counted reason."""


class ComplaintSource(ABC):
    name: str
    city: str

    def __init__(self) -> None:
        self.report: Counter = Counter()
        # Ground truth (synthetic sources only), kept apart from tickets so it cannot leak into features.
        self.truth: list[dict[str, Any]] = []

    @abstractmethod
    def fetch(self) -> Iterator[dict[str, Any]]:
        """Yield raw rows exactly as the source provides them."""

    @abstractmethod
    def normalise(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Return a canonical ticket dict, or raise Drop(reason)."""

    def tickets(self) -> Iterator[dict[str, Any]]:
        """Normalised tickets. Drop reasons and kept counts accumulate in self.report."""
        for raw in self.fetch():
            self.report["rows_read"] += 1
            try:
                t = self.normalise(raw)
            except Drop as d:
                self.report[f"dropped:{d}"] += 1
                continue
            self.report["kept"] += 1
            yield t
