"""Test Waveshare diagnostic sensors."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
from pywaveshare import (
    WaveshareConnectionError,
    WaveshareDeviceState,
    WaveshareSerialConfig,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er


async def test_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Attach diagnostic sensors to the existing adapter device."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)
    device = device_registry.async_get_device_by_identifier(
        ("waveshare_serial", "aabbccddeeff-4196"), mock_config_entry.entry_id
    )
    assert device is not None
    assert {
        entry.device_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
    } == {device.id}


async def test_polling(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    mock_query_device: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Refresh all sensors together without sending serial configuration commands."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    mock_query_device.return_value = replace(
        mock_query_device.return_value,
        state=WaveshareDeviceState(
            txd_bytes=4096,
            rxd_bytes=8192,
            serial_config=WaveshareSerialConfig(baudrate=9600),
        ),
    )
    mock_query_device.reset_mock()
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.serial_adapter_bytes_transmitted").state == "4096"
    assert hass.states.get("sensor.serial_adapter_bytes_received").state == "8192"
    assert hass.states.get("sensor.serial_adapter_baud_rate").state == "9600"
    mock_query_device.assert_awaited_once_with("192.0.2.1")
    mock_client.serial_proxy_write.assert_not_called()
    mock_client.serial_proxy_configure.assert_not_awaited()
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    mock_query_device.reset_mock()
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    mock_query_device.assert_not_awaited()


@pytest.mark.parametrize(
    "exception",
    [
        pytest.param(WaveshareConnectionError("UDP timeout"), id="library-error"),
        pytest.param(OSError("Network unreachable"), id="network-error"),
    ],
)
async def test_unavailable_and_recovery(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_query_device: AsyncMock,
    freezer: FrozenDateTimeFactory,
    exception: Exception,
) -> None:
    """Show diagnostics as unavailable after a failed query and recover on success."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    mock_query_device.side_effect = exception
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.serial_adapter_bytes_transmitted").state
        == STATE_UNAVAILABLE
    )
    assert (
        hass.states.get("sensor.serial_adapter_bytes_received").state
        == STATE_UNAVAILABLE
    )
    assert hass.states.get("sensor.serial_adapter_baud_rate").state == STATE_UNAVAILABLE
    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_query_device.side_effect = None
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.serial_adapter_bytes_transmitted").state == "1024"
    assert hass.states.get("sensor.serial_adapter_bytes_received").state == "2048"
    assert hass.states.get("sensor.serial_adapter_baud_rate").state == "115200"


async def test_missing_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_query_device: AsyncMock,
) -> None:
    """Retry initial setup if the management response has no diagnostic state."""
    mock_query_device.return_value.state = None
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
