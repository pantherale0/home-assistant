"""Diagnostic sensors for Waveshare serial adapters."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from pywaveshare import WaveshareDeviceState

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WaveshareSerialConfigEntry, WaveshareSerialCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class WaveshareSensorEntityDescription(SensorEntityDescription):
    """Describe a Waveshare diagnostic value."""

    value_fn: Callable[[WaveshareDeviceState], int]


SENSORS: tuple[WaveshareSensorEntityDescription, ...] = (
    WaveshareSensorEntityDescription(
        key="tx_bytes",
        translation_key="tx_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda state: state.txd_bytes,
    ),
    WaveshareSensorEntityDescription(
        key="rx_bytes",
        translation_key="rx_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda state: state.rxd_bytes,
    ),
    WaveshareSensorEntityDescription(
        key="baud_rate",
        translation_key="baud_rate",
        native_unit_of_measurement="Bd",
        value_fn=lambda state: state.serial_config.baudrate,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WaveshareSerialConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add diagnostic sensors for the adapter."""
    async_add_entities(WaveshareSensor(entry, description) for description in SENSORS)


class WaveshareSensor(CoordinatorEntity[WaveshareSerialCoordinator], SensorEntity):
    """A diagnostic sensor attached to the serial adapter device."""

    entity_description: WaveshareSensorEntityDescription
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry: WaveshareSerialConfigEntry,
        description: WaveshareSensorEntityDescription,
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(entry.runtime_data)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        if TYPE_CHECKING:
            assert entry.unique_id is not None
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.unique_id)})

    @property
    @override
    def native_value(self) -> int:
        """Return the latest value read from the adapter."""
        return self.entity_description.value_fn(self.coordinator.data)
