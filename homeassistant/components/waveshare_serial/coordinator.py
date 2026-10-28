"""Coordinate Waveshare diagnostic state updates."""

from datetime import timedelta
import logging
from typing import override

from pywaveshare import WaveshareDeviceState, WaveshareError, async_query_device_udp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import WaveshareSerialData
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type WaveshareSerialConfigEntry = ConfigEntry[WaveshareSerialCoordinator]


class WaveshareSerialCoordinator(DataUpdateCoordinator[WaveshareDeviceState]):
    """Read device counters and serial settings through UDP management."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WaveshareSerialConfigEntry,
        connection: WaveshareSerialData,
    ) -> None:
        """Initialize the shared diagnostic poller."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
            always_update=False,
        )
        self.client = connection.client
        self.device_info = connection.device_info
        self._host: str = entry.data[CONF_HOST]

    @override
    async def _async_update_data(self) -> WaveshareDeviceState:
        try:
            info = await async_query_device_udp(self._host)
        except (WaveshareError, OSError) as err:
            raise UpdateFailed(f"Unable to read adapter diagnostics: {err}") from err
        if info.state is None:
            raise UpdateFailed("Adapter did not return diagnostic state")
        return info.state
