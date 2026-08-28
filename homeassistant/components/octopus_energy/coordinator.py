"""Data update coordinators for the Octopus Energy integration."""

from abc import abstractmethod
import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import override

from pykrakentech import AuthenticationError, KrakenError, RateLimitError
from pykrakentech.models import Account, ConsumptionGrouping, TelemetryGrouping

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_TELEMETRY_UPDATE_INTERVAL = timedelta(seconds=30)
_CONSUMPTION_UPDATE_INTERVAL = timedelta(hours=1)
_CONSUMPTION_LOOKBACK = timedelta(days=4)


@dataclass(frozen=True, slots=True)
class OctopusEnergyCoordinators:
	"""Octopus Energy data update coordinators."""

	telemetry: OctopusEnergyTelemetryDataUpdateCoordinator
	consumption: OctopusEnergyConsumptionDataUpdateCoordinator


type OctopusEnergyConfigEntry = ConfigEntry[OctopusEnergyCoordinators]


class OctopusEnergyBaseCoordinator(DataUpdateCoordinator):
	"""Base coordinator for Octopus Energy endpoints."""

	config_entry: OctopusEnergyConfigEntry

	def __init__(
		self,
		hass: HomeAssistant,
		config_entry: OctopusEnergyConfigEntry,
		account: Account,
	) -> None:
		"""Initialize the coordinator."""
		super().__init__(
			hass,
			_LOGGER,
			config_entry=config_entry,
			name=DOMAIN,
			update_interval=self._update_interval,
		)
		self.account = account
		self._first_refresh: bool = True
		self._consecutive_refresh_failures: int = 0

	@abstractmethod
	async def update_data(self) -> None:
		"""Fetch data from an Octopus Energy endpoint."""

	@override
	async def _async_update_data(self) -> None:
		"""Fetch data and translate API failures into coordinator failures."""
		if self._consecutive_refresh_failures > 5:
			self.update_interval = (
				self._update_interval+timedelta(minutes=10)
			)
		else:
			self.update_interval = self._update_interval
		await self.update_data()

	async def _async_call_endpoint[
		_EndpointT
	](
		self,
		endpoint: Awaitable[_EndpointT],
		*,
		endpoint_name: str,
		default: _EndpointT | None = None,
	) -> _EndpointT:
		"""Call an endpoint while allowing other endpoints to update."""
		try:
			data = await endpoint
		except AuthenticationError as err:
			raise ConfigEntryAuthFailed from err
		except RateLimitError as err:
			self._consecutive_refresh_failures += 1
			if self._first_refresh:
				raise
			raise UpdateFailed(retry_after=120) from err
		except KrakenError as err:
			self._consecutive_refresh_failures += 1
			_LOGGER.exception("Failed to update %s endpoint", endpoint_name)
			raise UpdateFailed from err
		else:
			self._first_refresh = False
			return data


class OctopusEnergyTelemetryDataUpdateCoordinator(
	OctopusEnergyBaseCoordinator
):
	"""Poll smart-meter telemetry for an account."""

	_update_interval = _TELEMETRY_UPDATE_INTERVAL

	@override
	async def update_data(self) -> None:
		"""Fetch the latest smart-meter telemetry."""
		data = await self._async_call_endpoint(
			self.account.get_telemetry(
				end=dt_util.utcnow(),
				start=dt_util.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
				grouping=TelemetryGrouping.TEN_SECONDS
			),
			endpoint_name="telemetry",
			default=(),
		)
		self.update_interval = (
			_TELEMETRY_UPDATE_INTERVAL
			if any(meter.latest_sample for meter in data)
			else timedelta(minutes=30)
		)


class OctopusEnergyConsumptionDataUpdateCoordinator(
	OctopusEnergyBaseCoordinator
):
	"""Poll consumption intervals and tariff information for an account."""

	_update_interval = _CONSUMPTION_UPDATE_INTERVAL

	@override
	async def update_data(self) -> None:
		"""Fetch recent consumption and current tariff information."""
		await asyncio.gather(
			self._async_call_endpoint(
				self.account.get_consumption(
					start_at=dt_util.now() - _CONSUMPTION_LOOKBACK,
					grouping=ConsumptionGrouping.HALF_HOUR,
				),
				endpoint_name="consumption"
			),
			self._async_call_endpoint(
				self.account.get_agreements(),
				endpoint_name="agreements"
			),
		)
