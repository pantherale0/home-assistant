"""Fixtures for Waveshare Serial tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry
from pywaveshare import (
    ConfigMode,
    SerialProxyInfo,
    WaveshareDeviceInfo,
    WaveshareDeviceState,
)

from homeassistant.components.waveshare_serial.const import CONF_CONFIG_MODE, DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT


@pytest.fixture
def mock_client_constructor() -> Generator[MagicMock]:
    """Mock the library client constructor."""
    with patch(
        "homeassistant.components.waveshare_serial.client.WaveshareClient",
        autospec=True,
    ) as constructor:
        yield constructor


@pytest.fixture
def mock_client(mock_client_constructor: MagicMock) -> MagicMock:
    """Mock communication with a Waveshare adapter."""
    client = mock_client_constructor.return_value
    client.is_connected = True
    client.serial_proxy_write = Mock()
    client.add_connection_closed_callback = Mock(return_value=Mock())
    client.subscribe_serial_proxy_data = Mock(return_value=Mock())
    client.device_info.return_value = WaveshareDeviceInfo(
        name="Serial adapter",
        mac_address="AA:BB:CC:DD:EE:FF",
        device_id=bytes.fromhex("aabbccddeeff"),
        ip_address="192.0.2.1",
        model="RS485 TO ETH (B)",
        firmware_version="1.0",
        serial_proxies=[SerialProxyInfo(name="UART0", instance=0)],
        state=WaveshareDeviceState(txd_bytes=1024, rxd_bytes=2048),
    )
    return client


@pytest.fixture
def user_input() -> dict[str, str]:
    """Return the fields supplied by a user configuring an adapter."""
    return {CONF_HOST: "192.0.2.1", CONF_CONFIG_MODE: ConfigMode.RFC2217}


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a Waveshare config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Serial adapter",
        unique_id="aabbccddeeff-4196",
        data={
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 4196,
            CONF_CONFIG_MODE: ConfigMode.RFC2217,
        },
    )


@pytest.fixture(autouse=True)
def mock_query_device(mock_client: MagicMock) -> Generator[AsyncMock]:
    """Mock reading the adapter's UDP management configuration."""
    with (
        patch(
            "homeassistant.components.waveshare_serial.client.async_query_device_udp",
            return_value=mock_client.device_info.return_value,
        ) as query,
        patch(
            "homeassistant.components.waveshare_serial.coordinator.async_query_device_udp",
            new=query,
        ),
    ):
        yield query


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Keep config flow tests separate from config entry setup."""
    with patch(
        "homeassistant.components.waveshare_serial.async_setup_entry",
        return_value=None,
    ) as setup:
        yield setup
