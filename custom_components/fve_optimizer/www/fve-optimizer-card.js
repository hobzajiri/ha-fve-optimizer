/*
 * FVE Optimizer card – power flow + decision of the FVE Optimizer integration.
 *
 *   type: custom:fve-optimizer-card
 *   entity: sensor.fve_optimizer_status   # the optimizer "Status" sensor
 *
 * Reads the "data" attribute (refreshed every dispatch cycle).
 */

const T = {
  cs: {
    pv: "FV", grid: "Síť", battery: "Baterie", house: "Dům",
    import: "ze sítě", export: "do sítě", charging: "nabíjí", discharging: "vybíjí", idle: "klid",
    target: "cíl", surplus: "Přebytek", allocated: "rozděleno", exportRaised: "Limit přetoku zvýšen",
    exportNormal: "Limit přetoku běžný", nt: "NT (HDO)", vt: "VT", borrow: "Dorovnání z baterie",
    forecast: "Predikce", need: "potřeba", breaker: "Jistič", noData: "Čekám na data z FVE Optimizeru…",
    urgent: "termín", minFirst: "před baterií", atRisk: "nestihne", plan: "plán",
    batteryFirst: "Přednost baterie", devicesFirst: "Přednost zařízení",
    dryRun: "Jen sledování – nic se nespíná", failsafe: "Pojistka – chybí data ze střídače",
  },
  en: {
    pv: "PV", grid: "Grid", battery: "Battery", house: "House",
    import: "import", export: "export", charging: "charging", discharging: "discharging", idle: "idle",
    target: "target", surplus: "Surplus", allocated: "allocated", exportRaised: "Export limit raised",
    exportNormal: "Export limit normal", nt: "Low tariff", vt: "High tariff", borrow: "Rounding up from battery",
    forecast: "Forecast", need: "need", breaker: "Breaker", noData: "Waiting for FVE Optimizer data…",
    urgent: "deadline", minFirst: "before battery", atRisk: "at risk", plan: "plan",
    batteryFirst: "Battery first", devicesFirst: "Devices first",
    dryRun: "Watch only – nothing is switched", failsafe: "Fail-safe – no inverter data",
  },
};

const ICON = {
  pv: "mdi:solar-power-variant", grid: "mdi:transmission-tower", house: "mdi:home",
  battery: "mdi:home-battery", switched: "mdi:water-boiler", ev_charger: "mdi:car-electric",
};

const fmtW = (w) => {
  const v = Math.abs(Number(w) || 0);
  return v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1).replace(".", ",")} kW` : `${Math.round(v)} W`;
};
const num = (v, d = 1) => (v == null ? "?" : Number(v).toFixed(d).replace(".", ","));

class FveOptimizerCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("entity is required (sensor …_status of FVE Optimizer)");
    this._config = config;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  getCardSize() {
    return 7;
  }

  static getStubConfig(hass) {
    const id = Object.keys(hass.states).find(
      (e) => e.startsWith("sensor.") && hass.states[e].attributes.data?.devices
    );
    return { entity: id || "sensor.fve_optimizer_status" };
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._config.entity];
    const data = state?.attributes?.data;
    const key = data ? JSON.stringify(data) : "none";
    if (key === this._last) return;
    this._last = key;
    this._render(data, (hass.locale?.language || hass.language || "en").startsWith("cs") ? T.cs : T.en);
  }

  _render(d, t) {
    const root = this.shadowRoot;
    if (!d || !d.devices) {
      root.innerHTML = `<ha-card><div class="empty">${t.noData}</div></ha-card>${STYLE}`;
      return;
    }
    const grid = Number(d.grid_w) || 0; // + import
    const bat = Number(d.battery_w) || 0; // + charging
    const devices = d.devices || [];
    const devW = devices.reduce((s, x) => s + (Number(x.actual_w) || 0), 0);
    const pv = d.pv_w != null ? Number(d.pv_w) : Math.max(devW + bat - grid, 0);
    const house = d.house_w != null ? Math.max(Number(d.house_w) - (d.managed_w || 0), 0)
      : Math.max(pv + grid - bat - devW, 0);

    // Layout (viewBox 0 0 420 H)
    const H = devices.length ? 322 : 210;
    const C = { x: 210, y: 140 };
    const P = { pv: { x: 210, y: 38 }, grid: { x: 52, y: 140 }, battery: { x: 368, y: 140 } };
    const step = devices.length > 1 ? 260 / (devices.length - 1) : 0;
    const devPos = devices.map((_, i) => ({
      x: devices.length > 1 ? 80 + i * step : 210, y: 262,
    }));

    const flow = (a, b, w, color, label, labelPos) => {
      const on = Math.abs(w) > 30;
      const dir = w >= 0 ? "" : " rev";
      return `
        <line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" class="track"/>
        ${on ? `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" class="flow${dir}" style="stroke:${color}"/>` : ""}
        ${on ? `<text x="${labelPos.x}" y="${labelPos.y}" class="fl" style="fill:${color}">${label}</text>` : ""}`;
    };

    // side = "below" (default), "right" or "upright" – away from the lines.
    const node = (p, icon, color, title, value, extra = "", side = "below") => {
      const right = side === "right" || side === "upright";
      const tx = right ? p.x + 34 : p.x;
      const ty = side === "upright" ? p.y - 34 : right ? p.y - 2 : p.y + 42;
      const anchor = right ? "start" : "middle";
      return `
      <g>
        <circle cx="${p.x}" cy="${p.y}" r="25" class="node" style="stroke:${color}"/>
        ${extra}
        <foreignObject x="${p.x - 12}" y="${p.y - 12}" width="24" height="24">
          <ha-icon icon="${icon}" style="color:${color};--mdc-icon-size:24px"></ha-icon>
        </foreignObject>
        <text x="${tx}" y="${ty}" class="nt" style="text-anchor:${anchor}">${title}</text>
        ${value ? `<text x="${tx}" y="${ty + 14}" class="nv" style="text-anchor:${anchor}">${value}</text>` : ""}
      </g>`;
    };

    // Battery SoC ring + target tick
    const soc = Math.max(0, Math.min(100, Number(d.battery_soc) || 0));
    const R = 29, circ = 2 * Math.PI * R;
    const tgt = Math.max(0, Math.min(100, Number(d.battery_target_soc) || 0));
    const ta = (tgt / 100) * 2 * Math.PI - Math.PI / 2;
    const ring = `
      <circle cx="${P.battery.x}" cy="${P.battery.y}" r="${R}" class="ringbg"/>
      <circle cx="${P.battery.x}" cy="${P.battery.y}" r="${R}" class="ring"
        stroke-dasharray="${(soc / 100) * circ} ${circ}" transform="rotate(-90 ${P.battery.x} ${P.battery.y})"/>
      <line x1="${P.battery.x + (R - 5) * Math.cos(ta)}" y1="${P.battery.y + (R - 5) * Math.sin(ta)}"
            x2="${P.battery.x + (R + 5) * Math.cos(ta)}" y2="${P.battery.y + (R + 5) * Math.sin(ta)}" class="tick"/>`;

    const cPV = "var(--warning-color, #ff9800)";
    const cImp = "var(--error-color, #db4437)";
    const cExp = "var(--success-color, #43a047)";
    const cBat = "var(--info-color, #039be5)";
    const cDev = "var(--primary-color, #03a9f4)";
    const cUrg = "var(--error-color, #db4437)";

    const svg = `
      <svg viewBox="0 0 420 ${H}" role="img">
        ${flow(P.pv, C, pv, cPV, "", { x: 0, y: 0 })}
        ${flow(P.grid, C, grid, grid >= 0 ? cImp : cExp, fmtW(grid), { x: 125, y: 128 })}
        ${flow(C, P.battery, bat, cBat, fmtW(bat), { x: 300, y: 128 })}
        ${devices.map((x, i) => flow(C, devPos[i], x.actual_w, x.urgent ? cUrg : cDev, fmtW(x.actual_w),
          { x: (C.x + devPos[i].x) / 2 + (devPos[i].x < C.x ? -14 : devPos[i].x > C.x ? 14 : 30), y: (C.y + devPos[i].y) / 2 + 4 })).join("")}
        ${node(P.pv, ICON.pv, cPV, t.pv, fmtW(pv), "", "right")}
        ${node(P.grid, ICON.grid, grid >= 0 ? cImp : cExp, t.grid,
          Math.abs(grid) > 30 ? (grid > 0 ? t.import : t.export) : t.idle)}
        ${node(P.battery, ICON.battery, cBat, `${t.battery} ${Math.round(soc)} %`,
          `${t.target} ${Math.round(tgt)} %`, ring)}
        ${node(C, ICON.house, "var(--primary-text-color)", t.house, fmtW(house), "", devices.length ? "upright" : "below")}
        ${devices.map((x, i) => node(devPos[i], ICON[x.kind] || "mdi:power-plug",
          x.active ? (x.urgent ? cUrg : cDev) : "var(--disabled-text-color, #9e9e9e)", x.name, "")).join("")}
      </svg>`;

    const chip = (text, cls = "") => `<span class="chip ${cls}">${text}</span>`;
    const chips = [
      d.dry_run ? chip(t.dryRun, "info") : "",
      d.reason === "failsafe" ? chip(t.failsafe, "warn") : "",
      chip(d.battery_priority ? t.batteryFirst : t.devicesFirst, d.battery_priority ? "warn" : "ok"),
      chip(`${t.surplus} ${fmtW(d.budget_w)} · ${t.allocated} ${fmtW(d.allocated_w)}`),
      d.forecast_kwh != null
        ? chip(`${t.forecast} ${num(d.forecast_kwh)} / ${t.need} ${num(d.forecast_need_kwh)} kWh ${d.forecast_covers ? "✔" : "✘"}`,
          d.forecast_covers ? "ok" : "warn") : "",
      chip(d.export_raised ? t.exportRaised : t.exportNormal),
      d.hdo != null ? chip(d.hdo ? t.nt : t.vt, d.hdo ? "ok" : "") : "",
      d.borrow ? chip(t.borrow, "info") : "",
      d.headroom_a != null ? chip(`${t.breaker} ${num(d.headroom_a)} A`, d.headroom_a < 3 ? "warn" : "") : "",
    ].join("");

    const rows = devices.map((x) => {
      const det = [];
      if (x.active && x.current) det.push(`${x.phases}f · ${x.current} A`);
      if (x.temperature != null) det.push(`${num(x.temperature)} °C`);
      if (x.soc != null) det.push(`SoC ${Math.round(x.soc)} %`);
      if (x.plan && x.plan.length) det.push(`${t.plan} ${x.plan.join(", ")}`);
      const tags = [
        x.urgent ? `<span class="tag urg">⚡ ${t.urgent}</span>` : "",
        x.min_first ? `<span class="tag min">⬆ ${t.minFirst}</span>` : "",
        x.at_risk ? `<span class="tag urg">⚠ ${t.atRisk}</span>` : "",
      ].join("");
      return `
        <div class="row ${x.active ? "on" : ""}">
          <ha-icon icon="${ICON[x.kind] || "mdi:power-plug"}"></ha-icon>
          <div class="main">
            <div class="name">${x.name} <span class="state">${x.state}</span> ${tags}</div>
            ${det.length ? `<div class="det">${det.join(" · ")}</div>` : ""}
          </div>
          <div class="pw">${x.active ? fmtW(x.allocated_w) : "–"}</div>
        </div>`;
    }).join("");

    const time = d.changed_at ? new Date(d.changed_at).toLocaleTimeString() : "";
    root.innerHTML = `
      <ha-card>
        ${this._config.title !== false ? `<h1 class="title">${this._config.title || "FVE Optimizer"}</h1>` : ""}
        <div class="headline">${d.headline || ""}</div>
        ${svg}
        <div class="chips">${chips}</div>
        <div class="rows">${rows}</div>
        <div class="foot">${time}</div>
      </ha-card>${STYLE}`;
  }
}

const STYLE = `<style>
  ha-card { padding: 12px 16px 10px; }
  .title { font-size: 20px; font-weight: 400; margin: 4px 0 2px; }
  .headline { color: var(--secondary-text-color); font-size: 13px; margin-bottom: 4px; }
  .empty { padding: 16px; color: var(--secondary-text-color); }
  svg { width: 100%; height: auto; display: block; }
  .track { stroke: var(--divider-color, #ccc); stroke-width: 2; }
  .flow { stroke-width: 3; stroke-dasharray: 3 9; stroke-linecap: round; animation: dash 1.2s linear infinite; }
  .flow.rev { animation-direction: reverse; }
  @keyframes dash { to { stroke-dashoffset: -24; } }
  .node { fill: var(--card-background-color, #fff); stroke-width: 2; }
  .ringbg { fill: none; stroke: var(--divider-color, #ddd); stroke-width: 4; }
  .ring { fill: none; stroke: var(--info-color, #039be5); stroke-width: 4; stroke-linecap: round; }
  .tick { stroke: var(--primary-text-color); stroke-width: 2; }
  .nt { font-size: 12px; text-anchor: middle; fill: var(--primary-text-color); }
  .nv { font-size: 11px; text-anchor: middle; fill: var(--secondary-text-color); }
  .fl { font-size: 11px; font-weight: 500; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 10px; }
  .chip { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: var(--secondary-background-color);
    color: var(--primary-text-color); }
  .chip.ok { background: rgba(67,160,71,.15); color: var(--success-color, #43a047); }
  .chip.warn { background: rgba(255,152,0,.15); color: var(--warning-color, #ff9800); }
  .chip.info { background: rgba(3,155,229,.15); color: var(--info-color, #039be5); }
  .rows { display: flex; flex-direction: column; gap: 6px; }
  .row { display: flex; align-items: center; gap: 10px; padding: 6px 8px; border-radius: 8px;
    background: var(--secondary-background-color); opacity: .75; }
  .row.on { opacity: 1; }
  .row ha-icon { color: var(--secondary-text-color); --mdc-icon-size: 22px; }
  .row.on ha-icon { color: var(--primary-color); }
  .main { flex: 1; min-width: 0; }
  .name { font-size: 14px; }
  .state { color: var(--secondary-text-color); font-size: 13px; margin-left: 4px; }
  .det { color: var(--secondary-text-color); font-size: 12px; }
  .pw { font-weight: 500; font-size: 14px; white-space: nowrap; }
  .tag { font-size: 11px; padding: 1px 6px; border-radius: 8px; margin-left: 4px; }
  .tag.urg { background: rgba(219,68,55,.15); color: var(--error-color, #db4437); }
  .tag.min { background: rgba(3,155,229,.15); color: var(--info-color, #039be5); }
  .foot { text-align: right; font-size: 11px; color: var(--secondary-text-color); margin-top: 6px; }
</style>`;

customElements.define("fve-optimizer-card", FveOptimizerCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "fve-optimizer-card",
  name: "FVE Optimizer",
  description: "Power flow and decisions of the FVE Optimizer integration.",
});
