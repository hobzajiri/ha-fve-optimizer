/*
 * FVE Optimizer card – decisions of the FVE Optimizer integration (state,
 * recommendations, devices, log; optional power flow diagram).
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
    forecast: "Predikce", need: "potřeba", forecastOk: "pokryje baterii", forecastShort: "nestačí na baterii",
    breaker: "Jistič", noData: "Čekám na data z FVE Optimizeru…",
    urgent: "termín", minFirst: "před baterií", atRisk: "nestihne", plan: "plán",
    batteryFirst: "Přednost baterie", devicesFirst: "Přednost zařízení",
    dryRun: "Jen sledování – povely proveď ručně", failsafe: "Pojistka – chybí data ze střídače",
    stale: "Stará data – senzory nedostupné",
    recs: "Doporučení", doIt: "Provést", doAll: "Provést vše", since: "od",
    device: "Zařízení", wanted: "Doporučeno", now: "Teď", on: "Zap", off: "Vyp",
    charge: "Nabíjet", noCharge: "Nenabíjet", exportLimit: "Limit přetoku", manual: "proveď ručně",
    decisions: "Rozhodnutí", planned: "doporučeno",
    mode: "Režim", auto: "Řídí automaticky", priority: "Priorita", prioBattery: "baterie",
    prioDevices: "zařízení", tariff: "Tarif", raised: "zvýšený", normal: "běžný", reserve: "rezerva",
    borrowShort: "dorovnání z baterie", turnOn: "zapnout", turnOff: "vypnout", stop: "zastavit nabíjení",
    setTo: "nastavit", inProgress: "provádí se", manualHint: "Doporučení proveď ručně",
    until: "do", then: "pak", price: "Cena", today: "dnes", notControlled: "neřízeno",
    available: "Návrh", availableHint: "Kolik chce Optimizer dát řízeným zařízením. Zahrnuje i výkon, který už teď berou (ten se jim může sebrat a přerozdělit) – proto může být návrh větší než samotný přetok do sítě.",
    allocatedRow: "Rozděleno", allocatedHint: "Součet výkonu, který Optimizer právě navrhuje řízeným zařízením.",
    rest: "zbytek", restHint: "Co z návrhu zařízení nevyužijí – zůstane baterii nebo půjde do sítě.",
    toBattery: "baterii", toBatteryGrid: "baterii / síť",
    forecastHint: "Dnešní predikce výroby oproti energii, kterou ještě potřebuje baterie do cíle.",
    tariffHint: "Aktuální tarif HDO a kdy se přepne.",
    priceHint: "Cena elektřiny ze sítě podle aktuálního tarifu (NT/VT).",
    gridHint: "Výkon na elektroměru: ze sítě = odběr, do sítě = přetok.",
    batteryHint: "Stav baterie. Cíl SoC určuje, kdy mají zařízení přednost před nabíjením.",
    exportHint: "Limit přetoku na střídači. Optimizer ho může dočasně zvednout, když je výhodný přebytek.",
    deviceHint: "Teď = skutečný odběr. Návrh = co Optimizer chce nastavit.",
    prioBatHint: "Baterie má přednost – zařízení dostanou jen přebytek nad nabíjením baterie.",
    prioDevHint: "Zařízení mají přednost – mohou brát přebytek dřív, než se nabije baterie na cíl.",
    borrowHint: "Zařízení s termínem nebo minimem smí na chvíli brát i výkon, který by jinak šel do baterie.",
    urgentHint: "Musí doběhnout do nastaveného termínu.",
    minFirstHint: "Ještě není hotové povinné minimum – smí běžet i při přednosti baterie.",
    atRiskHint: "Do termínu to podle současného výkonu nestíhá.",
    nowLabel: "teď", wantLabel: "návrh",
    prioShortBat: "přednost baterie", prioShortDev: "přednost zařízení",
    realOff: "vypnuto", realOn: "zapnuto", realRun: "běží", realCharge: "nabíjí",
    review: "AI hodnocení", reviewNow: "Vyhodnotit nyní", reviewing: "Vyhodnocuji…", noReview: "Zatím žádné hodnocení.",
    reviewOff: "AI hodnocení není nastavené – vyber AI Task entitu v nastavení FVE Optimizeru (krok Řízení).",
    good: "Co fungovalo", problems: "Problémy", suggestions: "Návrhy úprav", watchOnlyDay: "den v režimu Jen sledovat",
    statsHint: "Spotřeba dnes, náklady za energii ze sítě (NT/VT) a podíl ze slunce",
    outlook: "Předpoklad dne", outlookHint: "Co Optimizer očekává do konce dne z predikce, termínů a HDO – ne AI odhad.",
    outlookSurplus: "jen při přebytku", outlookSolar: "pokryje slunce", outlookMet: "minimum splněno",
    outlookFrom: "od", aiOutlook: "Zbytek dne",
    chargeOrder: "objednávka", boost: "rychlé nabíjení", eta: "hotovo cca",
    orderSoc: "Cíl %", orderWhen: "Termín", orderCreate: "Objednat", orderClear: "Zrušit objednávku",
    boostStart: "Rychle teď", boostStop: "Stop rychlé",
    holdHint: "Do 80 % dřív · 80–100 % až těsně před termínem · Rychlé nabíjení zruší objednávku",
    orderOpen: "Nabíjení", orderModalTitle: "Nabíjení auta", orderClose: "Zavřít",
    orderError: "Nepodařilo se uložit – zkus to znovu",
  },
  en: {
    pv: "PV", grid: "Grid", battery: "Battery", house: "House",
    import: "import", export: "export", charging: "charging", discharging: "discharging", idle: "idle",
    target: "target", surplus: "Surplus", allocated: "allocated", exportRaised: "Export limit raised",
    exportNormal: "Export limit normal", nt: "Low tariff", vt: "High tariff", borrow: "Rounding up from battery",
    forecast: "Forecast", need: "need", forecastOk: "covers battery", forecastShort: "short of battery",
    breaker: "Breaker", noData: "Waiting for FVE Optimizer data…",
    urgent: "deadline", minFirst: "before battery", atRisk: "at risk", plan: "plan",
    batteryFirst: "Battery first", devicesFirst: "Devices first",
    dryRun: "Watch only – nothing is switched", failsafe: "Fail-safe – no inverter data",
    stale: "Stale data – sensors unavailable",
    recs: "Recommendations", doIt: "Do it", doAll: "Do all", since: "since",
    device: "Device", wanted: "Recommended", now: "Now", on: "On", off: "Off",
    charge: "Charge", noCharge: "Don't charge", exportLimit: "Export limit", manual: "do by hand",
    decisions: "Decisions", planned: "recommended",
    mode: "Mode", auto: "Automatic control", priority: "Priority", prioBattery: "battery",
    prioDevices: "devices", tariff: "Tariff", raised: "raised", normal: "normal", reserve: "headroom",
    borrowShort: "rounding up from battery", turnOn: "turn on", turnOff: "turn off", stop: "stop charging",
    setTo: "set", inProgress: "in progress", manualHint: "Carry out the recommendations by hand",
    until: "until", then: "then", price: "Price", today: "today", notControlled: "not controlled",
    available: "Plan", availableHint: "How much the Optimizer wants to give managed devices. Includes power they already draw (it can be taken back and reallocated) – so the plan can be larger than grid export alone.",
    allocatedRow: "Allocated", allocatedHint: "Sum of power the Optimizer currently proposes for managed devices.",
    rest: "rest", restHint: "What devices do not take from the plan – left for the battery or the grid.",
    toBattery: "battery", toBatteryGrid: "battery / grid",
    forecastHint: "Today’s production forecast versus energy the battery still needs to reach its target.",
    tariffHint: "Current time-of-use tariff and when it switches.",
    priceHint: "Grid electricity price for the current tariff (low/high).",
    gridHint: "Meter power: import from grid, or export to grid.",
    batteryHint: "Battery state. Target SoC decides when devices outrank charging.",
    exportHint: "Inverter export limit. The Optimizer may raise it temporarily when surplus is useful.",
    deviceHint: "Now = actual draw. Plan = what the Optimizer wants to set.",
    prioBatHint: "Battery first – devices only get surplus beyond battery charging.",
    prioDevHint: "Devices first – they may take surplus before the battery reaches its target.",
    borrowHint: "Deadline or minimum devices may briefly use power that would otherwise charge the battery.",
    urgentHint: "Must finish by the configured deadline.",
    minFirstHint: "Required minimum not done yet – may run even when the battery has priority.",
    atRiskHint: "At the current rate it will miss the deadline.",
    nowLabel: "now", wantLabel: "plan",
    prioShortBat: "battery first", prioShortDev: "devices first",
    realOff: "off", realOn: "on", realRun: "running", realCharge: "charging",
    review: "AI review", reviewNow: "Review now", reviewing: "Reviewing…", noReview: "No review yet.",
    reviewOff: "AI review is not set up – choose an AI Task entity in the FVE Optimizer settings (Control step).",
    good: "What worked", problems: "Problems", suggestions: "Suggested changes", watchOnlyDay: "watch-only day",
    statsHint: "Consumption today, cost of grid energy (NT/VT) and solar share",
    outlook: "Today’s outlook", outlookHint: "What the Optimizer expects for the rest of the day from forecast, deadlines and HDO – not an AI guess.",
    outlookSurplus: "surplus only", outlookSolar: "covered by sun", outlookMet: "minimum met",
    outlookFrom: "from", aiOutlook: "Rest of day",
    chargeOrder: "order", boost: "fast charge", eta: "ready ~",
    orderSoc: "Target %", orderWhen: "Deadline", orderCreate: "Order", orderClear: "Clear order",
    boostStart: "Fast now", boostStop: "Stop boost",
    holdHint: "To 80 % earlier · 80–100 % only just before the deadline · Fast charge clears the order",
    orderOpen: "Charge", orderModalTitle: "EV charging", orderClose: "Close",
    orderError: "Could not save – try again",
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
const num = (v, d = 1) => (v == null || Number.isNaN(Number(v)) ? "?" : Number(v).toFixed(d).replace(".", ","));
const esc = (x) => String(x ?? "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
// Survives script reloads (customElements.define cannot replace the class).
const INSTANCES = (window.__fveOptimizerCards = window.__fveOptimizerCards || new Set());

class FveOptimizerCard extends HTMLElement {
  connectedCallback() {
    INSTANCES.add(this);
    if (!this._evEscBound) {
      this._evEscBound = (ev) => {
        if (ev.key === "Escape") this._closeEvModal?.();
      };
      window.addEventListener("keydown", this._evEscBound);
    }
  }

  disconnectedCallback() {
    INSTANCES.delete(this);
    if (this._evEscBound) {
      window.removeEventListener("keydown", this._evEscBound);
      this._evEscBound = null;
    }
  }

  setConfig(config) {
    if (!config?.entity) throw new Error("entity is required (sensor …_status of FVE Optimizer)");
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
    if (!hass) return;
    this._hass = hass;
    const state = hass.states?.[this._config?.entity];
    const data = state?.attributes?.data;
    let key = "none";
    try { key = data ? JSON.stringify(data) : "none"; } catch { key = `err-${Date.now()}`; }
    if (key === this._last) return;
    this._last = key;
    const lang = hass.locale?.language || hass.language || "en";
    this._render(data, String(lang).startsWith("cs") ? T.cs : T.en);
  }

  _render(d, t) {
    const root = this.shadowRoot;
    if (!root) return;
    try {
      this._renderInner(d, t || T.en);
    } catch (err) {
      console.error("fve-optimizer-card", err);
      const msg = (t && t.noData) || T.en.noData;
      root.innerHTML = `<ha-card><div class="empty">${msg}<br><small>${esc(err?.message || err)}</small></div></ha-card>${STYLE}`;
    }
  }

  _renderInner(d, t) {
    const root = this.shadowRoot;
    // Preserve in-progress modal edits across coordinator re-renders.
    if (this._evModalId) {
      const soc = root.querySelector?.(".ord-soc")?.value;
      const when = root.querySelector?.(".ord-when")?.value;
      if (soc != null || when != null) {
        this._evModalDraft = { id: this._evModalId, soc, when };
      }
    }
    if (!d || !Array.isArray(d.devices)) {
      root.innerHTML = `<ha-card><div class="empty">${t.noData}</div></ha-card>${STYLE}`;
      return;
    }
    const grid = Number(d.grid_w) || 0; // + import
    const bat = Number(d.battery_w) || 0; // + charging
    const devices = d.devices.filter(Boolean);
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

    const langRaw = this._hass?.locale?.language || this._hass?.language;
    const lang = langRaw && String(langRaw).trim() ? String(langRaw) : undefined;
    let tf;
    try { tf = new Intl.DateTimeFormat(lang, { hour: "2-digit", minute: "2-digit" }); }
    catch { tf = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }); }
    const hhmm = (iso) => {
      if (!iso) return "";
      const dt = new Date(iso);
      if (Number.isNaN(dt.getTime())) return "";
      try { return tf.format(dt); } catch { return ""; }
    };

    // --- Context tiles: forecast, tariff, price --------------------------------
    const tariffTile = () => {
      if (d.hdo == null) return null;
      const nt = d.hdo === true;
      const win = d.hdo_window, next = d.hdo_next_window;
      let sub = "";
      if (nt && win) {
        sub = `${t.until} ${hhmm(win[1])}${next ? ` · ${t.then} VT ${t.until} ${hhmm(next[0])}` : ""}`;
      } else if (!nt && next) {
        sub = `${t.until} ${hhmm(next[0])} · ${t.then} NT ${hhmm(next[0])}–${hhmm(next[1])}`;
      }
      return { label: t.tariff, value: nt ? "NT" : "VT", sub, cls: nt ? "ok" : "", hint: t.tariffHint };
    };
    const priceTile = () => {
      if (!d.price_vt && !d.price_nt) return null;
      const nt = d.hdo === true;
      const cur = d.hdo == null ? null : nt ? d.price_nt : d.price_vt;
      const other = nt ? d.price_vt : d.price_nt;
      if (cur != null) {
        return {
          label: t.price,
          value: `${num(cur, 2)} Kč`,
          sub: other != null ? `${nt ? "VT" : "NT"} ${num(other, 2)} Kč/kWh` : "Kč/kWh",
          hint: t.priceHint,
        };
      }
      return {
        label: t.price,
        value: `${num(d.price_nt, 2)} / ${num(d.price_vt, 2)}`,
        sub: "NT / VT Kč/kWh",
        hint: t.priceHint,
      };
    };

    // --- One vertical stack: grid, battery, devices ---------------------------
    const unit = d.export_limit_unit ? ` ${d.export_limit_unit}` : "";
    const g = Number(d.grid_w);
    const gridIdle = !Number.isFinite(g) || Math.abs(g) < 30;
    const batW = Number(d.battery_w) || 0;
    const batSoc = Math.round(Number(d.battery_soc) || 0);
    const batTgt = Math.round(Number(d.battery_target_soc) || 0);
    const chip = (text, cls = "", hint = "") => text
      ? `<span class="chip ${cls}"${hint ? ` title="${esc(hint)}"` : ""}>${text}</span>` : "";
    const modeChip = d.stale || d.reason === "missing_input" ? chip(t.stale, "warn")
      : d.reason === "failsafe" ? chip(t.failsafe, "warn")
      : d.dry_run ? chip(t.dryRun, "info") : chip(t.auto, "ok");
    const metaTiles = [
      d.forecast_kwh != null ? {
        label: t.forecast,
        value: `${num(d.forecast_kwh)} / ${num(d.forecast_need_kwh)}`,
        sub: `kWh · ${d.forecast_covers ? t.forecastOk : t.forecastShort}`,
        cls: d.forecast_covers ? "ok" : "warn",
        hint: t.forecastHint,
      } : null,
      tariffTile(),
      priceTile(),
    ].filter(Boolean);
    const metaHtml = !metaTiles.length ? "" : `
      <div class="meta">
        ${metaTiles.map((m) => `
          <div class="meta-tile ${m.cls || ""}"${m.hint ? ` title="${esc(m.hint)}"` : ""}>
            <div class="meta-label">${m.label}</div>
            <div class="meta-value">${m.value}</div>
            ${m.sub ? `<div class="meta-sub">${m.sub}</div>` : ""}
          </div>`).join("")}
      </div>`;

    const budgetHtml = (() => {
      if (d.budget_w == null && !d.budget_parts) return "";
      const budget = Number(d.budget_w) || 0;
      const allocated = Number(d.allocated_w) || 0;
      const leftover = Math.max(budget - allocated, 0);
      const restDest = d.battery_priority ? t.toBattery : t.toBatteryGrid;
      return `
        <div class="budget">
          <div class="budget-item" title="${esc(t.availableHint)}">
            <div class="meta-label">${t.available}</div>
            <div class="budget-value">${fmtW(budget)}</div>
          </div>
          <div class="budget-item" title="${esc(t.allocatedHint)}">
            <div class="meta-label">${t.allocatedRow}</div>
            <div class="budget-value sm">${fmtW(allocated)}</div>
          </div>
          <div class="budget-item rest" title="${esc(t.restHint)}">
            <div class="meta-label">${t.rest}</div>
            <div class="budget-value sm">${leftover > 30 ? `${fmtW(leftover)} → ${restDest}` : "–"}</div>
          </div>
        </div>`;
    })();

    const outlookHtml = (() => {
      const o = d.outlook;
      if (!o) return "";
      const rows = [];
      const f = o.forecast || {};
      const b = o.battery || {};
      if (f.remaining_kwh != null) {
        rows.push({
          name: t.forecast,
          text: `${num(f.remaining_kwh)} / ${num(f.need_kwh)} kWh · ${f.covers_battery ? t.forecastOk : t.forecastShort}`,
          cls: f.covers_battery ? "" : "warn",
          hint: t.forecastHint,
        });
      }
      if (b.soc != null && b.target_soc != null) {
        rows.push({
          name: t.battery,
          text: b.priority
            ? `${t.prioShortBat} · ${Math.round(b.soc)}→${Math.round(b.target_soc)} %`
            : `${t.prioShortDev} · SoC ${Math.round(b.soc)} %`,
          cls: b.priority ? "warn" : "",
          hint: b.priority ? t.prioBatHint : t.prioDevHint,
        });
      }
      for (const x of o.devices || []) {
        let text = "";
        let cls = x.at_risk ? "warn" : "";
        if (x.mode === "deadline_met") text = t.outlookMet;
        else if (x.mode === "surplus") text = t.outlookSurplus;
        else if (x.mode === "boost") {
          const bits = [`${t.boost} → ${Math.round(x.target)} %`];
          if (x.eta) bits.push(`${t.eta} ${hhmm(x.eta)}`);
          if (x.charging_h != null) bits.push(`${num(x.charging_h, 1)} h`);
          text = bits.join(" · ");
          cls = "warn";
        } else if (x.mode === "deadline") {
          const bits = [];
          const target = x.target != null
            ? (x.kind === "ev_charger" ? `${Math.round(x.target)} %` : `${num(x.target, 0)} °C`)
            : "";
          if (x.deadline) bits.push(`${t.until} ${hhmm(x.deadline)}${target ? ` · ${target}` : ""}`);
          if (x.deadline_mode === "solar") bits.push(t.outlookSolar);
          else {
            if (x.solar_kwh > 0.05) bits.push(`☀ ${num(x.solar_kwh)} kWh`);
            if (x.grid_kwh > 0.05) bits.push(`${t.grid} ${num(x.grid_kwh)} kWh`);
            if (Array.isArray(x.plan) && x.plan.length) bits.push(`NT ${x.plan.join(", ")}`);
            else if (x.deadline_start) bits.push(`${t.outlookFrom} ${hhmm(x.deadline_start)}`);
          }
          if (x.at_risk) bits.push(t.atRisk);
          if (x.urgent_now) bits.push(t.urgent);
          if (x.waiting_for_hdo) bits.push("HDO");
          if (x.charge_order || x.source === "order") bits.push(t.chargeOrder);
          text = bits.join(" · ") || t.outlookSurplus;
        } else {
          text = x.reason || x.mode || "";
        }
        if (!text) continue;
        rows.push({ name: x.name, text, cls, hint: t.outlookHint });
      }
      if (!rows.length) return "";
      return `
        <div class="outlook" title="${esc(t.outlookHint)}">
          <div class="meta-label">${t.outlook}</div>
          ${rows.map((r) => `
            <div class="ol-row ${r.cls || ""}" title="${esc(r.hint || t.outlookHint)}">
              <span class="ol-name">${esc(r.name)}</span>
              <span class="ol-text">${esc(r.text)}</span>
            </div>`).join("")}
        </div>`;
    })();

    const recs = Array.isArray(d.recommendations) ? d.recommendations.filter((r) => r && r.id != null) : [];
    const recById = Object.fromEntries(recs.map((r) => [r.id, r]));
    const blocks = [];

    blocks.push({
      kind: "grid",
      icon: ICON.grid,
      name: t.grid,
      sub: gridIdle ? t.idle : (g > 0 ? t.import : t.export),
      cls: gridIdle ? "" : g > 0 ? "warn" : "ok",
      on: !gridIdle,
      hint: t.gridHint,
      valueHtml: `<div class="pw">${gridIdle ? "–" : fmtW(Math.abs(g))}</div>`,
    });

    const batSub = [
      `${t.target} ${batTgt} %`,
      Math.abs(batW) > 30 ? `${batW > 0 ? t.charging : t.discharging} ${fmtW(Math.abs(batW))}` : "",
      d.battery_priority ? t.prioShortBat : "",
    ].filter(Boolean).join(" · ");
    blocks.push({
      kind: "battery",
      icon: ICON.battery,
      name: t.battery,
      sub: batSub,
      cls: d.battery_priority ? "warn" : "",
      on: Math.abs(batW) > 30 || batSoc >= 95,
      hint: t.batteryHint,
      valueHtml: `<div class="pw">${batSoc} %</div>`,
    });

    for (const x of devices) {
      const now = x.now || {};
      const realOn = !!now.on;
      const det = [];
      const curA = now.current != null ? Math.round(now.current) : null;
      if (realOn && curA) det.push(`${now.phases ?? "?"}f · ${curA} A`);
      if (x.temperature != null) det.push(`${num(x.temperature)} °C`);
      if (x.kind === "ev_charger" && x.soc == null) {
        /* SoC sensor not configured – power stays the headline. */
      } else if (x.soc != null && x.kind !== "ev_charger") {
        det.push(x.target_soc != null
          ? `SoC ${Math.round(x.soc)}→${Math.round(x.target_soc)} %`
          : `SoC ${Math.round(x.soc)} %`);
      } else if (x.kind === "ev_charger" && x.target_soc != null) {
        det.push(`${t.target} ${Math.round(x.target_soc)} %`);
      }
      if (x.charge_order?.soc != null) {
        det.push(`${t.chargeOrder} ${Math.round(x.charge_order.soc)} %${x.charge_order.deadline ? ` ${t.until} ${hhmm(x.charge_order.deadline)}` : ""}`);
      }
      if (x.boost?.soc != null) {
        det.push(`${t.boost} → ${Math.round(x.boost.soc)} %${x.deadline_eta ? ` · ${t.eta} ${hhmm(x.deadline_eta)}` : ""}`);
      }
      if (Array.isArray(x.plan) && x.plan.length) det.push(`${t.plan} ${x.plan.join(", ")}`);
      else if (typeof x.plan === "string" && x.plan) det.push(`${t.plan} ${x.plan}`);
      const td = x.today || {};
      if (td.total > 0.005) {
        det.push(`${t.today} ${num(td.total, 1)} kWh · ☀ ${Math.round((100 * (td.solar || 0)) / td.total)} %`);
      }
      let wanted = "", wantPower = "";
      if (x.pending) {
        if (x.kind === "ev_charger") {
          wanted = x.active ? `${x.current} A · ${x.phases}f` : t.stop;
          wantPower = x.active ? fmtW(x.allocated_w) : "0 W";
        } else {
          wanted = x.active ? t.turnOn : t.turnOff;
          wantPower = x.active ? fmtW(x.allocated_w) : "0 W";
        }
      }
      const state = d.dry_run
        ? (realOn
          ? (x.kind === "ev_charger" ? t.realCharge : (Number(x.actual_w) > 30 ? t.realRun : t.realOn))
          : t.realOff)
        : x.state;
      const tags = [
        x.urgent ? `<span class="tag urg" title="${esc(t.urgentHint)}">⚡ ${t.urgent}</span>` : "",
        x.min_first ? `<span class="tag min" title="${esc(t.minFirstHint)}">⬆ ${t.minFirst}</span>` : "",
        x.at_risk ? `<span class="tag urg" title="${esc(t.atRiskHint)}">⚠ ${t.atRisk}</span>` : "",
      ].join("");
      const rec = recById[x.id];
      const power = fmtW(x.actual_w);
      const cmpHint = !d.dry_run && wanted ? t.inProgress : t.deviceHint;
      const valueHtml = wanted
        ? `<div class="cmp" title="${esc(cmpHint)}">
            <span class="cmp-now"><small>${t.nowLabel}</small> ${x.soc != null ? `${Math.round(x.soc)} %` : power}</span>
            <span class="cmp-arrow">→</span>
            <span class="cmp-want"><small>${t.wantLabel}</small> <b>${wantPower}</b>${wanted ? ` <span class="cmp-det">${wanted}</span>` : ""}</span>
          </div>`
        : (x.kind === "ev_charger" && x.soc != null
          ? `<div class="pw" title="${esc(t.deviceHint)}">${Math.round(x.soc)} %</div>
             <div class="det">${power}</div>`
          : `<div class="pw" title="${esc(t.deviceHint)}">${power}</div>`);
      blocks.push({
        kind: "device",
        id: x.id,
        icon: ICON[x.kind] || "mdi:power-plug",
        name: x.name,
        sub: [state, ...det].filter(Boolean).join(" · "),
        tags,
        cls: wanted ? "pending" : "",
        on: realOn,
        hint: t.deviceHint,
        valueHtml,
        rec,
      });
    }

    if (d.export_limit_now != null || d.export_limit_target != null) {
      const controlled = d.export_limit_controlled !== false && d.export_limit_target != null;
      const diff = controlled
        && (d.export_limit_now == null || Math.abs(d.export_limit_now - d.export_limit_target) >= 0.5);
      const rec = recById.export_limit;
      const power = `${d.export_limit_now ?? "?"}${unit}`;
      const valueHtml = diff
        ? `<div class="cmp" title="${esc(t.exportHint)}">
            <span class="cmp-now"><small>${t.nowLabel}</small> ${power}</span>
            <span class="cmp-arrow">→</span>
            <span class="cmp-want"><small>${t.wantLabel}</small> <b>${d.export_limit_target}${unit}</b></span>
          </div>`
        : `<div class="pw" title="${esc(t.exportHint)}">${power}</div>`;
      blocks.push({
        kind: "export",
        id: "export_limit",
        icon: "mdi:transmission-tower-export",
        name: t.exportLimit,
        sub: controlled ? (d.export_raised ? t.raised : t.normal) : t.notControlled,
        cls: diff ? "pending" : "",
        on: controlled,
        hint: t.exportHint,
        valueHtml,
        rec: diff ? rec : null,
      });
    }

    const pending = blocks.filter((b) => b.rec);
    const isEv = (b) => b.kind === "device" && devices.some((x) => x.id === b.id && x.kind === "ev_charger");
    const renderBlock = (b) => `
      <div class="block ${b.on ? "on" : ""} ${b.cls || ""}"${b.hint ? ` title="${esc(b.hint)}"` : ""}>
        <ha-icon icon="${b.icon}"></ha-icon>
        <div class="main">
          <div class="name">${b.name}${b.tags || ""}</div>
          ${b.sub ? `<div class="det">${b.sub}</div>` : ""}
          ${isEv(b) ? `<button type="button" class="btn ghost ev-open" data-evid="${b.id}">${t.orderOpen}</button>` : ""}
        </div>
        <div class="side">
          ${b.valueHtml}
          ${d.dry_run && b.rec ? `<button class="btn" data-id="${b.id}" title="${t.since} ${hhmm(b.rec.since)}">${t.doIt}</button>` : ""}
        </div>
      </div>`;
    const evModal = `
      <div class="modal" hidden>
        <div class="modal-backdrop" data-ev="close"></div>
        <div class="modal-card" role="dialog" aria-modal="true" aria-label="${esc(t.orderModalTitle)}">
          <div class="modal-head">
            <div class="modal-title">${t.orderModalTitle}</div>
            <button type="button" class="btn ghost" data-ev="close">${t.orderClose}</button>
          </div>
          <p class="ev-hint">${t.holdHint}</p>
          <div class="ev-actions" data-evid="">
            <div class="ev-row">
              <label>${t.orderSoc}<input type="number" class="ord-soc" min="1" max="100" step="1" value="90"></label>
              <label>${t.orderWhen}<input type="datetime-local" class="ord-when"></label>
            </div>
            <div class="ev-row">
              <button type="button" class="btn" data-ev="order">${t.orderCreate}</button>
              <button type="button" class="btn ghost" data-ev="clear-order">${t.orderClear}</button>
            </div>
            <div class="ev-row">
              <button type="button" class="btn" data-ev="boost">${t.boostStart}</button>
              <button type="button" class="btn warn" data-ev="stop-boost">${t.boostStop}</button>
            </div>
            <div class="ev-err" hidden></div>
          </div>
        </div>
      </div>`;
    const stackChrome = (body) => `
      <div class="chips">
        ${modeChip}
        ${chip(
          d.battery_priority ? t.prioShortBat : t.prioShortDev,
          d.battery_priority ? "warn" : "",
          d.battery_priority ? t.prioBatHint : t.prioDevHint,
        )}
        ${d.hdo != null ? chip(d.hdo ? "NT" : "VT", d.hdo ? "ok" : "", t.tariffHint) : ""}
        ${d.borrow ? chip(t.borrowShort, "warn", t.borrowHint) : ""}
      </div>
      ${metaHtml}
      ${budgetHtml}
      ${outlookHtml}
      ${d.dry_run && pending.length > 1 ? `<div class="doall"><span>${t.manualHint}</span>
        <button class="btn all" data-id="">${t.doAll}</button></div>` : ""}
      <div class="stack">${body}</div>`;
    const fullStack = stackChrome(blocks.map(renderBlock).join(""));
    const cfg = this._config || {};
    const logSize = cfg.log === false ? 0 : Number(cfg.log ?? 20);
    const all = Array.isArray(d.log) ? d.log : [];
    const log = all.slice(0, logSize);
    // Show only what changed against the previous (older) decision.
    const changed = (i) => {
      const text = all[i]?.text;
      if (text == null) return "";
      const parts = String(text).split(" · ");
      const older = all[i + 1]?.text != null ? new Set(String(all[i + 1].text).split(" · ")) : null;
      const diff = older ? parts.filter((p) => !older.has(p)) : parts;
      return (diff.length ? diff : parts).join(" · ");
    };
    const logBlock = !log.length ? "" : `
      <div class="log">
        <div class="log-head">${t.decisions}</div>
        ${log.map((l, i) => `<div class="le${i === 0 ? " newest" : ""}" title="${esc(l?.text)}"><span class="lt">${hhmm(l?.at)}</span><span class="lx">${esc(changed(i))}</span></div>`).join("")}
      </div>`;
    // --- AI review ----------------------------------------------------------------
    const rv = d.review;
    const lines = (txt) => String(txt || "").split("\n").map((l) => l.replace(/^\s*[-•*]\s*/, "").trim())
      .filter((l) => l && !/^žádné\.?$|^none\.?$/i.test(l));
    const list = (title, txt, cls) => {
      const items = lines(txt);
      return items.length ? `<div class="rv-sec ${cls}"><div class="rv-h">${title}</div><ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>` : "";
    };
    const scoreCls = (sc) => (sc >= 8 ? "ok" : sc >= 5 ? "mid" : "bad");
    const history = (d.review_history || []).slice(0, 14).reverse();
    const reviewBlock = !d.review_enabled ? `<div class="none">${t.reviewOff}</div>` : `
      <div class="review">
        <div class="rv-top">
          ${rv ? `<div class="score ${scoreCls(rv.score)}">${rv.score}<small>/10</small></div>` : ""}
          <div class="rv-meta">
            ${rv ? `<div>${new Date(rv.at).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" })}${rv.dry_run ? ` · ${t.watchOnlyDay}` : ""}</div>` : `<div>${t.noReview}</div>`}
            ${d.review_error ? `<div class="err">${esc(d.review_error)}</div>` : ""}
          </div>
          <button class="btn review-now" ${d.review_running ? "disabled" : ""}>${d.review_running ? t.reviewing : t.reviewNow}</button>
        </div>
        ${rv ? `<div class="rv-sum">${esc(rv.summary)}</div>
          ${list(t.good, rv.good, "good")}${list(t.problems, rv.problems, "bad")}${list(t.suggestions, rv.suggestions, "sugg")}${list(t.aiOutlook, rv.outlook, "outlook")}` : ""}
        ${history.length > 1 ? `<div class="rv-hist">${history.map((h) => `<div class="hb ${scoreCls(h.score)}" title="${h.date}: ${h.score}/10" style="height:${8 + h.score * 3}px"></div>`).join("")}</div>` : ""}
      </div>`;
    const time = (() => {
      if (!d.changed_at) return "";
      const dt = new Date(d.changed_at);
      if (Number.isNaN(dt.getTime())) return "";
      try { return dt.toLocaleTimeString(lang); } catch { return ""; }
    })();
    // sections: which parts to show (split the card over several columns).
    // The power flow diagram is optional – Power Flow Card Plus does it better.
    const sections = Array.isArray(cfg.sections) ? cfg.sections : ["summary", "devices", "log"];
    const show = new Set(sections);
    if (show.has("chips")) show.add("summary"); // old names
    if (show.has("recommendations")) show.add("devices");
    const showStack = show.has("summary") || show.has("devices");
    let stackHtml = "";
    if (showStack) {
      if (show.has("summary") && show.has("devices")) {
        stackHtml = fullStack;
      } else {
        const keep = new Set();
        if (show.has("summary")) { keep.add("grid"); keep.add("battery"); }
        if (show.has("devices")) { keep.add("device"); keep.add("export"); }
        stackHtml = stackChrome(blocks.filter((b) => keep.has(b.kind)).map(renderBlock).join(""));
      }
    }
    const defaultTitle = show.size === 1 && show.has("log") ? t.decisions
      : show.size === 1 && show.has("review") ? t.review : "FVE Optimizer";
    root.innerHTML = `
      <ha-card>
        ${cfg.title !== false ? `<h1 class="title">${cfg.title || defaultTitle}</h1>` : ""}
        ${show.has("flow") ? `<div class="headline">${d.headline || ""}</div>${svg}` : ""}
        ${stackHtml}
        ${show.has("review") ? reviewBlock : ""}
        ${show.has("log") ? logBlock.replace(`<div class="log-head">${t.decisions}</div>`, show.size === 1 ? "" : `<div class="log-head">${t.decisions}</div>`) : ""}
        ${showStack ? `<div class="foot">${time}</div>` : ""}
        ${evModal}
      </ha-card>${STYLE}`;
    root.querySelector("button.review-now")?.addEventListener("click", (ev) => {
      ev.currentTarget.disabled = true;
      ev.currentTarget.textContent = t.reviewing;
      this._hass.callService("fve_optimizer", "run_review", {});
    });
    root.querySelectorAll("button.btn[data-id]").forEach((b) =>
      b.addEventListener("click", (ev) => {
        const id = ev.currentTarget.dataset.id;
        ev.currentTarget.disabled = true;
        this._hass.callService("fve_optimizer", "execute_recommendation", id ? { id } : {});
      })
    );
    const modal = root.querySelector(".modal");
    const actions = root.querySelector(".ev-actions");
    const errEl = actions?.querySelector(".ev-err");
    const showEvErr = (msg) => {
      if (!errEl) return;
      errEl.hidden = !msg;
      errEl.textContent = msg || "";
    };
    const fillEvForm = (x, draft) => {
      if (!actions) return;
      const socEl = actions.querySelector(".ord-soc");
      const whenEl = actions.querySelector(".ord-when");
      if (socEl) {
        socEl.value = draft?.soc != null && draft.soc !== ""
          ? draft.soc
          : Math.round(x.charge_order?.soc || x.deadline_soc || x.target_soc || 90);
      }
      if (whenEl) {
        if (draft?.when) {
          whenEl.value = draft.when;
        } else {
          try {
            const base = x.charge_order?.deadline ? new Date(x.charge_order.deadline) : new Date(Date.now() + 86400000);
            base.setMinutes(0, 0, 0);
            if (!x.charge_order) base.setHours(7);
            whenEl.value = new Date(base.getTime() - base.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
          } catch { whenEl.value = ""; }
        }
      }
      actions.querySelector('[data-ev="clear-order"]')?.toggleAttribute("hidden", !x.charge_order);
      actions.querySelector('[data-ev="stop-boost"]')?.toggleAttribute("hidden", !x.boost);
      actions.querySelector('[data-ev="boost"]')?.toggleAttribute("hidden", !!x.boost);
    };
    const openEvModal = (id, { useDraft = false } = {}) => {
      const x = devices.find((d) => d.id === id);
      if (!x || !modal || !actions) return;
      this._evModalId = id;
      actions.dataset.evid = id;
      const title = root.querySelector(".modal-title");
      if (title) title.textContent = `${t.orderModalTitle} – ${x.name}`;
      const draft = useDraft && this._evModalDraft?.id === id ? this._evModalDraft : null;
      fillEvForm(x, draft);
      showEvErr("");
      modal.hidden = false;
    };
    const closeEvModal = () => {
      this._evModalId = null;
      this._evModalDraft = null;
      showEvErr("");
      if (modal) modal.hidden = true;
    };
    this._closeEvModal = closeEvModal;
    const callEv = async (service, data) => {
      try {
        await this._hass.callService("fve_optimizer", service, data);
        closeEvModal();
        return true;
      } catch (err) {
        showEvErr(err?.message || t.orderError);
        return false;
      }
    };
    root.querySelectorAll("button.ev-open").forEach((b) =>
      b.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._evModalDraft = null;
        openEvModal(ev.currentTarget.dataset.evid);
      })
    );
    modal?.addEventListener("click", async (ev) => {
      const btn = ev.target.closest("[data-ev]");
      if (!btn) return;
      const act = btn.dataset.ev;
      if (act === "close") { closeEvModal(); return; }
      const id = actions?.dataset.evid;
      const soc = Number(actions.querySelector(".ord-soc")?.value);
      const when = actions.querySelector(".ord-when")?.value;
      btn.disabled = true;
      showEvErr("");
      let ok = true;
      if (act === "order") {
        if (!when || !soc) { btn.disabled = false; return; }
        ok = await callEv("set_ev_charge_order", {
          device_id: id,
          target_soc: soc,
          deadline: when.replace("T", " ") + ":00",
        });
      } else if (act === "clear-order") {
        ok = await callEv("clear_ev_charge_order", { device_id: id });
      } else if (act === "boost") {
        const data = { device_id: id };
        if (soc) data.target_soc = soc;
        ok = await callEv("start_ev_boost", data);
      } else if (act === "stop-boost") {
        ok = await callEv("stop_ev_boost", { device_id: id });
      }
      if (!ok) btn.disabled = false;
    });
    if (this._evModalId) openEvModal(this._evModalId, { useDraft: true });
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
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 8px; }
  .chip { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: var(--secondary-background-color);
    color: var(--primary-text-color); }
  .chip.ok { background: rgba(67,160,71,.15); color: var(--success-color, #43a047); }
  .chip.warn { background: rgba(255,152,0,.15); color: var(--warning-color, #ff9800); }
  .chip.info { background: rgba(3,155,229,.15); color: var(--info-color, #039be5); }
  .meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin: 0 0 10px; }
  @media (max-width: 420px) { .meta { grid-template-columns: 1fr; } }
  .meta-tile { padding: 10px 12px; border-radius: 10px; background: var(--secondary-background-color); min-width: 0; }
  .meta-label { font-size: 11px; text-transform: uppercase; letter-spacing: .02em;
    color: var(--secondary-text-color); margin-bottom: 2px; }
  .meta-value { font-size: 16px; font-weight: 500; font-variant-numeric: tabular-nums; line-height: 1.2;
    color: var(--primary-text-color); word-break: break-word; }
  .meta-sub { font-size: 12px; color: var(--secondary-text-color); margin-top: 3px; line-height: 1.3; }
  .meta-tile.ok .meta-value { color: var(--success-color, #43a047); }
  .meta-tile.warn .meta-value { color: var(--warning-color, #ff9800); }
  .budget { display: grid; grid-template-columns: 1.2fr 1fr 1.4fr; gap: 8px; padding: 10px 12px;
    border-radius: 10px; background: var(--secondary-background-color); margin: 0 0 10px; }
  .budget-item { min-width: 0; }
  .budget-item.rest { text-align: right; }
  .budget-value { font-size: 20px; font-weight: 500; font-variant-numeric: tabular-nums; line-height: 1.2; }
  .budget-value.sm { font-size: 16px; }
  .budget-item.rest .budget-value { font-size: 13px; font-weight: 400; color: var(--secondary-text-color);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .outlook { padding: 10px 12px; border-radius: 10px; background: var(--secondary-background-color); margin: 0 0 10px; }
  .outlook .meta-label { margin-bottom: 6px; }
  .ol-row { display: flex; gap: 10px; font-size: 13px; line-height: 1.35; padding: 2px 0; }
  .ol-name { flex: 0 0 28%; min-width: 4.5em; color: var(--secondary-text-color); }
  .ol-text { flex: 1; min-width: 0; }
  .ol-row.warn .ol-text { color: var(--warning-color, #ff9800); }
  .stack { display: flex; flex-direction: column; gap: 6px; margin: 0 0 8px; }
  .block { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px;
    background: var(--secondary-background-color); opacity: .78; }
  .block.on { opacity: 1; }
  .block.pending { outline: 1px solid var(--warning-color, #ff9800); opacity: 1; }
  .block.ok .pw { color: var(--success-color, #43a047); }
  .block.warn .pw { color: var(--warning-color, #ff9800); }
  .block ha-icon { color: var(--secondary-text-color); --mdc-icon-size: 22px; flex-shrink: 0; }
  .block.on ha-icon { color: var(--primary-color); }
  .block .main { flex: 1; min-width: 0; }
  .block .name { font-size: 14px; }
  .block .det { color: var(--secondary-text-color); font-size: 12px; margin-top: 1px; }
  .block .side { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
  .block .pw { font-weight: 500; font-size: 16px; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .ev-open { margin-top: 6px; font-size: 12px; padding: 2px 8px; }
  .modal[hidden] { display: none !important; }
  .modal { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center;
    padding: 16px; }
  .modal-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,.45); }
  .modal-card { position: relative; z-index: 1; width: min(420px, 100%); max-height: 90vh; overflow: auto;
    padding: 14px 16px; border-radius: 12px; background: var(--card-background-color, #1c1c1c);
    color: var(--primary-text-color); box-shadow: 0 8px 28px rgba(0,0,0,.35); }
  .modal-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
  .modal-title { font-size: 16px; font-weight: 500; }
  .ev-actions { display: flex; flex-direction: column; gap: 10px; margin-top: 8px; }
  .ev-row { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px; }
  .ev-row label { display: flex; flex-direction: column; gap: 2px; font-size: 11px;
    color: var(--secondary-text-color); flex: 1; min-width: 6em; }
  .ev-row input { font: inherit; font-size: 14px; padding: 6px 8px; border-radius: 6px;
    border: 1px solid var(--divider-color, #555); background: var(--secondary-background-color, #111);
    color: var(--primary-text-color); width: 100%; box-sizing: border-box; }
  .btn.ghost { background: transparent; border: 1px solid var(--divider-color, #555); }
  .btn.warn { background: var(--warning-color, #ff9800); }
  .ev-hint { font-size: 12px; color: var(--secondary-text-color); margin: 0; line-height: 1.35; }
  .ev-err { font-size: 12px; color: var(--error-color, #db4437); margin-top: 4px; }
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
  .recs { border: 1px solid var(--divider-color, #ddd); border-radius: 10px; padding: 8px 10px; margin: 0 0 10px; }
  .recs-head { display: flex; justify-content: space-between; align-items: center; font-size: 13px;
    color: var(--info-color, #039be5); margin-bottom: 4px; }
  .rtab { width: 100%; border-collapse: collapse; font-size: 13px; }
  .rtab th { text-align: left; font-weight: 400; font-size: 11px; color: var(--secondary-text-color); padding: 2px 4px; }
  .rtab td { padding: 5px 4px; border-top: 1px solid var(--divider-color, #ddd); vertical-align: middle; }
  .rtab td.w { font-weight: 500; }
  .rtab td.n { color: var(--secondary-text-color); }
  .rtab td.act { text-align: right; white-space: nowrap; color: var(--success-color, #43a047); }
  .rtab tr.diff td.w { color: var(--warning-color, #ff9800); }
  .rtab tr.diff td.act { color: var(--secondary-text-color); }
  .btn { font: inherit; font-size: 12px; padding: 3px 10px; border-radius: 12px; border: none; cursor: pointer;
    background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
  .btn.all { background: transparent; color: var(--primary-color, #03a9f4); border: 1px solid var(--primary-color, #03a9f4); }
  .btn:disabled { opacity: .5; cursor: default; }
  .none { font-size: 12px; color: var(--secondary-text-color); }
  .log { margin-top: 10px; }
  .log-head { font-size: 13px; color: var(--secondary-text-color); margin-bottom: 2px; }
  .le { display: flex; gap: 8px; font-size: 12px; padding: 3px 0; border-top: 1px solid var(--divider-color, #ddd); }
  .le .lt { color: var(--secondary-text-color); white-space: nowrap; font-variant-numeric: tabular-nums; }
  .le .lx { flex: 1; min-width: 0; }
  .le.newest .lx { font-weight: 500; }
  .summary { margin: 4px 0 12px; }
  .row.pending { outline: 1px solid var(--warning-color, #ff9800); }
  .det.stats { opacity: .85; }
  .side { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
  .cmp { display: flex; align-items: baseline; gap: 6px; font-size: 13px; font-variant-numeric: tabular-nums; }
  .cmp small { display: block; font-size: 10px; color: var(--secondary-text-color); line-height: 1; margin-bottom: 1px;
    text-transform: uppercase; }
  .cmp-now { color: var(--secondary-text-color); text-align: right; }
  .cmp-arrow { color: var(--secondary-text-color); }
  .cmp-want { color: var(--warning-color, #ff9800); text-align: right; }
  .cmp-det { font-weight: 400; font-size: 11px; opacity: .9; }
  .doall { display: flex; justify-content: space-between; align-items: center; font-size: 12px;
    color: var(--info-color, #039be5); }
  .review .rv-top { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
  .score { font-size: 32px; font-weight: 500; line-height: 1; }
  .score small { font-size: 14px; color: var(--secondary-text-color); }
  .score.ok { color: var(--success-color, #43a047); }
  .score.mid { color: var(--warning-color, #ff9800); }
  .score.bad { color: var(--error-color, #db4437); }
  .rv-meta { flex: 1; font-size: 12px; color: var(--secondary-text-color); }
  .rv-meta .err { color: var(--error-color, #db4437); }
  .rv-sum { font-size: 14px; margin-bottom: 8px; }
  .rv-sec { font-size: 13px; margin-bottom: 6px; }
  .rv-sec .rv-h { color: var(--secondary-text-color); font-size: 12px; }
  .rv-sec ul { margin: 2px 0 0; padding-left: 18px; }
  .rv-sec.sugg li { color: var(--info-color, #039be5); }
  .rv-sec.outlook li { color: var(--primary-text-color); }
  .rv-hist { display: flex; align-items: flex-end; gap: 3px; height: 42px; margin-top: 8px; }
  .hb { width: 10px; border-radius: 2px; }
  .hb.ok { background: var(--success-color, #43a047); }
  .hb.mid { background: var(--warning-color, #ff9800); }
  .hb.bad { background: var(--error-color, #db4437); }
  .foot { text-align: right; font-size: 11px; color: var(--secondary-text-color); margin-top: 6px; }
</style>`;

const TAG = "fve-optimizer-card";
const Prev = customElements.get(TAG);
if (!Prev) {
  customElements.define(TAG, FveOptimizerCard);
} else {
  // Script reloaded with same tag: swap methods/setters onto the registered class.
  for (const key of Object.getOwnPropertyNames(FveOptimizerCard.prototype)) {
    if (key === "constructor") continue;
    const desc = Object.getOwnPropertyDescriptor(FveOptimizerCard.prototype, key);
    if (desc) Object.defineProperty(Prev.prototype, key, desc);
  }
  for (const el of INSTANCES) {
    el._last = null;
    if (el._hass) el.hass = el._hass;
  }
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === TAG)) {
  window.customCards.push({
    type: TAG,
    name: "FVE Optimizer",
    description: "Power flow and decisions of the FVE Optimizer integration.",
  });
}
