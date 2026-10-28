"""Test Waveshare Serial setup and port discovery."""

from unittest.mock import AsyncMock, MagicMock

from pytest_homeassistant.common import MockConfigEntry
from pywaveshare import ConnectionClosedEvent, WaveshareConnectionError

from homeassistant.components.usb import async_scan_serial_ports
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr


async def test_setup_unload(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Expose a serial port, register the adapter, and release it on unload."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    ports = await async_scan_serial_ports(hass)
    port = next(port for port in ports if port.manufacturer == "Waveshare")
    assert port.device == f"waveshare-hass://waveshare/{mock_config_entry.entry_id}/0"
    assert port.serial_number == "aabbccddeeff-4196-0"
    assert port.description == "Serial adapter (UART0)"
    device = device_registry.async_get_device_by_identifier(
        ("waveshare_serial", "aabbccddeeff-4196"), mock_config_entry.entry_id
    )
    assert device is not None
    assert device.model == "RS485 TO ETH (B)"
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    mock_client.disconnect.assert_awaited_once()
    assert port not in await async_scan_serial_ports(hass)


async def test_setup_failure(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Retry setup when the adapter is unreachable and close partial connections."""
    mock_client.connect.side_effect = WaveshareConnectionError("offline")
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_client.disconnect.assert_awaited_once()


async def test_disconnect(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reconnect through a config entry reload after losing the TCP connection."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    closed = mock_client.add_connection_closed_callback.call_args.args[0]
    mock_client.connect.reset_mock()
    closed(ConnectionClosedEvent(expected_disconnect=False))
    await hass.async_block_till_done()
    mock_client.disconnect.assert_awaited_once()
    mock_client.connect.assert_awaited_once()
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_shutdown(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Release the adapter connection when Home Assistant shuts down."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_stop()
    mock_client.disconnect.assert_awaited_once()


async def test_disconnected_ports(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """An offline adapter does not contribute usable serial ports."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    mock_client.is_connected = False
    assert not any(
        port.manufacturer == "Waveshare" for port in await async_scan_serial_ports(hass)
    )


async def test_reported_port(
    hass: HomeAssistant,
    mock_client_constructor: MagicMock,
    mock_query_device: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Read the current TCP port at setup even if the stored port is stale."""
    mock_query_device.return_value.tcp_port = 5001
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    mock_client_constructor.assert_called_once_with(
        "192.0.2.1", port=5001, config_mode="rfc2217"
    )
    assert mock_config_entry.data["port"] == 5001


async def test_management_failure(
    hass: HomeAssistant,
    mock_query_device: AsyncMock,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Retry setup if the management interface is unreachable."""
    mock_query_device.side_effect = WaveshareConnectionError(
        "UDP management query timed out"
    )
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_client.connect.assert_not_awaited()
