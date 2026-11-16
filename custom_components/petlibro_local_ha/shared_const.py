from __future__ import annotations

import logging
from datetime import datetime

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


def get_tz_offset_hours() -> float:
    """Get the current local timezone offset in hours dynamically."""
    offset = datetime.now().astimezone().utcoffset()
    return offset.total_seconds() / 3600 if offset else 0.0


# Backward compatibility
TZ_OFFSET = get_tz_offset_hours()


def local_time_to_utc(
    local_time_str: str, repeat_days: list[int] | None = None
) -> tuple[str, list[int]]:
    """Convert local HH:MM string to UTC HH:MM, adjusting repeatDay if crossing midnight.

    repeatDay: 1=Mon, ..., 7=Sun (Petlibro convention)
    """
    if repeat_days is None:
        repeat_days = [1, 2, 3, 4, 5, 6, 7]

    parts = local_time_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])

    offset = int(get_tz_offset_hours())
    raw_utc_hours = hours - offset
    utc_hours = raw_utc_hours % 24
    day_shift = raw_utc_hours // 24

    shifted_days = [((d - 1 + day_shift) % 7) + 1 for d in repeat_days]
    return f"{utc_hours:02d}:{minutes:02d}", sorted(shifted_days)


def utc_to_local_time(
    utc_time_str: str, repeat_days: list[int] | None = None
) -> tuple[str, list[int]]:
    """Convert UTC HH:MM string to local HH:MM, adjusting repeatDay if crossing midnight."""
    if repeat_days is None:
        repeat_days = [1, 2, 3, 4, 5, 6, 7]

    parts = utc_time_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])

    offset = int(get_tz_offset_hours())
    raw_local_hours = hours + offset
    local_hours = raw_local_hours % 24
    day_shift = raw_local_hours // 24

    shifted_days = [((d - 1 + day_shift) % 7) + 1 for d in repeat_days]
    return f"{local_hours:02d}:{minutes:02d}", sorted(shifted_days)

