"""The single owner of polling. Entities only ever read coordinator.data."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .client import (
    DeviceIdentity,
    InverterAuthError,
    InverterClient,
    InverterConnectionError,
    InverterData,
    InverterError,
    InverterWriteError,
)
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class PvInverterCoordinator(DataUpdateCoordinator[InverterData]):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: InverterClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )
            ),
        )
        self.client = client
        self.identity: DeviceIdentity | None = None

    async def _async_update_data(self) -> InverterData:
        try:
            if self.identity is None:
                self.identity = await self.client.async_identify()
            return await self.client.async_read()
        except InverterAuthError as err:            # subclass first!
            raise ConfigEntryAuthFailed(f"authentication failed: {err}") from err
        except (InverterConnectionError, InverterError) as err:
            raise UpdateFailed(f"cannot read inverter: {err}") from err

    async def async_set_power_limit(self, percent: int) -> None:
        """Single write path, used by number.py and by the optional action."""
        try:
            await self.client.async_write_power_limit(percent)
        except InverterWriteError as err:
            raise HomeAssistantError(f"inverter rejected the command: {err}") from err
        except InverterConnectionError as err:
            raise HomeAssistantError(f"inverter is offline: {err}") from err
        _LOGGER.debug("power limit set to %s%%", percent)
        await self.async_request_refresh()