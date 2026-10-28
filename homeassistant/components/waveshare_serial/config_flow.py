"""Config flow for the Waveshare Serial integration."""

import logging
from typing import Any, override

import probatio
from pywaveshare import ConfigMode, WaveshareError

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import selector
from homeassistant.util.network import is_host_valid

from .client import async_connect
from .const import CONF_CONFIG_MODE, DOMAIN

_LOGGER = logging.getLogger(__name__)


class WaveshareSerialConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Waveshare Serial."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate the adapter and create its config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip().lower()
            user_input[CONF_HOST] = host
            self._async_abort_entries_match({CONF_HOST: host})
            if not is_host_valid(host):
                errors[CONF_HOST] = "invalid_host"
            else:
                try:
                    data = await async_connect(host, user_input[CONF_CONFIG_MODE])
                except (WaveshareError, OSError) as err:
                    _LOGGER.warning(
                        "Unable to connect to Waveshare adapter %s: %s",
                        host,
                        err,
                        exc_info=True,
                    )
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception(
                        "Unexpected exception connecting to Waveshare adapter"
                    )
                    errors["base"] = "unknown"
                else:
                    await data.client.disconnect()
                    info = data.device_info
                    mac = info.mac_address.replace(":", "").lower()
                    identity = mac if mac != "000000000000" else host
                    await self.async_set_unique_id(f"{identity}-{info.tcp_port}")
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                    return self.async_create_entry(
                        title=info.name,
                        data={**user_input, CONF_PORT: info.tcp_port},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(
                    {
                        probatio.Required(CONF_HOST): str,
                        probatio.Required(
                            CONF_CONFIG_MODE, default=ConfigMode.RFC2217
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    mode
                                    for mode in ConfigMode
                                    if mode is not ConfigMode.RAW
                                ],
                                translation_key="config_mode",
                            )
                        ),
                    }
                ),
                user_input,
            ),
            errors=errors,
        )
