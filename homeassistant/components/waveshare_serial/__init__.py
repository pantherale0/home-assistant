"""The Waveshare Serial integration."""

from typing import TYPE_CHECKING

from pywaveshare import ConnectionClosedEvent, WaveshareError

from homeassistant.components.usb import (
    SerialDevice,
    async_notify_serial_ports_changed,
    async_register_serial_port_scanner,
)
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .client import async_connect
from .const import CONF_CONFIG_MODE, DOMAIN
from .coordinator import WaveshareSerialConfigEntry, WaveshareSerialCoordinator
from .serial_proxy import build_url, register_serialx_transport

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


PLATFORMS = [Platform.SENSOR]


@callback
def _async_scan_serial_ports(hass: HomeAssistant) -> list[SerialDevice]:
    """Return ports exposed by connected Waveshare adapters."""
    ports: list[SerialDevice] = []
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        data = entry.runtime_data
        if not data.client.is_connected:
            continue
        ports.extend(
            SerialDevice(
                device=str(build_url(entry.entry_id, proxy.instance)),
                serial_number=f"{entry.unique_id}-{proxy.instance}",
                manufacturer="Waveshare",
                description=f"{data.device_info.name} ({proxy.name})",
                interface_description=proxy.port_type,
            )
            for proxy in data.device_info.serial_proxies
        )
    return ports


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register Waveshare serial ports and the serialx transport."""
    unregister_scanner = async_register_serial_port_scanner(
        hass, _async_scan_serial_ports
    )
    unregister_transport = register_serialx_transport(hass.loop)

    @callback
    def async_stop(event: Event) -> None:
        """Remove the serial port scanner and transport."""
        unregister_scanner()
        unregister_transport()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: WaveshareSerialConfigEntry
) -> None:
    """Connect to a Waveshare adapter and expose its serial ports."""
    try:
        data = await async_connect(entry.data[CONF_HOST], entry.data[CONF_CONFIG_MODE])
    except (WaveshareError, OSError) as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = WaveshareSerialCoordinator(hass, entry, data)
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        await data.client.disconnect()
        raise
    entry.runtime_data = coordinator
    client = data.client
    info = data.device_info
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_PORT: info.tcp_port}
    )
    if TYPE_CHECKING:
        assert entry.unique_id is not None
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id)},
        manufacturer="Waveshare",
        model=info.model,
        name=info.name,
        sw_version=info.firmware_version or None,
    )

    @callback
    def async_connection_closed(event: ConnectionClosedEvent) -> None:
        """Reload after an unexpected disconnect to reconnect and refresh ports."""
        if not event.expected_disconnect:
            async_notify_serial_ports_changed(hass)
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(
        client.add_connection_closed_callback(async_connection_closed)
    )

    async def async_stop_entry(event: Event) -> None:
        """Close the connection when Home Assistant stops."""
        await client.disconnect()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop_entry)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_notify_serial_ports_changed(hass)


async def async_unload_entry(
    hass: HomeAssistant, entry: WaveshareSerialConfigEntry
) -> None:
    """Disconnect the adapter and remove its ports."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
    await entry.runtime_data.client.disconnect()
    async_notify_serial_ports_changed(hass)
