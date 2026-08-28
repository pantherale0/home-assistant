"""Config flow for the Octopus Energy integration."""

import logging
from typing import Any

from pykrakentech import KrakenClient, KrakenError
from pykrakentech.features import Feature
from pykrakentech.models.account import Account
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_KEY,
    CONF_REGION,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_ACCOUNT_ID,
    CONF_USE_API_KEY,
    DOMAIN,
    SUPPORTED_REGIONS,
)

_LOGGER = logging.getLogger(__name__)

AUTH_METHOD_API_KEY = "api_key"
AUTH_METHOD_CREDENTIALS = "credentials"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default="uk"): SelectSelector(
            SelectSelectorConfig(
                options=[SelectOptionDict(value=x, label=y) for x, y in SUPPORTED_REGIONS.items()],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required("auth_method", default=AUTH_METHOD_API_KEY): SelectSelector(
            SelectSelectorConfig(
                options=[AUTH_METHOD_API_KEY, AUTH_METHOD_CREDENTIALS],
                translation_key="auth_method",
            )
        )
    }
)

STEP_API_KEY_DATA_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})
STEP_CREDENTIALS_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class OctopusEnergyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Octopus Energy."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.client: KrakenClient | None = None
        self.accounts: tuple[Account, ...] = ()
        self.user_data: dict[str, Any] = {}

    def _build_entry_data(self, account_id: str) -> dict[str, Any]:
        """Build the data for the config entry."""
        entry_data: dict[str, Any] = {
            CONF_ACCOUNT_ID: account_id,
            CONF_REGION: self.user_data[CONF_REGION]
        }
        if Feature.AUTH_REFRESH_TOKEN in self.client.capabilities:
            entry_data[CONF_ACCESS_TOKEN] = self.client.authenticator.refresh_token
        if Feature.AUTH_EMAIL_PASSWORD in self.client.capabilities:
            entry_data[CONF_USERNAME] = self.user_data[CONF_USERNAME]
            entry_data[CONF_PASSWORD] = self.user_data[CONF_PASSWORD]
        if Feature.AUTH_API_KEY in self.client.capabilities and self.user_data.get(CONF_API_KEY):
            entry_data[CONF_USE_API_KEY] = True
            entry_data[CONF_API_KEY] = self.user_data[CONF_API_KEY]
        return entry_data

    async def _async_connect(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Connect to Kraken and retrieve the user's accounts."""
        self.user_data.update(user_input)
        self.client = KrakenClient(
            provider=f"octopus_{self.user_data[CONF_REGION]}",
            email=user_input.get(CONF_USERNAME),
            password=user_input.get(CONF_PASSWORD),
            api_key=user_input.get(CONF_API_KEY),
            session=async_get_clientsession(self.hass),
        )
        try:
            await self.client.connect()
            self.accounts = await self.client.list_accounts()
        except KrakenError:
            return {"base": "invalid_auth"}
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return {"base": "unknown"}
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            self.user_data[CONF_REGION] = user_input[CONF_REGION]
            if user_input["auth_method"] == AUTH_METHOD_API_KEY:
                return await self.async_step_api_key()
            return await self.async_step_credentials()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle API key authentication."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_connect(user_input)
            if not errors:
                return await self.async_step_user_select_account()
        return self.async_show_form(
            step_id="api_key", data_schema=STEP_API_KEY_DATA_SCHEMA, errors=errors
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle username and password authentication."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_connect(user_input)
            if not errors:
                return await self.async_step_user_select_account()
        return self.async_show_form(
            step_id="credentials",
            data_schema=STEP_CREDENTIALS_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_user_select_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the account selection step."""
        if len(self.accounts) > 1:
            if user_input is not None:
                await self.async_set_unique_id(user_input[CONF_ACCOUNT_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_ACCOUNT_ID], data=self._build_entry_data(user_input[CONF_ACCOUNT_ID])
                )
            return self.async_show_form(
                step_id="user_select_account",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_ACCOUNT_ID): vol.In(
                            {account.id: account.number for account in self.accounts}
                        )
                    }
                ),
            )
        if len(self.accounts) == 1:
            await self.async_set_unique_id(self.accounts[0].id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self.accounts[0].number, data=self._build_entry_data(self.accounts[0].number))
        return self.async_abort(reason="no_accounts_found")
