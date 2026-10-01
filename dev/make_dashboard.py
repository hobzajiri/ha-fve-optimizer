"""Generate the dev dashboard from the entity registry.

Entity IDs depend on the HA language and areas (e.g. "kuchyne_…"), so the
dashboard is built from the unique IDs of FVE Optimizer entities.

    docker exec -i fve-optimizer-dev python3 - < make_dashboard.py

Then reload the browser (the dashboard is in YAML mode, no restart needed
after the first one).
"""

import json
from pathlib import Path

import yaml

CONFIG = Path("/config")
registry = json.loads((CONFIG / ".storage/core.entity_registry").read_text())["data"]["entities"]
entries = json.loads((CONFIG / ".storage/core.config_entries").read_text())["data"]["entries"]

entry = next(e for e in entries if e["domain"] == "fve_optimizer")
entry_id = entry["entry_id"]
subentries = {s["subentry_id"]: s for s in entry.get("subentries", [])}

by_uid = {
    e["unique_id"]: e["entity_id"]
    for e in registry
    if e["platform"] == "fve_optimizer" and e["config_entry_id"] == entry_id
}


def hub(key: str) -> str | None:
    return by_uid.get(f"{entry_id}_{key}")


def dev(subentry_id: str, key: str) -> str | None:
    return by_uid.get(f"{entry_id}_{subentry_id}_{key}")


def only(*ids):
    return [i for i in ids if i]


def entities_card(title, ids):
    ids = only(*ids)
    return {"type": "entities", "title": title, "entities": ids} if ids else None


decision = hub("last_decision")
cards = []

# Graphical card shipped with the integration (power flow + decision).
if hub("status"):
    cards.append({"type": "custom:fve-optimizer-card", "entity": hub("status")})

cards.append(
    {
        "type": "entities",
        "title": "Simulátor",
        "entities": [
            "input_number.sim_pv_available",
            "input_number.sim_house_load",
            "input_number.sim_battery_soc",
            "input_number.sim_water_temp",
            "input_number.sim_forecast_remaining",
            "input_number.sim_speed",
            "input_boolean.sim_ev_connected",
            "input_boolean.sim_hdo",
            {"type": "section", "label": "Ovládá integrace"},
            "input_number.sim_export_limit",
            "input_boolean.sim_boiler",
            "input_boolean.sim_ev_charge",
            "input_boolean.sim_ev_3phase",
            "input_number.sim_ev_current",
        ],
    }
)
cards.append(
    {
        "type": "history-graph",
        "title": "Toky energie (2 h)",
        "hours_to_show": 2,
        "entities": [
            "sensor.sim_pv_power",
            "sensor.sim_grid_power",
            "sensor.sim_battery_power",
            "sensor.sim_load",
            "sensor.sim_boiler_power",
            "sensor.sim_ev_power",
        ],
    }
)
DECISION_TEMPLATE = """
{%- macro w(v) -%}{{ '{:,.0f}'.format(v | float(0)).replace(',', ' ') }} W{%- endmacro -%}
{%- macro n(v) -%}{{ (v | float(0) | round(1) | string).replace('.', ',') }}{%- endmacro -%}
{%- set d = state_attr('ENTITY', 'data') -%}
{%- if not d -%}
Zatím žádné rozhodnutí.
{%- else -%}
<ha-alert alert-type="{{ 'warning' if d.battery_priority else 'success' }}">{{ d.headline }}</ha-alert>

| | |
|:--|--:|
| Síť | {% if d.grid_w is none %}?{% elif d.grid_w < -50 %}↑ {{ w(-d.grid_w) }} do sítě{% elif d.grid_w > 50 %}↓ {{ w(d.grid_w) }} ze sítě{% else %}≈ 0 W{% endif %} |
| Baterie | {{ d.battery_soc | round(0) }} % → cíl {{ d.battery_target_soc | round(0) }} % · {% if d.battery_w is none %}?{% elif d.battery_w > 50 %}nabíjí {{ w(d.battery_w) }}{% elif d.battery_w < -50 %}vybíjí {{ w(-d.battery_w) }}{% else %}klid{% endif %} |
| Přebytek | {{ w(d.budget_w) }} · rozděleno {{ w(d.allocated_w) }} |
{%- if d.forecast_kwh is not none %}
| Predikce | {{ n(d.forecast_kwh) }} kWh / potřeba {{ n(d.forecast_need_kwh) }} kWh {{ '✔' if d.forecast_covers else '✘' }} |
{%- endif %}
| Limit přetoku | {{ 'zvýšen' if d.export_raised else 'běžný' }}{{ ' · dorovnání z baterie' if d.borrow else '' }} |
{%- if d.hdo is not none %}
| Tarif | {{ 'NT (HDO)' if d.hdo else 'VT' }} |
{%- endif %}
{%- if d.headroom_a is not none %}
| Rezerva jističe | {{ n(d.headroom_a) }} A |
{%- endif %}

| Zařízení | Stav | Výkon | Detail |
|:--|:--|--:|:--|
{%- for x in d.devices %}
| {{ '**' ~ x.name ~ '**' if x.active else x.name }} | {{ x.state }}{{ ' ⚡' if x.urgent else '' }}{{ ' ⬆︎' if x.min_first else '' }} | {{ w(x.allocated_w) if x.active else '–' }} | {% set p = [] %}{% if x.current and x.active %}{% set p = p + [x.phases ~ 'f · ' ~ x.current ~ ' A'] %}{% endif %}{% if x.temperature is not none %}{% set p = p + [n(x.temperature) ~ ' °C'] %}{% endif %}{% if x.soc is not none %}{% set p = p + ['SoC ' ~ x.soc ~ ' %'] %}{% endif %}{% if x.plan %}{% set p = p + ['plán ' ~ x.plan | join(', ')] %}{% endif %}{% if x.at_risk %}{% set p = p + ['⚠ nestihne'] %}{% endif %}{{ p | join(' · ') }} |
{%- endfor %}

<small>Změněno {{ as_timestamp(d.changed_at) | timestamp_custom('%H:%M:%S') }} · ⚡ termín (i ze sítě) · ⬆︎ minimum před baterií</small>

<details><summary>Podrobnosti</summary>

{% for l in state_attr('ENTITY', 'details') or [] %}`{{ l }}`<br>{% endfor %}
</details>
{%- endif -%}
"""

if decision:
    cards.append(
        {
            "type": "markdown",
            "title": "Poslední rozhodnutí",
            "content": DECISION_TEMPLATE.replace("ENTITY", decision).strip(),
        }
    )
cards.append(
    entities_card(
        "Optimizer",
        [
            hub("enabled"),
            hub("status"),
            hub("budget"),
            hub("allocated"),
            hub("managed"),
            hub("effective_target_soc"),
            hub("battery_priority"),
            hub("forecast_covers_battery"),
            hub("export_limit_raised"),
            hub("hdo"),
            hub("breaker_headroom"),
        ],
    )
)

device_cards = []
for subentry_id, sub in subentries.items():
    keys = [
        "control", "reason", "allocated", "active", "priority",
        # boiler
        "nominal_power_w", "max_temperature", "max_temperature_hysteresis",
        "deadline_enabled", "deadline_time", "deadline_temperature",
        "deadline_hdo_only", "deadline_earliest",
        "legionella_enabled", "legionella_temperature", "legionella_interval_days",
        # EV
        "min_current", "max_current", "phases",
        "ev_deadline_enabled", "ev_deadline_time", "ev_deadline_soc", "ev_deadline_hdo_only",
    ]
    card = entities_card(sub["title"], [dev(subentry_id, k) for k in keys])
    if card:
        device_cards.append(card)

settings = entities_card(
    "Nastavení baterie a řízení",
    [
        hub(k)
        for k in (
            "battery_target_soc", "night_target", "night_power_w", "night_extra_hours",
            "battery_reserve_soc", "forecast_min_soc", "forecast_safety_factor",
            "export_limit_control", "export_limit_normal", "export_limit_raised",
            "reserve_w", "main_breaker_a", "update_interval",
        )
    ],
)

dashboard = {
    "title": "FVE Optimizer",
    "views": [
        {
            "title": "Ladění",
            "path": "ladeni",
            "type": "masonry",
            "cards": [c for c in cards + device_cards + [settings] if c],
        }
    ],
}

out = CONFIG / "dashboards/fve.yaml"
out.parent.mkdir(exist_ok=True)
out.write_text(
    "# Generated by dev/make_dashboard.py – do not edit, regenerate instead.\n"
    + yaml.safe_dump(dashboard, allow_unicode=True, sort_keys=False)
)
print(f"Written {out} ({len(dashboard['views'][0]['cards'])} cards)")
missing = [k for k in ("last_decision", "hdo") if not hub(k)]
if missing:
    print("Not yet created (restart HA after updating the integration):", ", ".join(missing))
