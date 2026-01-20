from __future__ import annotations

import logging
from datetime import datetime

DOMAIN = "petlibro_local_ha"

# Default update interval (minutes)
DEFAULT_SCAN_INTERVAL = 5

# MQTT topics
TOPIC_DEVICE_EVENT = "dl/{model}/{sn}/device/event/post"
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

# Get timezone offset in hours
TZ_OFFSET = datetime.now().astimezone().utcoffset().total_seconds() / 3600
