"""Lifecycle wiring for fsolar_inverter_ha."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .client import create_client
from .const import DOMAIN
from .coordinator import PvInverterCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]   # step 8 adds Platform.NUMBER

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = create_client(dict(entry.data))
    coordinator = PvInverterCoordinator(hass, entry, client)

    # First refresh BEFORE entities exist. A failure becomes ConfigEntryNotReady
    # (HA retries) or ConfigEntryAuthFailed (HA asks for credentials).
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed -> rebuild everything with the new interval."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_close()
    return unload_ok