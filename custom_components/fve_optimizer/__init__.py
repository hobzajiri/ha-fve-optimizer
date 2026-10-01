"""FVE Optimizer – distributes PV surplus to boilers, EV chargers and more."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import FveOptimizerCoordinator, config_structure

type FveOptimizerConfigEntry = ConfigEntry[FveOptimizerCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_URL = f"/{DOMAIN}/fve-optimizer-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the Lovelace card shipped with the integration."""
    card = Path(__file__).parent / "www" / "fve-optimizer-card.js"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), False)])
    # The file's mtime busts the browser cache after an update.
    version = await hass.async_add_executor_job(lambda: card.stat().st_mtime_ns)
    add_extra_js_url(hass, f"{CARD_URL}?v={version}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FveOptimizerConfigEntry) -> bool:
    """Set up FVE Optimizer from a config entry."""
    coordinator = FveOptimizerCoordinator(hass, entry)
    entry.runtime_data = coordinator
    # Register the hub first so device entities can link to it by id.
    hub = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="FVE Optimizer",
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    coordinator.hub_device_id = hub.id
    await coordinator.hdo.async_load()
    await coordinator.async_load_state()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # First cycle runs after the switch entities restored their states.
    await coordinator.async_refresh()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FveOptimizerConfigEntry) -> bool:
    """Unload a config entry and hand control back (export limit, loads)."""
    await entry.runtime_data.async_release_all()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: FveOptimizerConfigEntry) -> None:
    """Apply tunables in place; reload only when entities or devices change."""
    coordinator = entry.runtime_data
    if config_structure(entry) != coordinator.structure:
        await hass.config_entries.async_reload(entry.entry_id)
        return
    coordinator.apply_config(entry)
    await coordinator.async_refresh()
