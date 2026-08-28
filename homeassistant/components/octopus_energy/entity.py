"""Represent an Octopus Energy entity."""

from pykrakentech.features import SupplyType
from pykrakentech.models.meters import Meter, MeterPoint

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OctopusEnergyBaseCoordinator

SUPPLY_TYPE_MAPPING: dict[SupplyType, str] = {
	SupplyType.ELECTRICITY: "Electricity",
	SupplyType.GAS: "Gas",
	SupplyType.WATER: "Water"
}

class OctopusEnergyBaseEntity(CoordinatorEntity[OctopusEnergyBaseCoordinator]):
	"""Base entity for Octopus Energy coordinator entities."""

	_attr_has_entity_name = True

	def __init__(self, coordinator: OctopusEnergyBaseCoordinator, description: EntityDescription) -> None:
		"""Initialize an Octopus Energy entity."""
		super().__init__(coordinator)
		self.entity_description = description
		self._attr_unique_id = (
			f"{coordinator.config_entry.entry_id}_{coordinator.account.id}_{description.key}"
		)

class OctopusEnergySmartMeter(OctopusEnergyBaseEntity):
	"""Represent a Smart energy meter device."""

	def __init__(
		self,
		coordinator: OctopusEnergyBaseCoordinator,
		description: EntityDescription,
		meter: Meter,
	) -> None:
		"""Init a meter point."""
		super().__init__(coordinator, description)
		self.meter_identifier = meter.identifier
		self.direction = "import" if not meter.direction else meter.direction
		self._attr_unique_id = (
			f"{coordinator.config_entry.entry_id}_{coordinator.account.id}_{meter.id}_{self.direction}_{description.key}"
		)

	@property
	def meter(self) -> MeterPoint:
		"""Return the MeterPoint."""
		return self.coordinator.account.get_meter_point(identifier=self.meter_identifier)

	@property
	def device_info(self) -> DeviceInfo:
		"""Return information about the Octopus Energy account device."""
		return DeviceInfo(
			identifiers={
				(DOMAIN, f"{self.coordinator.account.id}_{self.meter.meter.id}_{self.direction}")
			},
			manufacturer=self.meter.meter.manufacturer,
			model=self.meter.meter.model,
			serial_number=self.meter.meter.serial_number,
			translation_key="meter",
			translation_placeholders={
				"direction": self.direction.capitalize(),
				"fuel_type": SUPPLY_TYPE_MAPPING[self.meter.supply_type]}
		)
