"""Read-only entities: one per field of the coordinator snapshot."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import InverterData
from .const import DOMAIN, MANUFACTURER
from .coordinator import PvInverterCoordinator

WORK_MODES = {
    0: "Standby",
    1: "Self-use",
    2: "Feed-in priority",
    3: "Battery priority",
    9: "Fault",
}


@dataclass(frozen=True, kw_only=True)
class PvSensorDescription(SensorEntityDescription):
    """Entity description plus the function that extracts its value."""

    value_fn: Callable[[InverterData], float | int | str | None]


SENSORS: tuple[PvSensorDescription, ...] = (
    PvSensorDescription(
        key="pv_power",
        name="PV power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: data.pv_power,
    ),
    PvSensorDescription(
        key="grid_power",
        name="Grid power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: data.grid_power,
    ),
    PvSensorDescription(
        key="load_power",
        name="Load power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.load_power,
    ),
    PvSensorDescription(
        key="battery_power",
        name="Battery power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.battery_power,
    ),
    PvSensorDescription(
        key="battery_soc",
        name="Battery SOC",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: data.battery_soc,
    ),
    PvSensorDescription(
        key="temperature",
        name="Inverter temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.temperature,
    ),
    PvSensorDescription(
        key="work_mode",
        name="Work mode",
        icon="mdi:state-machine",
        value_fn=lambda data: (
            WORK_MODES.get(data.work_mode, str(data.work_mode))
            if data.work_mode is not None
            else None
        ),
    ),
    PvSensorDescription(
        key="energy_today",
        name="Production today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda data: data.energy_today,
    ),
    PvSensorDescription(
        key="energy_total",
        name="Total production",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda data: data.energy_total,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator: PvInverterCoordinator = entry.runtime_data
    assert coordinator.identity is not None  # guaranteed by first refresh
    async_add_entities(
        PvInverterSensor(coordinator, description, coordinator.identity)
        for description in SENSORS
    )


class PvInverterSensor(CoordinatorEntity[PvInverterCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: PvSensorDescription

    def __init__(self, coordinator, description, identity) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{identity.serial}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity.serial)},
            manufacturer=MANUFACTURER,
            model=identity.model,
            sw_version=identity.sw_version,
            serial_number=identity.serial,
            name=f"PV Inverter {identity.serial}",
        )

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)