"""Daily AI review of the optimizer's decisions via Home Assistant's AI Task.

The integration only prepares the day's data and asks whichever AI Task
entity the user selected (Google, Anthropic, OpenAI, Ollama…). The AI scores
the day and suggests setting changes – it never changes anything itself.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AI_TASK_ENTITY,
    CONF_BATTERY_BORROW,
    CONF_FORECAST_MIN_SOC,
    CONF_FORECAST_SAFETY,
    CONF_MIN_OFF_TIME,
    CONF_MIN_ON_TIME,
    CONF_OFF_DELAY,
    CONF_OFF_TOLERANCE,
    CONF_ON_DELAY,
    CONF_ON_MARGIN,
    CONF_PRIORITY,
    CONF_RESERVE_W,
    DEVICE_TUNABLES,
    HUB_TUNABLES,
    Tunable,
)

if TYPE_CHECKING:
    from .coordinator import FveOptimizerCoordinator

_LOGGER = logging.getLogger(__name__)

# How many decision-log lines to send (full day can be huge and confuse the model).
DECISION_LOG_FOR_AI = 30
# on→off→on (or off→on→off) within this many minutes counts as a short cycle.
SHORT_CYCLE_MIN = 10
# Kept Q&A turns on the latest review (user question + AI answer = one turn).
DISCUSSION_MAX_TURNS = 20
# Hub keys that are not about energy control – omit from the AI payload.
_HUB_SETTINGS_SKIP_PREFIXES = ("ai_", "notify_")
_HUB_SETTINGS_SKIP = frozenset({"persistent_notification", "ai_task_entity", "notify_service"})

# Soft tunables AI may propose (apply only after user approval).
PROPOSAL_MAX = 5
HUB_PROPOSAL_KEYS = frozenset({
    CONF_RESERVE_W,
    CONF_FORECAST_SAFETY,
    CONF_BATTERY_BORROW,
    CONF_FORECAST_MIN_SOC,
})
DEVICE_PROPOSAL_KEYS = frozenset({
    CONF_ON_DELAY,
    CONF_OFF_DELAY,
    CONF_ON_MARGIN,
    CONF_OFF_TOLERANCE,
    CONF_MIN_ON_TIME,
    CONF_MIN_OFF_TIME,
    CONF_PRIORITY,
})
_DELAY_PROPOSAL_KEYS = frozenset({
    CONF_ON_DELAY,
    CONF_OFF_DELAY,
    CONF_MIN_ON_TIME,
    CONF_MIN_OFF_TIME,
})
_HUB_TARGET_ALIASES = frozenset({"hub", "fve optimizer", "fve_optimizer"})
_HUB_TUNABLES_BY_KEY = {t.key: t for t in HUB_TUNABLES}

INSTRUCTIONS = """\
Jsi energetický poradce. Hodnotíš jeden den práce integrace FVE Optimizer pro Home
Assistant. Integrace rozděluje přebytky fotovoltaiky mezi domácí baterii a řízená
zařízení (bojler, nabíječka auta) podle priorit, termínů (minimální teplota bojleru
večer, minimální SoC auta ráno) a nízkého tarifu HDO. Cíle, v tomto pořadí:
1. splnit termíny a minima,
2. co nejvíc využít přebytky ze slunce (málo přetoku do sítě, málo odběru ze sítě),
3. šetřit zařízení (málo spínání, žádné rychlé cvakání; mělké cykly baterie jsou v pořádku),
4. neprovádět zbytečný cyklus „nabít baterii – vybít do bojleru“.

Známka 1–10 (drž se této škály; „scoring_hints“ jsou pevné kotvy z integrace):
- 9–10: termíny OK (nebo bez termínu), dobré FV využití, bez zbytečného importu/exportu,
  spínání v normě (málo short_cycles, rozumné max_per_hour).
- 7–8: drobné ztráty, pár zbytečných sepnutí, nebo mírně dlouhé/krátké delay – nic vážného.
- 5–6: jasný problém (at_risk v outlooku, vysoký export při volné kapacitě zařízení,
  hunting = short_cycles > 0 / vysoké max_per_hour od integrace).
- ≤4: vážné selhání (nesplněný termín, dlouhá pojistka, agresivní cvakání relé).
Při splněných termínech a dobrém FV nesnižuj známku jen kvůli hustému decision_logu.

Data dne jsou v JSON níže: nastavení (klíče parametrů přesně jako v „settings“,
např. on_delay_s), spotřeba a náklady zařízení podle zdroje, odběr a přetok,
spínání zařízení, scoring_hints, doba pojistky a zkrácený decision_log.
Klíč „outlook“ je aktuální předpoklad zbytku dne spočítaný integrací (ne AI).
Klíč „morning_plan“ je ranní snímek (čísla z integrace + AI text) – baseline dne.
Když morning_plan chybí (null), nesrovnávej s ránem.
Klíč „charge_forecast“ je poslední AI předpověď nabití během dne (aktualizovatelná);
můžeš zmínit, jak se odhad vyvíjel oproti ránu.

Režim „dry_run“ znamená, že integrace jen sledovala a nic nespínala – pak hodnoť
hlavně kvalitu doporučení: dávala by smysl a co by se stalo, kdyby se provedla?

Spínání – jen skutečná sepnutí relé / nabíjení:
- Hodnoť frekvenci spínání výhradně z „switching“ a „switch_times“.
  To jsou pozorované změny stavu zařízení, ne záměry dispečera.
- „decision_log“ je jen doplněk (proč se rozhodovalo: waiting ↔ starting…).
  Časté střídání v logu je při kolísání výroby normální a NENÍ důkaz cvakání
  relé. Nikdy z něj nevyvozuj nestabilitu spínání ani delší delay.
- Pro on/off delay ber v úvahu hlavně sepnutí od „integrace“ (viz by_source,
  integration_count, max_per_hour, min_gap_min, short_cycles). „mimo integraci“
  a „tlačítko Provést“ delayy neovlivní.
- Orientačně: ≤ ~8 sepnutí integrace/den, max_per_hour ≤ 2–3 a short_cycles = 0
  = v pořádku, delay neprodlužuj. Hunting = short_cycles > 0 nebo vysoké
  max_per_hour → delší on_delay_s / off_delay_s (nebo min_on_time_s /
  min_off_time_s u bojleru). Málo sepnutí + dlouhé delay + zbytečný export /
  držení zátěže z baterie → kratší delay (typicky k 60–180 s). Delay nad
  ~15–20 min jen při opravdu agresivním cvakání.
- Zhodnoť i ruční zásahy: byly v souladu s doporučeními, nebo ukazují, co
  integrace přehlédla? „recommendations“ a „plan_match_pct“ k tomu pomáhají.

Konkrétní oblasti (uveď jen když data ukazují problém nebo příležitost):
- termíny at_risk / málo NT oken → dřívější deadline_earliest, vyšší safety, vypnout
  hdo_only, nebo snížit cíl minima;
- forecast nestačí na baterii a zařízení bez termínu = OK (mají čekat); se zapnutým
  termínem mají jít ze sítě / NT;
- vysoký export + nízké využití zařízení při „devices first“ → limity teploty/SoC
  nebo priorita;
- skutečné spínání (viz výše) → delší NEBO kratší on_delay_s / off_delay_s;
- pojistka (failsafe) → senzory / timeout;
- dry_run: hodnotí doporučení, ne skutečné spínání.

Srovnání s ranním plánem (když je „morning_plan“):
- Porovnej skutečnost (grid_today, energy_kwh_today u zařízení, termíny/outlook,
  scoring_hints) s ranním forecastem a očekáváními.
- V „good“ / „problems“ uveď, co sedělo a co se lišilo, a pravděpodobný důvod
  (počasí / predikce, řízení FVE Optimizeru, ruční zásah, HDO).
- Nevymýšlej ranní čísla – ber jen z morning_plan.snapshot.

Pole „outlook“ ve tvé odpovědi: večer / po západu (hours_until_sunset ≈ 0,
hodnocení typicky kolem 21:00) shrň srovnání s ránem v 1–3 odrážkách, nebo
krátce zítřek – nedramatizuj „zbytek dne“. Jinak shrň rizika z JSON outlooku.

Buď konkrétní a stručný, piš česky. Návrhy úprav uváděj jen tehdy, když je data
opravdu podporují:
- v „suggestions“ text: „Zařízení – klíč_parametru: z X na Y – důvod“ (nebo „Žádné“);
- v „proposals“ JSON pole max 5 objektů
  {"target":"Bojler"|"hub","key":"off_delay_s","from":60,"to":180,"reason":"…"}
  nebo [] / „Žádné“. Klíč přesně z „settings“. Povoleno jen: on_delay_s, off_delay_s,
  on_margin_w, off_tolerance_w, min_on_time_s, min_off_time_s, priority, reserve_w,
  forecast_safety_factor, battery_borrow, forecast_min_soc.
Nic sama neměň – návrhy schválí uživatel. Nevymýšlej jiné parametry ani entity.

Data dne:
"""

STRUCTURE: dict[str, Any] = {
    "score": {
        "description": (
            "Celková známka dne 1–10 podle škály v instrukcích "
            "(9–10 výborné, ≤4 jen vážné selhání)"
        ),
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
        "description": (
            "Návrhy úprav – každý na řádek „Zařízení – klíč_z_settings: z X na Y – důvod“, "
            "nebo „Žádné“"
        ),
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
    "proposals": {
        "description": (
            "JSON pole max 5 návrhů nastavení: "
            '[{"target":"Bojler"|"hub","key":"off_delay_s","from":60,"to":180,'
            '"reason":"krátký důvod"}] nebo [] / Žádné. Jen povolené klíče z instrukcí.'
        ),
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
    "outlook": {
        "description": (
            "Večer: srovnání s morning_plan / zítřek; jinak rizika z JSON outlook – "
            "krátké odrážky, nebo „Žádné“"
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


def _parse_switch_entry(entry: str) -> tuple[int | None, str | None, str]:
    """Return (minute_of_day, on|off|None, source) from a switch log line."""
    source = "neznámý"
    if "(" in entry and entry.endswith(")"):
        source = entry[entry.rfind("(") + 1 : -1]
    minute: int | None = None
    action: str | None = None
    if len(entry) >= 5 and entry[2] == ":":
        try:
            minute = int(entry[:2]) * 60 + int(entry[3:5])
        except ValueError:
            minute = None
    # "14:35 on (integrace)" / "09:01 off (mimo integraci)"
    rest = entry[6:] if len(entry) > 6 else ""
    if rest.startswith("on"):
        action = "on"
    elif rest.startswith("off"):
        action = "off"
    return minute, action, source


def _switching_stats(switches: list[str]) -> dict[str, Any]:
    """Summarize observed on/off events for the AI (not decision-log chatter)."""
    by_source: dict[str, int] = {}
    per_hour: dict[str, int] = {}
    integration: list[tuple[int, str]] = []  # (minute_of_day, on|off)
    for entry in switches:
        minute, action, source = _parse_switch_entry(entry)
        by_source[source] = by_source.get(source, 0) + 1
        if source != "integrace":
            continue
        if minute is not None:
            hour = f"{minute // 60:02d}"
            per_hour[hour] = per_hour.get(hour, 0) + 1
            if action in ("on", "off"):
                integration.append((minute, action))
    gaps = [
        b[0] - a[0]
        for a, b in zip(integration, integration[1:], strict=False)
        if b[0] >= a[0]
    ]
    short_cycles = 0
    for i in range(len(integration) - 2):
        t0, a0 = integration[i]
        t1, a1 = integration[i + 1]
        t2, a2 = integration[i + 2]
        if t2 < t0:
            continue
        if a0 == a2 and a0 != a1 and (t2 - t0) < SHORT_CYCLE_MIN:
            short_cycles += 1
    return {
        "total": len(switches),
        "by_source": by_source,
        "max_per_hour": max(per_hour.values(), default=0),
        "integration_count": by_source.get("integrace", 0),
        "min_gap_min": min(gaps) if gaps else None,
        "short_cycles": short_cycles,
    }


def _hub_settings_for_ai(conf: dict[str, Any]) -> dict[str, Any]:
    """Energy-related hub tunables only (skip AI/notify noise)."""
    out: dict[str, Any] = {}
    for tunable in HUB_TUNABLES:
        key = tunable.key
        if key not in conf:
            continue
        if key in _HUB_SETTINGS_SKIP or key.startswith(_HUB_SETTINGS_SKIP_PREFIXES):
            continue
        out[key] = conf.get(key)
    return out


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


def build_morning_snapshot(coordinator: FveOptimizerCoordinator) -> dict[str, Any]:
    """Deterministic morning baseline (numbers only – AI adds prose later)."""
    conf = coordinator.conf
    snap = coordinator.data
    return _round(
        {
            "date": dt_util.now().date().isoformat(),
            "at": dt_util.now().isoformat(),
            "dry_run": coordinator.dry_run,
            "prices_czk_kwh": {"vt": conf.get("price_vt"), "nt": conf.get("price_nt")},
            "outlook": build_outlook(coordinator, snap),
        }
    )


MORNING_INSTRUCTIONS = """\
Jsi energetický poradce. Ráno připravuješ krátký předpoklad dne pro integraci
FVE Optimizer (Home Assistant). Dostaneš deterministický snímek predikce a plánu
zařízení spočítaný integrací – čísla ber jako fakt, nevymýšlej jiná.

Shrň česky: kolik kWh se ještě čeká ze slunce, jestli to stačí na baterii, co
dostanou bojler/auto (termíny, slunce vs. síť/NT), hlavní rizika. Nic neměň –
jen popisuješ předpoklad. Buď stručný.

Data (JSON):
"""

MORNING_STRUCTURE: dict[str, Any] = {
    "summary": {
        "description": "Shrnutí předpokladu dne ve 2–4 větách",
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
    "expectations": {
        "description": (
            "Očekávání – krátké odrážky (výroba, baterie, bojler, auto, export/import)"
        ),
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
    "risks": {
        "description": "Rizika / na co dát pozor – odrážky, nebo „Žádné“",
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
}


async def async_morning_brief(
    coordinator: FveOptimizerCoordinator,
) -> dict[str, Any]:
    """Ask the AI for a morning day plan; return plan with snapshot + prose."""
    entity_id = coordinator.conf.get(CONF_AI_TASK_ENTITY)
    if not entity_id:
        raise HomeAssistantError("No AI Task entity selected")
    snapshot = build_morning_snapshot(coordinator)
    response = await coordinator.hass.services.async_call(
        "ai_task",
        "generate_data",
        {
            "task_name": "FVE Optimizer – ranní předpoklad",
            "entity_id": entity_id,
            "instructions": MORNING_INSTRUCTIONS + json.dumps(snapshot, ensure_ascii=False),
            "structure": MORNING_STRUCTURE,
        },
        blocking=True,
        return_response=True,
    )
    result = (response or {}).get("data") or {}
    if not isinstance(result, dict) or not result.get("summary"):
        raise HomeAssistantError(f"Unexpected AI Task response: {response!r}")
    plan = {
        "date": snapshot["date"],
        "at": snapshot["at"],
        "entity_id": entity_id,
        "dry_run": snapshot["dry_run"],
        "summary": str(result.get("summary") or "").strip(),
        "expectations": str(result.get("expectations") or "").strip(),
        "risks": str(result.get("risks") or "").strip(),
        "snapshot": snapshot,
    }
    _LOGGER.info(
        "AI morning brief %s: %s",
        plan["date"],
        plan["summary"][:120],
    )
    return plan


def build_charge_snapshot(coordinator: FveOptimizerCoordinator) -> dict[str, Any]:
    """Deterministic mid-day snapshot for the charge forecast."""
    conf = coordinator.conf
    day = coordinator.today()
    snap = coordinator.data
    return _round(
        {
            "date": dt_util.now().date().isoformat(),
            "at": dt_util.now().isoformat(),
            "dry_run": coordinator.dry_run,
            "prices_czk_kwh": {"vt": conf.get("price_vt"), "nt": conf.get("price_nt")},
            "grid_so_far": {
                "import_kwh": day.get("import_kwh", 0.0),
                "export_kwh": day.get("export_kwh", 0.0),
                "battery_charge_kwh": day.get("battery_charge_kwh", 0.0),
                "battery_discharge_kwh": day.get("battery_discharge_kwh", 0.0),
            },
            "outlook": build_outlook(coordinator, snap),
            "morning_summary": (
                (coordinator.morning_plan or {}).get("summary")
                if coordinator.morning_plan
                and coordinator.morning_plan.get("date") == dt_util.now().date().isoformat()
                else None
            ),
        }
    )


CHARGE_INSTRUCTIONS = """\
Jsi energetický poradce. Odhaduješ, kam se dnes dostane nabití (domácí baterie,
bojler, auto) u integrace FVE Optimizer. Dostaneš aktuální snímek predikce a plánu
ze integrace – čísla ber jako fakt.

Odhadni do západu slunce / do termínů: očekávané SoC baterie večer, u bojleru
teplotu nebo splnění termínu, u auta SoC nebo splnění termínu. Piš česky, stručně.
Nic neměň – jen předpovídáš. battery_expected_soc uveď jako celé číslo 0–100.

Data (JSON):
"""

CHARGE_STRUCTURE: dict[str, Any] = {
    "summary": {
        "description": "Shrnutí předpovědi nabití ve 2–4 větách",
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
    "battery_expected_soc": {
        "description": "Očekávané SoC domácí baterie večer (0–100)",
        "required": True,
        "selector": {"number": {"min": 0, "max": 100, "step": 1}},
    },
    "battery_note": {
        "description": "Krátká poznámka k baterii (1 věta)",
        "required": True,
        "selector": {"text": {}},
    },
    "devices": {
        "description": (
            "Očekávání u bojleru/auta – krátké odrážky (cíl, ze slunce/NT, riziko)"
        ),
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
    "risks": {
        "description": "Rizika – odrážky, nebo „Žádné“",
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
}


async def async_charge_forecast(
    coordinator: FveOptimizerCoordinator,
) -> dict[str, Any]:
    """Ask the AI for an updatable mid-day charge forecast."""
    entity_id = coordinator.conf.get(CONF_AI_TASK_ENTITY)
    if not entity_id:
        raise HomeAssistantError("No AI Task entity selected")
    snapshot = build_charge_snapshot(coordinator)
    response = await coordinator.hass.services.async_call(
        "ai_task",
        "generate_data",
        {
            "task_name": "FVE Optimizer – předpověď nabití",
            "entity_id": entity_id,
            "instructions": CHARGE_INSTRUCTIONS + json.dumps(snapshot, ensure_ascii=False),
            "structure": CHARGE_STRUCTURE,
        },
        blocking=True,
        return_response=True,
    )
    result = (response or {}).get("data") or {}
    if not isinstance(result, dict) or not result.get("summary"):
        raise HomeAssistantError(f"Unexpected AI Task response: {response!r}")
    try:
        soc = int(round(float(result.get("battery_expected_soc") or 0)))
    except (TypeError, ValueError):
        soc = 0
    soc = max(0, min(100, soc))
    forecast = {
        "date": snapshot["date"],
        "at": snapshot["at"],
        "entity_id": entity_id,
        "dry_run": snapshot["dry_run"],
        "summary": str(result.get("summary") or "").strip(),
        "battery_expected_soc": soc,
        "battery_note": str(result.get("battery_note") or "").strip(),
        "devices": str(result.get("devices") or "").strip(),
        "risks": str(result.get("risks") or "").strip(),
        "snapshot": snapshot,
    }
    _LOGGER.info(
        "AI charge forecast %s: battery ~%s %% – %s",
        forecast["date"],
        soc,
        forecast["summary"][:100],
    )
    return forecast


def build_day_data(coordinator: FveOptimizerCoordinator) -> dict[str, Any]:
    """Everything the AI needs to judge today, in a compact form."""
    conf = coordinator.conf
    day = coordinator.today()
    snap = coordinator.data
    settings: dict[str, Any] = {"FVE Optimizer": _hub_settings_for_ai(conf)}
    devices: dict[str, Any] = {}
    integration_switches = 0
    deadlines_at_risk: list[str] = []
    for sid, device in coordinator.devices.items():
        tunables = DEVICE_TUNABLES.get(device.kind, ())
        settings[device.name] = {
            "type": device.kind,
            "controlled": device.enabled,
            **{t.key: device.config.get(t.key) for t in tunables if t.key in device.config},
        }
        switches = day.get("switches", {}).get(sid, [])
        match = day.get("plan_match", {}).get(sid)
        switching = _switching_stats(switches)
        integration_switches += int(switching["integration_count"])
        device_outlook = device.outlook()
        if device_outlook.get("at_risk"):
            deadlines_at_risk.append(device.name)
        devices[device.name] = {
            "energy_kwh_today": coordinator.device_stats(sid).get("today", {}),
            "plan_match_pct": round(100 * match[0] / match[1]) if match and match[1] else None,
            "switching": switching,
            "switch_times": switches,
            "state_now": device.status.reason,
            "outlook": device_outlook,
        }
    log = day.get("log", [])
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
            "morning_plan": coordinator.morning_plan_for_ai(),
            "charge_forecast": coordinator.charge_forecast_for_ai(),
            "failsafe_minutes": day.get("failsafe_s", 0.0) / 60,
            "scoring_hints": {
                "deadlines_at_risk": deadlines_at_risk,
                "failsafe_minutes": round(day.get("failsafe_s", 0.0) / 60, 2),
                "integration_switches": integration_switches,
                "export_kwh": day.get("export_kwh", 0.0),
                "import_kwh": day.get("import_kwh", 0.0),
            },
            "recommendations": {
                "finished": day.get("recommendations", []),
                "open_now": [
                    {"since": r["since"][11:16], "text": r["text"]}
                    for r in coordinator.open_recommendations()
                ],
            },
            "devices": devices,
            "settings": settings,
            # Reason changes only – not relay flips; see each device's "switching".
            "decision_log": log[-DECISION_LOG_FOR_AI:],
        }
    )


def _clamp_score(value: Any) -> int:
    try:
        score = int(round(float(value or 0)))
    except (TypeError, ValueError):
        score = 0
    return max(1, min(10, score))


def _proposal_id(target: str, key: str, to_value: Any) -> str:
    raw = f"{target}|{key}|{to_value}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("1", "true", "yes", "on", "ano"):
            return True
        if low in ("0", "false", "no", "off", "ne"):
            return False
    return None


def _snap_number(value: float, tunable: Tunable) -> float:
    mn, mx = float(tunable.minimum), float(tunable.maximum)
    step = float(tunable.step or 1)
    v = max(mn, min(mx, float(value)))
    if step > 0:
        v = round(round((v - mn) / step) * step + mn, 10)
    if step >= 1 and abs(v - round(v)) < 1e-9:
        return float(int(round(v)))
    return v


def _limit_delay_delta(from_v: float, to_v: float) -> float:
    """Cap delay-like changes to about ×3 or ±300 s."""
    if to_v > from_v:
        return min(to_v, max(from_v * 3.0, from_v + 300.0))
    if to_v < from_v:
        floor = 0.0 if from_v < 300 else min(from_v / 3.0, from_v - 300.0)
        return max(to_v, floor)
    return to_v


def _load_proposal_items(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    text = str(raw).strip()
    if not text or re.fullmatch(r"(žádné|zadne|none|n/?a|\[?\s*\]?)", text, re.I):
        return []
    # Allow fenced ```json ... ```
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Sometimes the model wraps a single object.
        try:
            data = json.loads(f"[{text}]")
        except json.JSONDecodeError:
            _LOGGER.warning("AI proposals JSON unreadable: %s", text[:200])
            return []
    if isinstance(data, dict):
        data = data.get("proposals") or data.get("items") or [data]
    return data if isinstance(data, list) else []


def parse_proposals(
    coordinator: FveOptimizerCoordinator,
    raw: Any,
    *,
    day_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Validate AI proposals against whitelist, tunables and current settings."""
    settings = day_settings if day_settings is not None else build_day_data(coordinator).get(
        "settings", {}
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _load_proposal_items(raw):
        if len(out) >= PROPOSAL_MAX:
            break
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        target_raw = str(item.get("target") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if not key or not target_raw:
            continue

        scope: str | None = None
        subentry_id: str | None = None
        target_label = target_raw
        tunable: Tunable | None = None
        current: Any = None

        if target_raw.lower() in _HUB_TARGET_ALIASES or target_raw == "FVE Optimizer":
            if key not in HUB_PROPOSAL_KEYS:
                out.append(
                    {
                        "id": _proposal_id(target_raw, key, item.get("to")),
                        "target": "hub",
                        "key": key,
                        "from": item.get("from"),
                        "to": item.get("to"),
                        "reason": reason,
                        "status": "invalid",
                        "error": "key_not_allowed",
                    }
                )
                continue
            scope = "hub"
            target_label = "hub"
            tunable = _HUB_TUNABLES_BY_KEY.get(key)
            hub_settings = settings.get("FVE Optimizer") or {}
            current = hub_settings.get(key, coordinator.conf.get(key))
        else:
            if key not in DEVICE_PROPOSAL_KEYS:
                out.append(
                    {
                        "id": _proposal_id(target_raw, key, item.get("to")),
                        "target": target_raw,
                        "key": key,
                        "from": item.get("from"),
                        "to": item.get("to"),
                        "reason": reason,
                        "status": "invalid",
                        "error": "key_not_allowed",
                    }
                )
                continue
            match_sid = None
            match_name = None
            for sid, device in coordinator.devices.items():
                if device.name == target_raw or device.name.lower() == target_raw.lower():
                    match_sid, match_name = sid, device.name
                    break
            if match_sid is None:
                out.append(
                    {
                        "id": _proposal_id(target_raw, key, item.get("to")),
                        "target": target_raw,
                        "key": key,
                        "from": item.get("from"),
                        "to": item.get("to"),
                        "reason": reason,
                        "status": "invalid",
                        "error": "unknown_target",
                    }
                )
                continue
            scope = "device"
            subentry_id = match_sid
            target_label = match_name or target_raw
            device = coordinator.devices[match_sid]
            for t in DEVICE_TUNABLES.get(device.kind, ()):
                if t.key == key:
                    tunable = t
                    break
            dev_settings = settings.get(target_label) or settings.get(device.name) or {}
            current = dev_settings.get(key, device.config.get(key))

        if tunable is None:
            out.append(
                {
                    "id": _proposal_id(target_label, key, item.get("to")),
                    "target": target_label,
                    "key": key,
                    "scope": scope,
                    "subentry_id": subentry_id,
                    "from": item.get("from"),
                    "to": item.get("to"),
                    "reason": reason,
                    "status": "invalid",
                    "error": "unknown_key",
                }
            )
            continue

        if tunable.kind == "switch":
            to_val = _parse_bool(item.get("to"))
            from_val = _parse_bool(item.get("from"))
            if from_val is None:
                from_val = _parse_bool(current)
            if to_val is None or from_val is None:
                out.append(
                    {
                        "id": _proposal_id(target_label, key, item.get("to")),
                        "target": target_label,
                        "key": key,
                        "scope": scope,
                        "subentry_id": subentry_id,
                        "from": item.get("from"),
                        "to": item.get("to"),
                        "reason": reason,
                        "status": "invalid",
                        "error": "bad_bool",
                    }
                )
                continue
            if to_val == from_val:
                continue
        else:
            try:
                to_raw = float(item.get("to"))
                from_ai = item.get("from")
                from_val = float(from_ai) if from_ai is not None else float(current)
            except (TypeError, ValueError):
                out.append(
                    {
                        "id": _proposal_id(target_label, key, item.get("to")),
                        "target": target_label,
                        "key": key,
                        "scope": scope,
                        "subentry_id": subentry_id,
                        "from": item.get("from"),
                        "to": item.get("to"),
                        "reason": reason,
                        "status": "invalid",
                        "error": "bad_number",
                    }
                )
                continue
            # Prefer live current as baseline when AI's "from" drifted.
            try:
                live = float(current)
                from_val = live
            except (TypeError, ValueError):
                pass
            to_val = _snap_number(to_raw, tunable)
            if key in _DELAY_PROPOSAL_KEYS:
                to_val = _snap_number(_limit_delay_delta(from_val, to_val), tunable)
            if abs(to_val - from_val) < 1e-9:
                continue

        pid = _proposal_id(target_label, key, to_val)
        if pid in seen:
            continue
        seen.add(pid)
        out.append(
            {
                "id": pid,
                "target": target_label,
                "key": key,
                "scope": scope,
                "subentry_id": subentry_id,
                "from": from_val,
                "to": to_val,
                "reason": reason,
                "status": "pending",
            }
        )
    return out


async def async_review(
    coordinator: FveOptimizerCoordinator,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask the AI Task entity for today's review; return (review, day_data)."""
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
    proposals = parse_proposals(
        coordinator, result.get("proposals"), day_settings=data.get("settings")
    )
    review = {
        "at": dt_util.now().isoformat(),
        "date": data["date"],
        "entity_id": entity_id,
        "dry_run": data["dry_run"],
        "score": _clamp_score(result.get("score")),
        "summary": str(result.get("summary") or "").strip(),
        "good": str(result.get("good") or "").strip(),
        "problems": str(result.get("problems") or "").strip(),
        "suggestions": str(result.get("suggestions") or "").strip(),
        "proposals": proposals,
        "outlook": str(result.get("outlook") or "").strip(),
        "discussion": [],
    }
    _LOGGER.info(
        "AI review %s: %s/10 – %s (%s proposals)",
        review["date"],
        review["score"],
        review["summary"],
        sum(1 for p in proposals if p.get("status") == "pending"),
    )
    return review, data


DISCUSS_INSTRUCTIONS = """\
Jsi energetický poradce. Uživatel se ptá na denní AI hodnocení integrace FVE Optimizer.
Dostaneš: původní data dne, hotové hodnocení (známka, shrnutí, problémy, návrhy) a
dosavadní diskusi. Odpověz na otázku stručně česky. Opírej se o data a hodnocení –
nevymýšlej čísla. Parametry nastavení uváděj přesnými klíči (např. off_delay_s).
Nic sama neměň – jen radíš. Když něco z dat neplyne, řekni to.

Kontext (JSON):
"""

DISCUSS_STRUCTURE: dict[str, Any] = {
    "answer": {
        "description": "Odpověď na otázku uživatele – 2–8 vět nebo krátké odrážky",
        "required": True,
        "selector": {"text": {"multiline": True}},
    },
}


async def async_ask_review(
    coordinator: FveOptimizerCoordinator, question: str, day_data: dict[str, Any]
) -> dict[str, Any]:
    """Follow-up question about the latest review (stateless: full context each call)."""
    entity_id = coordinator.conf.get(CONF_AI_TASK_ENTITY)
    if not entity_id:
        raise HomeAssistantError("No AI Task entity selected")
    if not coordinator.reviews:
        raise HomeAssistantError("No review to discuss – run the daily review first")
    q = (question or "").strip()
    if not q:
        raise HomeAssistantError("Empty question")
    review = coordinator.reviews[0]
    payload = {
        "question": q,
        "review": {
            k: review.get(k)
            for k in (
                "date",
                "at",
                "score",
                "summary",
                "good",
                "problems",
                "suggestions",
                "proposals",
                "outlook",
                "dry_run",
            )
        },
        "discussion": list(review.get("discussion") or [])[-DISCUSSION_MAX_TURNS:],
        "day_data": day_data,
    }
    response = await coordinator.hass.services.async_call(
        "ai_task",
        "generate_data",
        {
            "task_name": "FVE Optimizer – diskuse k hodnocení",
            "entity_id": entity_id,
            "instructions": DISCUSS_INSTRUCTIONS + json.dumps(payload, ensure_ascii=False),
            "structure": DISCUSS_STRUCTURE,
        },
        blocking=True,
        return_response=True,
    )
    result = (response or {}).get("data") or {}
    answer = str((result or {}).get("answer") or "").strip()
    if not answer:
        raise HomeAssistantError(f"Unexpected AI Task response: {response!r}")
    turn = {
        "at": dt_util.now().isoformat(),
        "question": q,
        "answer": answer,
    }
    _LOGGER.info("AI review discuss: %s → %s", q[:80], answer[:80])
    return turn


OUTLOOK_CHECK_INSTRUCTIONS = """\
Jsi energetický poradce. Integrace FVE Optimizer hlásí, že zařízení nestíhá termín
(at_risk). Dostaneš aktuální „outlook“ (predikce, plán HDO, potřeba kWh) a nastavení.
Navrhni 1–3 konkrétní kroky pro uživatele (změna parametru, ruční zásah, nebo „počkat
na NT“). Piš česky, stručně. Nic sám neměň – jen poradíš. Parametry uváděj přesnými
klíči z nastavení (např. deadline_earliest, off_delay_s).

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
