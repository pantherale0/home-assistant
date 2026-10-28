"""Test serialx connections through a configured Waveshare proxy."""

import asyncio
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant.common import MockConfigEntry
from pywaveshare import (
    InvalidSettingsError,
    SerialProxyDataReceived,
    SerialProxyRequestResponse,
)
import serialx

from homeassistant.components.waveshare_serial.serial_proxy import build_url
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.setup import async_setup_component


async def test_serial_transport(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Send and receive literal bytes through serialx using the configured client."""
    mock_client.loop = hass.loop
    mock_client.serial_proxy_subscribe_await_response.return_value = (
        SerialProxyRequestResponse(instance=0)
    )
    mock_client.serial_proxy_configure_await_response.return_value = (
        SerialProxyRequestResponse(instance=0)
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    reader, writer = await serialx.open_serial_connection(
        url=str(build_url(mock_config_entry.entry_id, 0)), baudrate=9600
    )
    writer.write(b"\x01\x03\xff")
    mock_client.serial_proxy_write.assert_called_once_with(
        instance=0, data=b"\x01\x03\xff"
    )
    receive = mock_client.subscribe_serial_proxy_data.call_args.args[0]
    receive(SerialProxyDataReceived(instance=0, data=b"\x04\x05\xff"))
    assert await asyncio.wait_for(reader.readexactly(3), 1) == b"\x04\x05\xff"
    writer.close()
    await writer.wait_closed()
    mock_client.disconnect.assert_not_awaited()
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    mock_client.disconnect.assert_awaited_once()


@pytest.mark.parametrize(
    "url",
    [
        "waveshare-hass://waveshare/",
        "waveshare-hass://waveshare/missing/0",
        "waveshare-hass://waveshare/missing/abc",
    ],
)
async def test_invalid_url(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, url: str
) -> None:
    """Reject malformed URLs and missing config entries."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    with pytest.raises(InvalidSettingsError):
        await serialx.open_serial_connection(url=url, baudrate=9600)


async def test_worker_thread(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Resolve the HA client when a synchronous consumer owns another event loop."""
    mock_client.loop = hass.loop
    mock_client.serial_proxy_subscribe_await_response.return_value = (
        SerialProxyRequestResponse(instance=0)
    )
    mock_client.serial_proxy_configure_await_response.return_value = (
        SerialProxyRequestResponse(instance=0)
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)

    def send_bytes() -> None:
        port = serialx.serial_for_url(
            str(build_url(mock_config_entry.entry_id, 0)), baudrate=19200
        )
        port.open()
        try:
            assert port.write(b"\x01\xff\x03") == 3
        finally:
            port.close()

    await hass.async_add_executor_job(send_bytes)
    await hass.async_block_till_done()
    mock_client.serial_proxy_write.assert_called_once_with(
        instance=0, data=b"\x01\xff\x03"
    )
    mock_client.disconnect.assert_not_awaited()


async def test_unloaded_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Consumers retry while their adapter's config entry is not loaded."""
    assert await async_setup_component(hass, "waveshare_serial", {})
    mock_config_entry.add_to_hass(hass)
    with pytest.raises(ConfigEntryNotReady):
        await serialx.open_serial_connection(
            url=str(build_url(mock_config_entry.entry_id, 0)), baudrate=9600
        )
