"""Test the Probe Plus integration setup."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry


async def test_migrate_probe_entity_unique_ids(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test migrating legacy probe entity unique IDs."""
    entry = MockConfigEntry(
        domain="probe_plus",
        title="FM210 aa:bb:cc:dd:ee:ff",
        unique_id="aa:bb:cc:dd:ee:ff",
        version=1,
        data={"address": "aa:bb:cc:dd:ee:ff"},
    )
    entry.add_to_hass(hass)

    entity = entity_registry.async_get_or_create(
        SENSOR_DOMAIN,
        "probe_plus",
        "aa:bb:cc:dd:ee:ff_probe_temperature",
        suggested_object_id="probe_temperature",
        config_entry=entry,
    )
    entity_registry.async_update_entity(entity.entity_id, name="My probe")

    coordinator = MagicMock(
        device=SimpleNamespace(
            connected=True,
            device_state=SimpleNamespace(probes=[]),
            mac="aa:bb:cc:dd:ee:ff",
            name="FM210 aa:bb:cc:dd:ee:ff",
        ),
        config_entry=entry,
    )
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.async_add_listener.return_value = lambda: None

    with patch(
        "homeassistant.components.probe_plus.ProbePlusDataUpdateCoordinator",
        return_value=coordinator,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    migrated = entity_registry.async_get(entity.entity_id)
    assert migrated is not None
    assert migrated.unique_id == "aa:bb:cc:dd:ee:ff_probe_1_probe_temperature"
    assert migrated.name == "My probe"
    assert entry.version == 2
    assert entry.data["model"] == "FM210"
