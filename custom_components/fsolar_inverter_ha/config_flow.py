"""UI setup: validate the connection BEFORE creating a config entry."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .client import (
    InverterAuthError,
    InverterConnectionError,
    InverterError,
    create_client,
)
from .const import (
    CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, CONF_SIMULATOR, CONF_UNIT_ID,
    DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DEFAULT_UNIT_ID, DOMAIN,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="192.168.1.50"): selector.TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=247)
        ),
        vol.Optional(CONF_SIMULATOR, default=False): selector.BooleanSelector(),
    }
)


class PvInverterConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = create_client(dict(user_input))
            try:
                identity = await client.async_identify()
            except InverterAuthError:
                errors["base"] = "invalid_auth"
            except InverterConnectionError:
                errors["base"] = "cannot_connect"
            except InverterError:
                errors["base"] = "unknown"
            else:
                # Stable ID = device serial, NOT the IP address.
                await self.async_set_unique_id(identity.serial)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"PV Inverter {identity.serial}",
                    data=dict(user_input),
                )
            finally:
                await client.async_close()

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change connection settings / switch simulator <-> real device."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        reconfigure_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=entry.data.get(CONF_HOST, "192.168.1.50")
                ): selector.TextSelector(),
                vol.Required(
                    CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                vol.Required(
                    CONF_UNIT_ID, default=entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=247)),
                vol.Optional(
                    CONF_SIMULATOR, default=entry.data.get(CONF_SIMULATOR, False)
                ): selector.BooleanSelector(),
            }
        )
        if user_input is not None:
            client = create_client(dict(user_input))
            try:
                identity = await client.async_identify()
            except InverterAuthError:
                errors["base"] = "invalid_auth"
            except InverterConnectionError:
                errors["base"] = "cannot_connect"
            except InverterError:
                errors["base"] = "unknown"
            else:
                # Reject only if the new serial belongs to ANOTHER entry, so
                # switching simulator <-> real device keeps working.
                await self.async_set_unique_id(identity.serial)
                self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, **user_input},
                    unique_id=identity.serial,
                )
            finally:
                await client.async_close()

        return self.async_show_form(
            step_id="reconfigure", data_schema=reconfigure_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PvInverterOptionsFlow()


class PvInverterOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=dict(user_input))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
                }
            ),
        )