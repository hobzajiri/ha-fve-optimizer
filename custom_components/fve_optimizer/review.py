"""Daily AI review of the optimizer's decisions via Home Assistant's AI Task.

The integration only prepares the day's data and asks whichever AI Task
entity the user selected (Google, Anthropic, OpenAI, Ollama…). The AI scores
the day and suggests setting changes – it never changes anything itself.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AI_TASK_ENTITY,
    DEVICE_TUNABLES,
    HUB_TUNABLES,
)

if TYPE_CHECKING:
    from .coordinator import FveOptimizerCoordinator

_LOGGER = logging.getLogger(__name__)

INSTRUCTIONS = """\
Jsi energetický poradce. Hodnotíš jeden den práce integrace FVE Optimizer pro Home
Assistant. Integrace rozděluje přebytky fotovoltaiky mezi domácí baterii a řízená
zařízení (bojler, nabíječka auta) podle priorit, termínů (minimální teplota bojleru
večer, minimální SoC auta ráno) a nízkého tarifu HDO. Cíle, v tomto pořadí:
1. splnit termíny a minima,
2. co nejvíc využít přebytky ze slunce (málo přetoku do sítě, málo odběru ze sítě),
3. šetřit zařízení (málo spínání, žádné rychlé cvakání; mělké cykly baterie jsou v pořádku),
4. neprovádět zbytečný cyklus „nabít baterii – vybít do bojleru“.

Data dne jsou v JSON níže: nastavení (názvy parametrů tak, jak je uživatel vidí),
spotřeba a náklady zařízení podle zdroje, odběr a přetok, spínání zařízení s časy,
doba pojistky (chybějící data ze střídače) a log rozhodnutí (jen změny).
Klíč „outlook“ je předpoklad zbytku dne spočítaný integrací (ne AI): predikce vs.
potřeba baterie, přednost baterie, u každého zařízení termín / NT okna / kolik kWh
ze slunce vs. ze sítě / riziko nestíhání. Ber ho jako faktický plán – hodnotíš, jestli
dává smysl a co změnit v nastavení, ať se termíny stihnou levněji.

Režim „dry_run“ znamená, že integrace jen sledovala a nic nespínala – pak hodnoť
hlavně kvalitu doporučení: dávala by smysl a co by se stalo, kdyby se provedla?

U každého sepnutí je v závorce, kdo ho způsobil: „integrace“ (automatické řízení),
„tlačítko Provést“ (uživatel ručně provedl doporučení) nebo „mimo integraci“ (ruční
zásah uživatele, jiná automatizace, termostat bojleru, auto samo). Zhodnoť i ruční
zásahy: byly v souladu s doporučeními, nebo naopak ukazují, co integrace přehlédla
(např. uživatel zapnul bojler, ale integrace ho nedoporučila)? „recommendations“
ukazuje doporučení dne a jak skončila, „plan_match_pct“ kolik % času odpovídal stav
zařízení plánu.

Konkrétní oblasti hodnocení (uveď jen když data ukazují problém nebo příležitost):
- termíny at_risk / málo NT oken → dřívější deadline_earliest, vyšší safety, vypnout
  hdo_only, nebo snížit cíl minima;
- forecast nestačí na baterii a zařízení bez termínu = OK (mají čekat); se zapnutým
  termínem mají jít ze sítě / NT;
- vysoký export + nízké využití zařízení při „devices first“ → limity teploty/SoC
  nebo priorita;
- časté spínání (max_switches_per_hour) → delší on/off delay;
- pojistka (failsafe) → senzory / timeout;
- dry_run: hodnotí doporučení, ne skutečné spínání.

Buď konkrétní a stručný, piš česky. Návrhy úprav uváděj jen tehdy, když je data
opravdu podporují, ve tvaru: „Zařízení – parametr: z X na Y – důvod“. Nevymýšlej
parametry, které v nastavení nejsou. Když není co měnit, napiš „Žádné“.

Data dne:
"""

STRUCTURE: dict[str, Any] = {
    "score": {
        "description": "Celková známka dne 1–10 (10 = výborné)",
        "required": True,
        "selector": {"number": {"min": 1, "max": 10, "step": 1}},
    },
    "summary": {
        "description": "Shrnutí dne ve 2–4 větách",
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
    "good": {
        "description": "Co fungovalo dobře – krátké odrážky, každá na řádek",
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
    "problems": {
        "description": "Problémy a zbytečné ztráty – krátké odrážky, každá na řádek, nebo „Žádné“",
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
    "suggestions": {
        "description": "Návrhy úprav nastavení – každý na řádek ve tvaru „Zařízení – parametr: z X na Y – důvod“, nebo „Žádné“",
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
    "outlook": {
        "description": (
            "Předpoklad zbytku dne podle „outlook“ v datech: rizika termínů, "
            "co čekat u bojleru/auta/baterie – krátké odrážky, nebo „Žádné“"
        ),
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
}


def _round(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    return value


def build_outlook(
    coordinator: FveOptimizerCoordinator, snap: Any | None = None
) -> dict[str, Any]:
    """Deterministic rest-of-day expectation from forecast + deadline plans."""
    snap = snap if snap is not None else coordinator.data
    if snap is None:
        return {}
    devices = []
    for device in sorted(coordinator.devices.values(), key=lambda d: d.priority):
        if not device.enabled:
            continue
        entry = {"name": device.name, "kind": device.kind, **device.outlook()}
        devices.append(entry)
    return _round(
        {
            "forecast": {
                "remaining_kwh": snap.forecast_remaining_kwh,
                "need_kwh": snap.forecast_need_kwh,
                "covers_battery": snap.forecast_covers_battery,
                "solar_for_devices_kwh": snap.solar_for_devices_kwh,
                "hours_until_sunset": snap.hours_until_sunset,
            },
            "battery": {
                "soc": snap.battery_soc,
                "target_soc": snap.effective_target_soc,
                "priority": snap.battery_priority,
                "borrow": snap.borrow_active,
            },
            "devices": devices,
        }
    )


def build_day_data(coordinator: FveOptimizerCoordinator) -> dict[str, Any]:
    """Everything the AI needs to judge today, in a compact form."""
    conf = coordinator.conf
    day = coordinator.today()
    snap = coordinator.data
    settings: dict[str, Any] = {
        "FVE Optimizer": {t.key: conf.get(t.key) for t in HUB_TUNABLES if t.key in conf},
    }
    devices: dict[str, Any] = {}
    for sid, device in coordinator.devices.items():
        tunables = DEVICE_TUNABLES.get(device.kind, ())
        settings[device.name] = {
            "type": device.kind,
            "controlled": device.enabled,
            **{t.key: device.config.get(t.key) for t in tunables if t.key in device.config},
        }
        switches = day.get("switches", {}).get(sid, [])
        per_hour: dict[str, int] = {}
        for entry in switches:
            per_hour[entry[:2]] = per_hour.get(entry[:2], 0) + 1
        match = day.get("plan_match", {}).get(sid)
        devices[device.name] = {
            "energy_kwh_today": coordinator.device_stats(sid).get("today", {}),
            "plan_match_pct": round(100 * match[0] / match[1]) if match and match[1] else None,
            "switches_today": len(switches),
            "max_switches_per_hour": max(per_hour.values(), default=0),
            "switch_times": switches,
            "state_now": device.status.reason,
            "outlook": device.outlook(),
        }
    return _round(
        {
            "date": day.get("date"),
            "time": dt_util.now().strftime("%H:%M"),
            "dry_run": coordinator.dry_run,
            "prices_czk_kwh": {"vt": conf.get("price_vt"), "nt": conf.get("price_nt")},
            "grid_today": {
                "import_kwh": day.get("import_kwh", 0.0),
                "export_kwh": day.get("export_kwh", 0.0),
                "battery_charge_kwh": day.get("battery_charge_kwh", 0.0),
                "battery_discharge_kwh": day.get("battery_discharge_kwh", 0.0),
            },
            "battery_now": {
                "soc": snap.battery_soc if snap else None,
                "target_soc": snap.effective_target_soc if snap else None,
            },
            "forecast_remaining_kwh": snap.forecast_remaining_kwh if snap else None,
            "outlook": build_outlook(coordinator),
            "failsafe_minutes": day.get("failsafe_s", 0.0) / 60,
            "recommendations": {
                "finished": day.get("recommendations", []),
                "open_now": [
                    {"since": r["since"][11:16], "text": r["text"]}
                    for r in coordinator.open_recommendations()
                ],
            },
            "devices": devices,
            "settings": settings,
            "decision_log": day.get("log", []),
        }
    )


async def async_review(coordinator: FveOptimizerCoordinator) -> dict[str, Any]:
    """Ask the AI Task entity for today's review and return it (raises on failure)."""
    entity_id = coordinator.conf.get(CONF_AI_TASK_ENTITY)
    if not entity_id:
        raise HomeAssistantError("No AI Task entity selected")
    data = build_day_data(coordinator)
    response = await coordinator.hass.services.async_call(
        "ai_task",
        "generate_data",
        {
            "task_name": "FVE Optimizer – denní hodnocení",
            "entity_id": entity_id,
            "instructions": INSTRUCTIONS + json.dumps(data, ensure_ascii=False),
            "structure": STRUCTURE,
        },
        blocking=True,
        return_response=True,
    )
    result = (response or {}).get("data") or {}
    if not isinstance(result, dict) or "score" not in result:
        raise HomeAssistantError(f"Unexpected AI Task response: {response!r}")
    review = {
        "at": dt_util.now().isoformat(),
        "date": data["date"],
        "entity_id": entity_id,
        "dry_run": data["dry_run"],
        "score": int(round(float(result.get("score") or 0))),
        "summary": str(result.get("summary") or "").strip(),
        "good": str(result.get("good") or "").strip(),
        "problems": str(result.get("problems") or "").strip(),
        "suggestions": str(result.get("suggestions") or "").strip(),
        "outlook": str(result.get("outlook") or "").strip(),
    }
    _LOGGER.info("AI review %s: %s/10 – %s", review["date"], review["score"], review["summary"])
    return review


OUTLOOK_CHECK_INSTRUCTIONS = """\
Jsi energetický poradce. Integrace FVE Optimizer hlásí, že zařízení nestíhá termín
(at_risk). Dostaneš aktuální „outlook“ (predikce, plán HDO, potřeba kWh) a nastavení.
Navrhni 1–3 konkrétní kroky pro uživatele (změna parametru, ruční zásah, nebo „počkat
na NT“). Piš česky, stručně. Nic sám neměň – jen poradíš.

Data:
"""

OUTLOOK_CHECK_STRUCTURE: dict[str, Any] = {
    "urgency": {
        "description": "Naléhavost 1–5 (5 = hned jednat)",
        "required": True,
        "selector": {"number": {"min": 1, "max": 5, "step": 1}},
    },
    "advice": {
        "description": "Konkrétní rada ve 2–5 větách nebo odrážkách",
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
}


async def async_outlook_check(
    coordinator: FveOptimizerCoordinator, device_id: str
) -> dict[str, Any]:
    """Short AI advice when a device deadline becomes at_risk."""
    entity_id = coordinator.conf.get(CONF_AI_TASK_ENTITY)
    if not entity_id:
        raise HomeAssistantError("No AI Task entity selected")
    device = coordinator.devices.get(device_id)
    if device is None:
        raise HomeAssistantError(f"Unknown device {device_id}")
    payload = _round(
        {
            "time": dt_util.now().strftime("%H:%M"),
            "device": {
                "id": device_id,
                "name": device.name,
                "kind": device.kind,
                "settings": {
                    t.key: device.config.get(t.key)
                    for t in DEVICE_TUNABLES.get(device.kind, ())
                    if t.key in device.config
                },
                "outlook": device.outlook(),
                "reason": device.status.reason,
            },
            "outlook": build_outlook(coordinator),
            "hdo": coordinator.data.hdo_active if coordinator.data else None,
            "dry_run": coordinator.dry_run,
        }
    )
    response = await coordinator.hass.services.async_call(
        "ai_task",
        "generate_data",
        {
            "task_name": f"FVE Optimizer – rada ({device.name})",
            "entity_id": entity_id,
            "instructions": OUTLOOK_CHECK_INSTRUCTIONS + json.dumps(payload, ensure_ascii=False),
            "structure": OUTLOOK_CHECK_STRUCTURE,
        },
        blocking=True,
        return_response=True,
    )
    result = (response or {}).get("data") or {}
    if not isinstance(result, dict) or not result.get("advice"):
        raise HomeAssistantError(f"Unexpected AI Task response: {response!r}")
    advice = {
        "at": dt_util.now().isoformat(),
        "device_id": device_id,
        "device": device.name,
        "entity_id": entity_id,
        "urgency": int(round(float(result.get("urgency") or 3))),
        "advice": str(result.get("advice") or "").strip(),
    }
    _LOGGER.info("AI outlook check %s: %s", device.name, advice["advice"][:120])
    return advice
