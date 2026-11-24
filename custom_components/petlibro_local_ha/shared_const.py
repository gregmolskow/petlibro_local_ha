from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.util import dt as dt_util

DOMAIN = "petlibro_local_ha"

# Default update interval (minutes)
DEFAULT_SCAN_INTERVAL = 5

# MQTT topics
TOPIC_DEVICE_EVENT = "dl/{model}/{sn}/device/event/post"
TOPIC_DEVICE_EVENT_SUB = "dl/{model}/{sn}/device/event/sub"
TOPIC_DEVICE_CONTROL = "dl/{model}/{sn}/device/service/sub"
TOPIC_DEVICE_CONTROL_IN = "dl/{model}/{sn}/device/service/post"
TOPIC_DEVICE_HEARTBEAT = "dl/{model}/{sn}/device/heart/post"

_LOGGER = logging.getLogger(__name__)

# Device model
MODEL_PLAF301 = "PLAF301"
MODEL_PLWF116 = "PLWF116"
MANUFACTURER = "Petlibro"

# Get local timezone
TZ = datetime.now().astimezone().tzinfo


MINUTES_PER_DAY = 1440
MINUTES_PER_HOUR = 60
DAYS_PER_WEEK = 7
MAXIMUM_NUMBER_OF_PLANS = 10


def _get_tz_offset_minutes() -> int:
    """Get the current Home Assistant server timezone offset in minutes."""
    offset = dt_util.now().utcoffset()
    if offset is None:
        offset = datetime.now().astimezone().utcoffset()
    return round(offset.total_seconds() / 60) if offset else 0


def get_tz_offset_hours() -> float:
    """Get the current local timezone offset in hours dynamically."""
    return _get_tz_offset_minutes() / MINUTES_PER_HOUR


# Backward compatibility
TZ_OFFSET = get_tz_offset_hours()


def _shift_time_and_days(
    time_str: str,
    repeat_days: list[int] | None,
    offset_minutes: int,
) -> tuple[str, list[int]]:
    """Shift an HH:MM string and Petlibro repeatDay list by *offset_minutes*."""
    if repeat_days is None:
        repeat_days = [1, 2, 3, 4, 5, 6, 7]

    parts = time_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])

    total_minutes = hours * MINUTES_PER_HOUR + minutes + offset_minutes
    day_shift, rem_minutes = divmod(total_minutes, MINUTES_PER_DAY)
    shifted_hours, shifted_minutes = divmod(rem_minutes, MINUTES_PER_HOUR)

    shifted_days = [
        ((d - 1 + day_shift) % DAYS_PER_WEEK) + 1 for d in repeat_days
    ]
    return f"{shifted_hours:02d}:{shifted_minutes:02d}", sorted(shifted_days)


def local_time_to_utc(
    local_time_str: str, repeat_days: list[int] | None = None
) -> tuple[str, list[int]]:
    """Convert local HH:MM string to UTC HH:MM, adjusting repeatDay if crossing midnight.

    repeatDay: 1=Mon, ..., 7=Sun (Petlibro convention)
    """
    return _shift_time_and_days(
        local_time_str, repeat_days, -_get_tz_offset_minutes()
    )


def utc_to_local_time(
    utc_time_str: str, repeat_days: list[int] | None = None
) -> tuple[str, list[int]]:
    """Convert UTC HH:MM string to local HH:MM, adjusting repeatDay if crossing midnight."""
    return _shift_time_and_days(
        utc_time_str, repeat_days, _get_tz_offset_minutes()
    )
