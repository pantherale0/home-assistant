"""The Octopus Energy integration."""

import asyncio
import contextlib

from pykrakentech import ConfigurationError, KrakenClient, KrakenError, NotFoundError, RateLimitError

from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_KEY,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ACCOUNT_ID
from .coordinator import (
    OctopusEnergyConfigEntry,
    OctopusEnergyConsumptionDataUpdateCoordinator,
    OctopusEnergyCoordinators,
    OctopusEnergyTelemetryDataUpdateCoordinator,
)

_PLATFORMS: list[Platform] = [Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: OctopusEnergyConfigEntry) -> bool:
    """Set up Octopus Energy from a config entry."""

    try:
        entry.runtime_data = client = KrakenClient(
            provider="octopus_uk",
            api_key=entry.data.get(CONF_API_KEY),
            refresh_token=entry.data.get(CONF_ACCESS_TOKEN),
            email=entry.data.get(CONF_USERNAME),
            password=entry.data.get(CONF_PASSWORD),
            session=async_get_clientsession(hass),
        )
    except ConfigurationError as err:
        raise ConfigEntryAuthFailed("Invalid credentials") from err

    try:
        await client.connect()
        account = await client.get_account(entry.data[CONF_ACCOUNT_ID])
    except NotFoundError as err:
        raise ConfigEntryAuthFailed from err
    except KrakenError as err:
        raise ConfigEntryNotReady from err

    telemetry = OctopusEnergyTelemetryDataUpdateCoordinator(hass, entry, account)
    consumption = OctopusEnergyConsumptionDataUpdateCoordinator(hass, entry, account)
    with contextlib.suppress(RateLimitError):
        await asyncio.gather(
            telemetry.async_config_entry_first_refresh(),
            consumption.async_config_entry_first_refresh(),
        )
    entry.runtime_data = OctopusEnergyCoordinators(telemetry, consumption)

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: OctopusEnergyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
