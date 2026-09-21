"""Conservative Step 2B contracts; no ingestion, imputation or canonical joins.

IDs are season-scoped official FPL IDs. Core match team references require the
separately verified team-code mapping; neither names nor slugs establish identity.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum


def utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("An explicit timezone is required")
    return parsed.astimezone(timezone.utc)


def integer_id(value) -> int:
    """Lossless ID parsing, including CSV '88.0'; reject booleans and truncation."""
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number != number.to_integral_value() or number <= 0:
            raise ValueError("Expected a positive integral identifier")
        return int(number)
    except InvalidOperation:
        raise ValueError("Expected a positive integral identifier") from None


@dataclass(frozen=True)
class ObservationTime:
    event_time: datetime | None
    retrieved_at: datetime
    available_at: datetime
    source_published_at: datetime | None = None
    publication_evidence: str | None = None

    def __post_init__(self):
        for name in ("event_time", "retrieved_at", "available_at", "source_published_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, utc(value))
        if self.retrieved_at is None or self.available_at is None:
            raise ValueError("Retrieval and availability are required")
        if self.source_published_at is not None:
            if not self.publication_evidence or self.source_published_at > self.retrieved_at:
                raise ValueError("Publication time needs evidence and cannot follow retrieval")
        # Step 2B only supports prospective, actually captured input versions.
        # An earlier archive-based availability policy requires separate review.
        if self.available_at < self.retrieved_at:
            raise ValueError("Cannot backdate this captured version")

    def eligible_at(self, forecast_origin_at: datetime) -> bool:
        return self.available_at < utc(forecast_origin_at)


class LabelState(str, Enum):
    PROVISIONAL = "provisional"
    FINAL = "final"
    UNUSABLE = "unusable"


def label_state(history: dict | None, fixture: dict, event: dict,
                *, element_id: int) -> tuple[LabelState, str]:
    """State of the observed minutes/points label, not every optional stat field.

    A zero-minute row can be valid; an absent row cannot establish DNP. Callers
    must check uniqueness of (season, element, fixture) and retain all three raw
    versions. Finality is conservative and versioned, not a promise of no revision.
    """
    try:
        if history is None:
            return LabelState.UNUSABLE, "missing_player_fixture_row"
        if type(element_id) is not int or element_id <= 0:
            raise ValueError
        if type(history["element"]) is not int or history["element"] != element_id:
            raise ValueError
        for value in (history["fixture"], fixture["id"], history["round"], fixture["event"],
                      event["id"], fixture["team_h"], fixture["team_a"], history["opponent_team"]):
            if type(value) is not int or value <= 0:
                raise ValueError
        if history["fixture"] != fixture["id"] or not history["round"] == fixture["event"] == event["id"]:
            raise ValueError
        if type(history["was_home"]) is not bool or fixture["team_h"] == fixture["team_a"]:
            raise ValueError
        opponent = fixture["team_a"] if history["was_home"] else fixture["team_h"]
        if history["opponent_team"] != opponent or utc(history["kickoff_time"]) != utc(fixture["kickoff_time"]):
            raise ValueError
        if type(history["minutes"]) is not int or not 0 <= history["minutes"] <= 120:
            raise ValueError
        if type(history["total_points"]) is not int:
            raise ValueError
        if "starts" in history and (type(history["starts"]) is not int or history["starts"] not in (0, 1)):
            raise ValueError
        if history.get("starts") == 1 and history["minutes"] == 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return LabelState.UNUSABLE, "missing_or_inconsistent_label_context"
    if fixture.get("started") is not True:
        return LabelState.UNUSABLE, "fixture_not_started"
    if fixture.get("finished") is True and event.get("finished") is True and event.get("data_checked") is True:
        return LabelState.FINAL, "official_fixture_and_event_checked"
    return LabelState.PROVISIONAL, "official_completion_not_confirmed"
