"""Constants for fsolar_inverter_ha. Deliberately free of homeassistant imports."""
from __future__ import annotations

DOMAIN = "fsolar_inverter_ha"

# Config keys. HA ships CONF_HOST / CONF_PORT in homeassistant.const; defining
# them locally keeps client.py free of HA imports so it can become a PyPI lib.
CONF_HOST = "host"
CONF_PORT = "port"
CONF_UNIT_ID = "unit_id"
CONF_SIMULATOR = "simulator"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
DEFAULT_SCAN_INTERVAL = 30

MANUFACTURER = "Example Solar"
MODEL = "Tutorial IV 5000"