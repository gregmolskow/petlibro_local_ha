"""Shared feeding schedule validation and helpers.

This module provides validation logic used by both the config flow UI
and the HA service calls, ensuring consistent rules everywhere.
"""

from __future__ import annotations

from typing import Any

from .shared_const import _LOGGER

# Hard limit – the device protocol replaces the entire plan list on every
# update, and the PLAF301 firmware has been observed to accept up to 10.
MAX_FEEDING_PLANS = 10

# Portions range accepted by the feeder hardware.
MIN_PORTIONS = 1
MAX_PORTIONS = 10


class ScheduleValidationError(Exception):
    """Raised when a schedule fails validation."""


def validate_time_string(time_str: str) -> str:
    """Validate and normalise an ``HH:MM`` time string.

    Accepts ``H:MM``, ``HH:MM``, and ``HH:MM:SS`` (seconds are dropped).

    Args:
        time_str: The time string to validate.

    Returns:
        Normalised ``HH:MM`` string.

    Raises:
        ScheduleValidationError: If the format is invalid.
    """
    if not time_str or not isinstance(time_str, str):
        raise ScheduleValidationError(f"Invalid time value: {time_str!r}")

    parts = time_str.strip().split(":")
    if len(parts) < 2:
        raise ScheduleValidationError(
            f"Time must be in HH:MM format, got: {time_str!r}"
        )

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError as exc:
        raise ScheduleValidationError(
            f"Time contains non-numeric values: {time_str!r}"
        ) from exc

    if not (0 <= hours <= 23):
        raise ScheduleValidationError(
            f"Hours must be 0-23, got {hours}"
        )
    if not (0 <= minutes <= 59):
        raise ScheduleValidationError(
            f"Minutes must be 0-59, got {minutes}"
        )

    return f"{hours:02d}:{minutes:02d}"


def validate_portions(portions: Any) -> int:
    """Validate and coerce a portions value.

    Args:
        portions: Raw portions value (may be int, float, str, or None).

    Returns:
        Validated integer portion count.

    Raises:
        ScheduleValidationError: If the value is out of range.
    """
    if portions is None:
        return MIN_PORTIONS

    try:
        portions_int = int(portions)
    except (ValueError, TypeError) as exc:
        raise ScheduleValidationError(
            f"Portions must be a number, got: {portions!r}"
        ) from exc

    if portions_int < MIN_PORTIONS or portions_int > MAX_PORTIONS:
        raise ScheduleValidationError(
            f"Portions must be between {MIN_PORTIONS} and {MAX_PORTIONS}, "
            f"got {portions_int}"
        )

    return portions_int


def validate_repeat_days(days: Any) -> list[int]:
    """Validate and normalise a repeat-day list.

    Petlibro convention: 1 = Monday … 7 = Sunday.

    Args:
        days: Raw day list, or ``None`` for every day.

    Returns:
        Sorted list of unique day integers.

    Raises:
        ScheduleValidationError: If any value is outside 1-7.
    """
    if not days:
        return [1, 2, 3, 4, 5, 6, 7]

    if not isinstance(days, list):
        raise ScheduleValidationError(
            f"repeat_days must be a list, got {type(days).__name__}"
        )

    validated: list[int] = []
    for d in days:
        try:
            day_int = int(d)
        except (ValueError, TypeError) as exc:
            raise ScheduleValidationError(
                f"Day value must be an integer 1-7, got: {d!r}"
            ) from exc
        if day_int < 1 or day_int > 7:
            raise ScheduleValidationError(
                f"Day value must be 1 (Mon) – 7 (Sun), got {day_int}"
            )
        validated.append(day_int)

    return sorted(set(validated))


def _days_overlap(days_a: list[int], days_b: list[int]) -> bool:
    """Return True if two repeat-day lists share at least one day."""
    return bool(set(days_a) & set(days_b))


def check_duplicate_schedule(
    time_str: str,
    days: list[int],
    existing_schedules: list[dict[str, Any]],
    *,
    exclude_index: int | None = None,
) -> str | None:
    """Check whether a schedule at *time_str* on *days* duplicates an existing one.

    Args:
        time_str: Normalised ``HH:MM`` local time.
        days: Validated repeat-day list.
        existing_schedules: The current list of schedule dicts
            (each with ``"time"`` and ``"repeatDay"`` keys).
        exclude_index: Optionally skip this index (used when editing).

    Returns:
        A human-readable error string if a duplicate is found, else ``None``.
    """
    for idx, existing in enumerate(existing_schedules):
        if exclude_index is not None and idx == exclude_index:
            continue

        existing_time = existing.get("time", "")
        existing_days = existing.get("repeatDay") or [1, 2, 3, 4, 5, 6, 7]

        if existing_time == time_str and _days_overlap(days, existing_days):
            return (
                f"A schedule at {time_str} already exists on overlapping days"
            )

    return None


def check_max_schedules(
    existing_schedules: list[dict[str, Any]],
    adding: int = 1,
) -> str | None:
    """Check whether adding more schedules would exceed the limit.

    Args:
        existing_schedules: Current schedule list.
        adding: Number of schedules being added.

    Returns:
        A human-readable error string if the limit would be exceeded,
        else ``None``.
    """
    if len(existing_schedules) + adding > MAX_FEEDING_PLANS:
        return (
            f"Maximum of {MAX_FEEDING_PLANS} feeding schedules allowed. "
            f"Currently have {len(existing_schedules)}."
        )
    return None


def validate_schedule_entry(
    schedule: dict[str, Any],
) -> dict[str, Any]:
    """Validate and normalise a single schedule dict.

    Expected keys: ``time``, ``portions``, and optionally ``repeatDay``.

    Args:
        schedule: Raw schedule dictionary.

    Returns:
        Cleaned schedule dictionary with normalised values.

    Raises:
        ScheduleValidationError: If validation fails.
    """
    if "time" not in schedule:
        raise ScheduleValidationError("Schedule is missing 'time' field")

    time_str = validate_time_string(schedule["time"])
    portions = validate_portions(schedule.get("portions", 1))
    days = validate_repeat_days(schedule.get("repeatDay"))

    result: dict[str, Any] = {
        "time": time_str,
        "portions": portions,
        "repeatDay": days,
    }

    # Preserve planId if present (needed for updating existing plans)
    if "planId" in schedule and schedule["planId"] is not None:
        result["planId"] = schedule["planId"]

    return result


def validate_schedule_list(
    schedules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate a full list of schedules (used by the service call).

    Checks every entry individually, then checks for duplicates and the
    max-plan limit.

    Args:
        schedules: List of raw schedule dictionaries.

    Returns:
        List of validated and normalised schedule dictionaries.

    Raises:
        ScheduleValidationError: On any validation failure.
    """
    if not isinstance(schedules, list):
        raise ScheduleValidationError(
            f"schedules must be a list, got {type(schedules).__name__}"
        )

    max_err = check_max_schedules([], adding=len(schedules))
    if max_err:
        raise ScheduleValidationError(max_err)

    validated: list[dict[str, Any]] = []
    for idx, raw in enumerate(schedules):
        try:
            entry = validate_schedule_entry(raw)
        except ScheduleValidationError as exc:
            raise ScheduleValidationError(
                f"Schedule {idx + 1}: {exc}"
            ) from exc

        # Check for duplicates against already-validated entries
        dup_err = check_duplicate_schedule(
            entry["time"], entry["repeatDay"], validated
        )
        if dup_err:
            raise ScheduleValidationError(
                f"Schedule {idx + 1}: {dup_err}"
            )

        validated.append(entry)

    return validated
