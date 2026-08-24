"""Test the Probe Plus sensors."""

from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from pyprobeplus.parser import ProbePlusData, ProbeReading

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry


async def test_probe_entities_are_discovered(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test probe entities are added when probe readings are discovered."""
    entry = MockConfigEntry(domain="probe_plus")
    device = SimpleNamespace(
        connected=True,
        device_state=ProbePlusData(
            relay_battery_thresholds=(3.87, 3.7, 3.6),
            probes=[ProbeReading(channel=0, temperature=25.0)],
        ),
        mac="aa:bb:cc:dd:ee:ff",
        name="FM210 aa:bb:cc:dd:ee:ff",
    )
    coordinator = MagicMock(device=device, config_entry=entry)
    listeners: list[Callable[[], None]] = []

    def add_listener(
        listener: Callable[[], None], context: str | None = None
    ) -> Callable[[], None]:
        listeners.append(listener)
        return lambda: None

    coordinator.async_add_listener.side_effect = add_listener
    coordinator.async_config_entry_first_refresh = AsyncMock()
    device.name = "FM210 aa:bb:cc:dd:ee:ff"
    device.connected = True

    with patch(
        "homeassistant.components.probe_plus.ProbePlusDataUpdateCoordinator",
        return_value=coordinator,
    ):
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entities = entity_registry.entities.get_entries_for_config_entry_id(entry.entry_id)
    assert len(entities) == 6
    probe_unique_ids = {
        entity.unique_id
        for entity in entities
        if entity.unique_id.startswith("aa:bb:cc:dd:ee:ff_probe_1_")
    }
    assert probe_unique_ids == {
        "aa:bb:cc:dd:ee:ff_probe_1_probe_temperature",
        "aa:bb:cc:dd:ee:ff_probe_1_probe_battery",
        "aa:bb:cc:dd:ee:ff_probe_1_probe_rssi",
        "aa:bb:cc:dd:ee:ff_probe_1_probe_voltage",
    }

    device.device_state.probes.append(ProbeReading(channel=1, temperature=26.0))
    for listener in listeners:
        listener()
    await hass.async_block_till_done()

    assert (
        len(entity_registry.entities.get_entries_for_config_entry_id(entry.entry_id))
        == 10
    )
