"""FVE Optimizer – distributes PV surplus to boilers, EV chargers and more."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import FveOptimizerCoordinator, config_structure

_LOGGER = logging.getLogger(__name__)

type FveOptimizerConfigEntry = ConfigEntry[FveOptimizerCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

STATIC_URL = f"/{DOMAIN}"
CARD_URL = f"{STATIC_URL}/fve-optimizer-card.js"
PANEL_URL = f"{STATIC_URL}/fve-optimizer-panel.js"
PANEL_PATH = "fve-optimizer"


async def _call_on_matching_entry(hass: HomeAssistant, action):
    """Run ``action(coordinator)`` on the first entry that accepts it.

    EV services raise ``ValueError`` when the charger is not on that entry;
    skip those and fail only if none matched.
    """
    errors: list[str] = []
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        try:
            return await action(entry.runtime_data)
        except ValueError as err:
            errors.append(str(err))
    raise HomeAssistantError(errors[0] if errors else "No FVE Optimizer entry loaded")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the card and register the sidebar panel shipped with the integration."""
    www = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, str(www), False)])
    await _async_register_frontend(hass)
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """(Re)register Lovelace resources; mtime busts the browser cache."""
    www = Path(__file__).parent / "www"
    version = await hass.async_add_executor_job(
        lambda: max(f.stat().st_mtime_ns for f in www.glob("*.js"))
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={version}")
    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_PATH,
            webcomponent_name="fve-optimizer-panel",
            module_url=f"{PANEL_URL}?v={version}",
            sidebar_title="FVE Optimizer",
            sidebar_icon="mdi:solar-power-variant",
            require_admin=False,
        )
    except ValueError:
        # Path already used (e.g. a dashboard with the same URL) – keep the card only.
        _LOGGER.warning(
            "Sidebar panel %s is already registered – card still available at %s",
            PANEL_PATH,
            CARD_URL,
        )

    # Services are registered once per HA start; allow adding new ones on reload.
    if not hass.services.has_service(DOMAIN, "run_review"):

        async def execute_recommendation(call: ServiceCall) -> ServiceResponse:
            """Carry out watch-only recommendations by hand (all, or one by id)."""
            done = 0
            for entry in hass.config_entries.async_loaded_entries(DOMAIN):
                done += await entry.runtime_data.async_execute_recommendation(call.data.get("id"))
            return {"executed": done}

        async def run_review(call: ServiceCall) -> ServiceResponse:
            """Run the AI review of today's decisions now."""
            reviews = []
            for entry in hass.config_entries.async_loaded_entries(DOMAIN):
                reviews.append(await entry.runtime_data.async_run_review())
            return {"reviews": reviews}

        hass.services.async_register(
            DOMAIN, "run_review", run_review, supports_response=SupportsResponse.OPTIONAL
        )
        hass.services.async_register(
            DOMAIN,
            "execute_recommendation",
            execute_recommendation,
            schema=vol.Schema({vol.Optional("id"): str}),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, "set_ev_charge_order"):

        async def set_ev_charge_order(call: ServiceCall) -> ServiceResponse:
            """One-shot: charge the EV to target SoC by the given deadline."""
            result = await _call_on_matching_entry(
                hass,
                lambda c: c.async_set_ev_charge_order(
                    target_soc=call.data["target_soc"],
                    deadline=call.data["deadline"],
                    device_id=call.data.get("device_id"),
                    name=call.data.get("name"),
                ),
            )
            return {"orders": [result]}

        async def clear_ev_charge_order(call: ServiceCall) -> ServiceResponse:
            """Cancel an active EV charge order."""
            result = await _call_on_matching_entry(
                hass,
                lambda c: c.async_clear_ev_charge_order(
                    device_id=call.data.get("device_id"),
                    name=call.data.get("name"),
                ),
            )
            return {"cleared": [result]}

        hass.services.async_register(
            DOMAIN,
            "set_ev_charge_order",
            set_ev_charge_order,
            schema=vol.Schema(
                {
                    vol.Required("target_soc"): vol.All(vol.Coerce(float), vol.Range(min=1, max=100)),
                    vol.Required("deadline"): cv.datetime,
                    vol.Optional("device_id"): str,
                    vol.Optional("name"): str,
                }
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            "clear_ev_charge_order",
            clear_ev_charge_order,
            schema=vol.Schema(
                {
                    vol.Optional("device_id"): str,
                    vol.Optional("name"): str,
                }
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, "start_ev_boost"):

        async def start_ev_boost(call: ServiceCall) -> ServiceResponse:
            """Charge flat-out from now until target SoC; returns ETA."""
            result = await _call_on_matching_entry(
                hass,
                lambda c: c.async_start_ev_boost(
                    target_soc=call.data.get("target_soc"),
                    device_id=call.data.get("device_id"),
                    name=call.data.get("name"),
                ),
            )
            return {"boosts": [result]}

        async def stop_ev_boost(call: ServiceCall) -> ServiceResponse:
            """Stop fast charging."""
            result = await _call_on_matching_entry(
                hass,
                lambda c: c.async_stop_ev_boost(
                    device_id=call.data.get("device_id"),
                    name=call.data.get("name"),
                ),
            )
            return {"stopped": [result]}

        hass.services.async_register(
            DOMAIN,
            "start_ev_boost",
            start_ev_boost,
            schema=vol.Schema(
                {
                    vol.Optional("target_soc"): vol.All(
                        vol.Coerce(float), vol.Range(min=1, max=100)
                    ),
                    vol.Optional("device_id"): str,
                    vol.Optional("name"): str,
                }
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            "stop_ev_boost",
            stop_ev_boost,
            schema=vol.Schema(
                {
                    vol.Optional("device_id"): str,
                    vol.Optional("name"): str,
                }
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )


async def async_setup_entry(hass: HomeAssistant, entry: FveOptimizerConfigEntry) -> bool:
    """Set up FVE Optimizer from a config entry."""
    # Refresh ?v= so a JS edit + entry reload picks up the new card without HA restart.
    await _async_register_frontend(hass)
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
    entry.async_on_unload(
        async_track_time_change(hass, coordinator.async_scheduled_review, second=0)
    )
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
