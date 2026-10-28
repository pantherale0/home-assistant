"""Test configuring Waveshare Serial."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant.common import MockConfigEntry
from pywaveshare import WaveshareConnectionError

from homeassistant.components.waveshare_serial.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


@pytest.mark.parametrize(
    ("mac", "port", "expected_id"),
    [
        pytest.param("AA:BB:CC:DD:EE:FF", 4196, "aabbccddeeff-4196", id="mac"),
        pytest.param("00:00:00:00:00:00", 4196, "192.0.2.1-4196", id="zero-mac"),
        pytest.param(
            "AA:BB:CC:DD:EE:FF", 5001, "aabbccddeeff-5001", id="reported-port"
        ),
    ],
)
async def test_user(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_client_constructor: MagicMock,
    mock_query_device: AsyncMock,
    user_input: dict[str, str],
    port: int,
    mac: str,
    expected_id: str,
) -> None:
    """Test manual setup and disconnecting the validation client."""
    mock_query_device.return_value.mac_address = mac
    mock_query_device.return_value.tcp_port = port
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        dict(user_input),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Serial adapter"
    assert result["data"] == {**user_input, "port": port}
    assert result["result"].unique_id == expected_id
    mock_query_device.assert_awaited_once_with("192.0.2.1")
    mock_client_constructor.assert_called_once_with(
        "192.0.2.1", port=port, config_mode="rfc2217"
    )
    mock_client.connect.assert_awaited_once_with(fetch_info=False)
    mock_client.disconnect.assert_awaited_once()
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (WaveshareConnectionError("offline"), "cannot_connect"),
        (RuntimeError("unexpected"), "unknown"),
    ],
)
async def test_connection_error(
    hass: HomeAssistant,
    mock_client: MagicMock,
    user_input: dict[str, str],
    caplog: pytest.LogCaptureFixture,
    exception: Exception,
    error: str,
) -> None:
    """Test connection errors leave the form open and release the connection."""
    mock_client.connect.side_effect = exception
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        dict(user_input),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert str(exception) in caplog.text
    mock_client.disconnect.assert_awaited_once()
    mock_client.connect.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        dict(user_input),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_duplicate(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    user_input: dict[str, str],
) -> None:
    """Reject duplicate host and port without opening another connection."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        dict(user_input),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_client.connect.assert_not_awaited()


async def test_invalid_host(
    hass: HomeAssistant,
    mock_client: MagicMock,
    user_input: dict[str, str],
) -> None:
    """Reject a URL in place of a hostname."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "http://192.0.2.1", "config_mode": "rfc2217"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"host": "invalid_host"}
    mock_client.connect.assert_not_awaited()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        dict(user_input),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_duplicate_mac(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Update the address when an existing adapter has moved."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.0.2.2", "config_mode": "rfc2217"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data["host"] == "192.0.2.2"
    mock_client.disconnect.assert_awaited_once()


async def test_no_manual_port(hass: HomeAssistant) -> None:
    """Read the TCP port from management instead of asking the user."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert "port" not in result["data_schema"].schema


async def test_raw_not_offered(hass: HomeAssistant) -> None:
    """Only offer protocols that can configure serial settings."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    mode = result["data_schema"].schema["config_mode"]
    assert "raw" not in mode.config["options"]


@pytest.mark.parametrize(
    "exception",
    [
        pytest.param(
            WaveshareConnectionError("UDP management query timed out"),
            id="management-timeout",
        ),
        pytest.param(OSError("Network unreachable"), id="network-unreachable"),
    ],
)
async def test_management_failure(
    hass: HomeAssistant,
    mock_query_device: AsyncMock,
    mock_client: MagicMock,
    user_input: dict[str, str],
    caplog: pytest.LogCaptureFixture,
    exception: Exception,
) -> None:
    """Log failed management queries and allow retry without opening a TCP connection."""
    mock_query_device.side_effect = exception
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(user_input)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert "Unable to connect to Waveshare adapter 192.0.2.1" in caplog.text
    assert str(exception) in caplog.text
    mock_client.connect.assert_not_awaited()
    mock_client.disconnect.assert_not_awaited()
    mock_query_device.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(user_input)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
