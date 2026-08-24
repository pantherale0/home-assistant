"""Common fixtures for the Probe Plus tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

from pyprobeplus.parser import ProbePlusData, ProbeReading
import pytest

from homeassistant.components.probe_plus.const import DOMAIN
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.probe_plus.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        title="FM210 aa:bb:cc:dd:ee:ff",
        domain=DOMAIN,
        version=1,
        data={
            CONF_ADDRESS: "aa:bb:cc:dd:ee:ff",
        },
        unique_id="aa:bb:cc:dd:ee:ff",
    )


@pytest.fixture
def mock_probe_plus() -> MagicMock:
    """Mock the Probe Plus device."""
    with patch(
        "homeassistant.components.probe_plus.coordinator.ProbePlusDevice",
        autospec=True,
    ) as mock_device:
        device = mock_device.return_value
        device.connected = True
        device.name = "FM210 aa:bb:cc:dd:ee:ff"
        device.device_state = ProbePlusData(
            probes=[ProbeReading(channel=0, temperature=25.0, rssi=200, voltage=3.7)],
            relay_status=1,
            relay_voltage=9.0,
            relay_battery_thresholds=(3.87, 3.7, 3.6),
        )
        yield device
