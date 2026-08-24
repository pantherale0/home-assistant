"""Support for Probe Plus BLE sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from pyprobeplus import ProbePlusDevice
from pyprobeplus.parsers import ProbeReading

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ProbePlusConfigEntry, ProbePlusDataUpdateCoordinator
from .entity import ProbePlusEntity

# Coordinator is used to centralize the data updates
PARALLEL_UPDATES = 0


@dataclass(kw_only=True, frozen=True)
class ProbePlusRelaySensorEntityDescription(SensorEntityDescription):
    """Description for Probe Plus sensor entities."""

    value_fn: Callable[[ProbePlusDevice], int | float | None]


@dataclass(kw_only=True, frozen=True)
class ProbePlusProbeSensorEntityDescription(SensorEntityDescription):
    """Description for Probe Plus sensor entities."""

    value_fn: Callable[[ProbeReading], int | float | None]


PROBE_SENSOR_DESCRIPTIONS: tuple[ProbePlusProbeSensorEntityDescription, ...] = (
    ProbePlusProbeSensorEntityDescription(
        key="probe_temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda probe: probe.temperature,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    ProbePlusProbeSensorEntityDescription(
        key="probe_battery",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda probe: probe.battery,
        device_class=SensorDeviceClass.BATTERY,
    ),
    ProbePlusProbeSensorEntityDescription(
        key="probe_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda probe: probe.rssi,
        entity_registry_enabled_default=False,
    ),
    ProbePlusProbeSensorEntityDescription(
        key="probe_voltage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.VOLTAGE,
        value_fn=lambda probe: probe.voltage,
        entity_registry_enabled_default=False,
    ),
)

RELAY_SENSOR_DESCRIPTIONS: tuple[ProbePlusRelaySensorEntityDescription, ...] = (
    ProbePlusRelaySensorEntityDescription(
        key="relay_voltage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.VOLTAGE,
        value_fn=lambda relay: relay.device_state.relay_voltage,
        entity_registry_enabled_default=False,
    ),
    ProbePlusRelaySensorEntityDescription(
        key="relay_battery",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda relay: relay.device_state.relay_battery,
        device_class=SensorDeviceClass.BATTERY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProbePlusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Probe Plus sensors."""
    coordinator = entry.runtime_data

    async_add_entities(
        RelaySensor(coordinator, description)
        for description in RELAY_SENSOR_DESCRIPTIONS
    )

    known_probe_sensors: set[tuple[int, str]] = set()

    @callback
    def _check_probes() -> None:
        new_entities = [
            (slot, probe, description)
            for slot, probe in enumerate(coordinator.device.device_state.probes)
            if any(
                value is not None
                for value in (
                    probe.temperature,
                    probe.ambient_temperature,
                    probe.voltage,
                    probe.rssi,
                )
            )
            for description in PROBE_SENSOR_DESCRIPTIONS
            if (slot, description.key) not in known_probe_sensors
        ]
        if not new_entities:
            return

        known_probe_sensors.update(
            (slot, description.key) for slot, _, description in new_entities
        )
        async_add_entities(
            ProbeSensor(coordinator, description, slot)
            for slot, probe, description in new_entities
        )

    entry.async_on_unload(coordinator.async_add_listener(_check_probes))
    _check_probes()


class RelaySensor(ProbePlusEntity, RestoreSensor):
    """Representation of a Probe Plus relay sensor."""

    entity_description: ProbePlusRelaySensorEntityDescription

    @property
    @override
    def native_value(self) -> int | float | None:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.device)


class ProbeSensor(ProbePlusEntity, RestoreSensor):
    """Representation of a Probe Plus sensor."""

    entity_description: ProbePlusProbeSensorEntityDescription

    def __init__(
        self,
        coordinator: ProbePlusDataUpdateCoordinator,
        entity_description: ProbePlusProbeSensorEntityDescription,
        slot: int,
    ) -> None:
        """Initialize a probe sensor."""
        super().__init__(coordinator, entity_description)
        self.slot = slot
        self._attr_translation_placeholders = {"channel": str(slot + 1)}
        self._attr_unique_id = (
            f"{format_mac(coordinator.device.mac)}_probe_"
            f"{slot + 1}_{entity_description.key}"
        )

    @property
    @override
    def native_value(self) -> int | float | None:
        """Return the state of the sensor."""
        probe = self.device.device_state.probes[self.slot]
        return self.entity_description.value_fn(probe)
