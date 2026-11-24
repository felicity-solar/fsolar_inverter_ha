"""Writable entity: inverter output power limit, in percent."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PvInverterCoordinator


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator: PvInverterCoordinator = entry.runtime_data
    assert coordinator.identity is not None
    async_add_entities([PvPowerLimitNumber(coordinator, coordinator.identity)])


class PvPowerLimitNumber(CoordinatorEntity[PvInverterCoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Power limit"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator, identity) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{identity.serial}_power_limit"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity.serial)}
        )

    @property
    def native_value(self):
        return self.coordinator.data.power_limit

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_power_limit(int(value))