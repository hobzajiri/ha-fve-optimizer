"""Notifications and domain events for FVE Optimizer.

Events always fire (for user automations). Push / persistent notifications
are optional and gated by config toggles.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_NOTIFY_SERVICE,
    CONF_PERSISTENT_NOTIFICATION,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import FveOptimizerCoordinator

_LOGGER = logging.getLogger(__name__)

# Event types: hass.bus fires ``fve_optimizer_<name>``.
EVENT_REVIEW_DONE = "review_done"
EVENT_OUTLOOK_CHECK = "outlook_check"
EVENT_FAILSAFE = "failsafe"
EVENT_FAILSAFE_CLEARED = "failsafe_cleared"
EVENT_DEADLINE_RISK = "deadline_risk"
EVENT_BOOST = "boost"
EVENT_CHARGE_ORDER = "charge_order"


def _cs(hass: HomeAssistant) -> bool:
    return (hass.config.language or "").startswith("cs")


def notify_service_name(conf: dict[str, Any]) -> str | None:
    """Return the notify service name (without domain), or None."""
    raw = str(conf.get(CONF_NOTIFY_SERVICE) or "").strip()
    if not raw:
        return None
    if raw.startswith("notify."):
        return raw.split(".", 1)[1] or None
    return raw


def fire_event(
    hass: HomeAssistant,
    coordinator: FveOptimizerCoordinator,
    name: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Fire ``fve_optimizer_<name>`` with entry context."""
    payload = {
        "entry_id": coordinator.config_entry.entry_id,
        "entry_title": coordinator.config_entry.title,
        **(data or {}),
    }
    hass.bus.async_fire(f"{DOMAIN}_{name}", payload)


async def async_notify(
    hass: HomeAssistant,
    coordinator: FveOptimizerCoordinator,
    *,
    title: str,
    message: str,
    notification_id: str | None = None,
    enabled: bool = True,
) -> None:
    """Send optional notify.* and/or persistent_notification."""
    if not enabled:
        return
    conf = coordinator.conf
    if conf.get(CONF_PERSISTENT_NOTIFICATION) and notification_id:
        try:
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": title,
                    "message": message,
                    "notification_id": f"{DOMAIN}_{notification_id}",
                },
                blocking=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("persistent_notification failed")
    service = notify_service_name(conf)
    if service:
        try:
            await hass.services.async_call(
                "notify",
                service,
                {"title": title, "message": message},
                blocking=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("notify.%s failed", service)


async def async_dismiss(
    hass: HomeAssistant, coordinator: FveOptimizerCoordinator, notification_id: str
) -> None:
    """Dismiss a persistent notification created by this integration."""
    if not coordinator.conf.get(CONF_PERSISTENT_NOTIFICATION):
        return
    try:
        await hass.services.async_call(
            "persistent_notification",
            "dismiss",
            {"notification_id": f"{DOMAIN}_{notification_id}"},
            blocking=True,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("dismiss %s failed", notification_id, exc_info=True)


def review_should_notify(review: dict[str, Any], max_score: float) -> bool:
    """True when the review score is low or there are real suggestions."""
    try:
        score = float(review.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    if score <= max_score:
        return True
    suggestions = str(review.get("suggestions") or "").strip().lower()
    if not suggestions:
        return False
    none_like = {"žádné", "zadne", "none", "n/a", "-", "–"}
    return suggestions not in none_like and not suggestions.startswith("žádné")


def msg_failsafe(hass: HomeAssistant, sensors: list[str]) -> tuple[str, str]:
    if _cs(hass):
        return (
            "FVE Optimizer – pojistka",
            "Chybí data ze střídače ("
            + ", ".join(sensors)
            + "). Zařízení na přebytek jsou zastavena; termíny pokračují.",
        )
    return (
        "FVE Optimizer – fail-safe",
        "No fresh inverter data ("
        + ", ".join(sensors)
        + "). Surplus devices stopped; deadlines continue.",
    )


def msg_failsafe_cleared(hass: HomeAssistant) -> tuple[str, str]:
    if _cs(hass):
        return ("FVE Optimizer – pojistka skončila", "Data ze střídače jsou zpět.")
    return ("FVE Optimizer – fail-safe cleared", "Inverter data is back.")


def msg_at_risk(hass: HomeAssistant, name: str, detail: str) -> tuple[str, str]:
    if _cs(hass):
        return (f"FVE Optimizer – {name} nestíhá", detail or "Termín je v riziku.")
    return (f"FVE Optimizer – {name} at risk", detail or "Deadline is at risk.")


def msg_review(hass: HomeAssistant, review: dict[str, Any]) -> tuple[str, str]:
    score = review.get("score")
    summary = str(review.get("summary") or "").strip()
    suggestions = str(review.get("suggestions") or "").strip()
    if _cs(hass):
        title = f"FVE Optimizer – hodnocení {score}/10"
        body = summary
        if suggestions and suggestions.lower() not in ("žádné", "zadne", "none"):
            body = f"{body}\n\nNávrhy:\n{suggestions}" if body else f"Návrhy:\n{suggestions}"
        return title, body or "Denní hodnocení je hotové."
    title = f"FVE Optimizer – review {score}/10"
    body = summary
    if suggestions and suggestions.lower() not in ("none", "n/a", "žádné"):
        body = f"{body}\n\nSuggestions:\n{suggestions}" if body else f"Suggestions:\n{suggestions}"
    return title, body or "Daily review is ready."


def msg_outlook_check(hass: HomeAssistant, name: str, advice: str) -> tuple[str, str]:
    if _cs(hass):
        return (f"FVE Optimizer – rada k {name}", advice)
    return (f"FVE Optimizer – advice for {name}", advice)


def msg_boost(hass: HomeAssistant, name: str, started: bool, detail: str = "") -> tuple[str, str]:
    if _cs(hass):
        title = f"FVE Optimizer – {name}: {'rychlé nabíjení' if started else 'boost ukončen'}"
    else:
        title = f"FVE Optimizer – {name}: {'boost started' if started else 'boost finished'}"
    return title, detail or title


def msg_order(
    hass: HomeAssistant,
    name: str,
    set_order: bool,
    detail: str = "",
    *,
    completed: bool = False,
) -> tuple[str, str]:
    if completed:
        if _cs(hass):
            title = f"FVE Optimizer – {name}: objednávka splněna"
        else:
            title = f"FVE Optimizer – {name}: charge order done"
        return title, detail or title
    if _cs(hass):
        title = f"FVE Optimizer – {name}: {'objednávka' if set_order else 'objednávka zrušena'}"
    else:
        title = f"FVE Optimizer – {name}: {'charge order' if set_order else 'order cleared'}"
    return title, detail or title
