"""Sensor platform for Octopus Energy."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import override

from pykrakentech import SupplyType
from pykrakentech.models.account import Account
from pykrakentech.models.meters import MeterPoint

from homeassistant.components.sensor import (
    EntityCategory,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OctopusEnergyBaseCoordinator, OctopusEnergyConfigEntry
from .entity import OctopusEnergySmartMeter

PARALLEL_UPDATES = 0

class OctopusEnergySensor(StrEnum):
    """Store keys for Octopus Energy sensors."""
    LATEST_READING = "latest_reading"
    LATEST_QUANTITY = "latest_quantity"
    CURRENT_CONSUMPTION = "current_consumption"
    CURRENT_USAGE = "current_usage"
    CURRENT_TARIFF_RATE = "current_tariff_rate"
    CURRENT_COST = "current_cost"
    PREVIOUS_CONSUMPTION = "previous_consumption"
    PREVIOUS_COST = "previous_cost"

@dataclass(frozen=True, kw_only=True)
class OctopusEnergyMeterSensorEntityDescription(SensorEntityDescription):
    """Describes an Octopus Energy meter entity."""

    value_fn: Callable[[Account, MeterPoint], float | datetime | None]
    available_fn: Callable[[MeterPoint], bool] | None = None

METER_ENTITY_DESCRIPTIONS: tuple[OctopusEnergyMeterSensorEntityDescription, ...] = (
    OctopusEnergyMeterSensorEntityDescription(
        key=OctopusEnergySensor.LATEST_READING,
        translation_key=OctopusEnergySensor.LATEST_READING,
        value_fn=lambda _, mp: mp.meter.latest.end if mp.meter.latest else None,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OctopusEnergyMeterSensorEntityDescription(
        key=OctopusEnergySensor.CURRENT_TARIFF_RATE,
        translation_key=OctopusEnergySensor.CURRENT_TARIFF_RATE,
        value_fn=lambda _, mp: mp.tariff.current_rate.value if mp.tariff and mp.tariff.current_rate else None,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OctopusEnergyMeterSensorEntityDescription(
        key=OctopusEnergySensor.PREVIOUS_COST,
        translation_key=OctopusEnergySensor.PREVIOUS_COST,
        value_fn=lambda _, mp: mp.total_previous_cost,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
    ),
)

ELECTRICITY_METER_ENTITY_DESCRIPTIONS: tuple[OctopusEnergyMeterSensorEntityDescription, ...] = (
    OctopusEnergyMeterSensorEntityDescription(
        key=OctopusEnergySensor.PREVIOUS_CONSUMPTION,
        translation_key=OctopusEnergySensor.PREVIOUS_CONSUMPTION,
        value_fn=lambda _, mp: mp.meter.total_previous_consumption,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
)

TELEMETRY_ELECTRIC_METER_ENTITY_DESCRIPTIONS: tuple[OctopusEnergyMeterSensorEntityDescription, ...] = (
    OctopusEnergyMeterSensorEntityDescription(
        key=OctopusEnergySensor.CURRENT_USAGE,
        translation_key=OctopusEnergySensor.CURRENT_USAGE,
        value_fn=lambda _, mp: mp.meter.current_usage,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        available_fn=lambda mp: mp.meter.latest_sample is not None,
    ),
    OctopusEnergyMeterSensorEntityDescription(
        key=OctopusEnergySensor.CURRENT_COST,
        translation_key=OctopusEnergySensor.CURRENT_COST,
        value_fn=lambda _, mp: mp.total_current_cost,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        available_fn=lambda mp: mp.meter.latest_sample is not None,
    ),
    OctopusEnergyMeterSensorEntityDescription(
        key=OctopusEnergySensor.CURRENT_CONSUMPTION,
        translation_key=OctopusEnergySensor.CURRENT_CONSUMPTION,
        value_fn=lambda _, mp: mp.meter.total_current_consumption,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        available_fn=lambda mp: mp.meter.latest_sample is not None,
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: OctopusEnergyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    # validate API supports meters
    async_add_entities(
        OctopusEnergyMeterSensorEntity(
            entry.runtime_data.consumption,
            description,
            meter
        ) for meter in entry.runtime_data.consumption.account.meters
        for description in METER_ENTITY_DESCRIPTIONS
    )
    if SupplyType.ELECTRICITY in entry.runtime_data.consumption.account.supply_types:
        async_add_entities(
            OctopusEnergyMeterSensorEntity(
                entry.runtime_data.consumption,
                description,
                meter
            ) for meter in entry.runtime_data.consumption.account.meters
            for description in ELECTRICITY_METER_ENTITY_DESCRIPTIONS
        )
        for meter in entry.runtime_data.telemetry.account.meters:
            if not len(meter.smart_devices) > 0:
                continue
            async_add_entities(
                OctopusEnergyMeterSensorEntity(
                    entry.runtime_data.telemetry,
                    description,
                    meter
                ) for meter in entry.runtime_data.telemetry.account.meters
                for description in TELEMETRY_ELECTRIC_METER_ENTITY_DESCRIPTIONS
            )


class OctopusEnergyMeterSensorEntity(OctopusEnergySmartMeter, SensorEntity):
    """Defines a Octopus Energy meter sensor."""

    entity_description: OctopusEnergyMeterSensorEntityDescription
    coordinator: OctopusEnergyBaseCoordinator

    @property
    @override
    def native_value(self) -> float | datetime | None:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.account, self.meter)

    @property
    @override
    def available(self) -> bool:
        """Return entity availability."""
        if not self.entity_description.available_fn:
            return super().available
        return super().available and self.entity_description.available_fn(self.meter)
