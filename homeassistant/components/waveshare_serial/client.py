"""Connect to Waveshare adapters using their management configuration."""

from dataclasses import dataclass

from pywaveshare import (
    ConfigMode,
    WaveshareClient,
    WaveshareDeviceInfo,
    async_query_device_udp,
)


@dataclass
class WaveshareSerialData:
    """Runtime data for a Waveshare adapter."""

    client: WaveshareClient
    device_info: WaveshareDeviceInfo


async def async_connect(
    host: str, config_mode: ConfigMode | str
) -> WaveshareSerialData:
    """Read the adapter's TCP port before opening its serial connection."""
    info = await async_query_device_udp(host)
    client = WaveshareClient(host, port=info.tcp_port, config_mode=config_mode)
    try:
        await client.connect(fetch_info=False)
    except BaseException:
        await client.disconnect()
        raise
    return WaveshareSerialData(client, info)
