"""The Probe Plus integration."""

from homeassistant.const import CONF_MODEL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntry

from .coordinator import ProbePlusConfigEntry, ProbePlusDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_migrate_entry(hass: HomeAssistant, entry: ProbePlusConfigEntry) -> bool:
    """Migrate a Probe Plus config entry."""
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_MODEL: entry.data.get(CONF_MODEL, entry.title.split(" ")[0]),
            },
            version=2,
        )

        mac = entry.unique_id
        if mac is None:
            return True
        legacy_keys = {
            "probe_temperature",
            "probe_battery",
            "probe_rssi",
            "probe_voltage",
        }

        def migrate_entity(entity: RegistryEntry) -> dict[str, str] | None:
            """Migrate legacy probe entity unique IDs."""
            if entity.unique_id == mac or not entity.unique_id.startswith(f"{mac}_"):
                return None
            key = entity.unique_id.removeprefix(f"{mac}_")
            if key not in legacy_keys:
                return None
            return {"new_unique_id": f"{mac}_probe_1_{key}"}

        await er.async_migrate_entries(hass, entry.entry_id, migrate_entity)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ProbePlusConfigEntry) -> bool:
    """Set up Probe Plus from a config entry."""
    coordinator = ProbePlusDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ProbePlusConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
