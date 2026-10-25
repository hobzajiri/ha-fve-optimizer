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
    gridImport: "odběr", gridExport: "přetok", allowedExport: "povolený přetok",
    target: "cíl", surplus: "Přebytek", allocated: "rozděleno", exportRaised: "Limit přetoku zvýšen",
    exportNormal: "Limit přetoku běžný", nt: "NT (HDO)", vt: "VT", borrow: "Dorovnání z baterie",
    forecast: "Predikce", need: "potřeba", forecastOk: "pokryje baterii", forecastShort: "nestačí na baterii",
    fcBattery: "baterie", fcHouse: "dům", fcMargin: "rezerva", fcMark: "predikce", fcNeed: "potřeba",
    fcUntilSunset: "do západu",
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
    budgetPartDevices: "řízená zařízení", budgetPartExport: "přetok", budgetPartImport: "odběr ze sítě",
    budgetPartBattery: "baterie", budgetPartReserved: "rezerva pro baterii", budgetPartReserve: "rezerva",
    budgetPartEq: "návrh",
    toSplit: "K rozdělení", toSplitHint: "Rozpočet pro řízená zařízení (po rezervě pro baterii). Svislá čára v grafu.",
    allocatedRow: "Rozděleno zařízením", allocatedHint: "Součet výkonu přiděleného řízeným zařízením.",
    overBudget: "nad rozpočet", overBudgetHint: "Zařízení berou víc než „k rozdělení“ – typicky dorovnání z výkonu, který by jinak nabíjel baterii.",
    rest: "zbytek", restHint: "Co zařízení neberou – zůstane baterii nebo půjde do sítě.",
    toBattery: "Baterie", toBatteryGrid: "Baterie / síť",
    toGrid: "Síť", toExport: "Přetok do sítě",
    budgetTargets: "Rozdělení",
    budgetFlowHint: "Barevné pruhy = návrh pro zařízení. Svislá čára = k rozdělení. Pod tím skutečná baterie a síť.",
    forecastHint: "Barevné úseky = potřeba do západu (dům, baterie, rezerva). Svislá čára = zbývající predikce výroby na stejném měřítku.",
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
    reviewAsk: "Zeptat se", reviewAsking: "Odpovídám…", reviewAskPlaceholder: "Otázka k hodnocení…",
    reviewYou: "Ty", reviewAi: "AI",
    morningPlan: "Ranní předpoklad", morningNow: "Připravit předpoklad", morningRunning: "Připravuji…",
    morningNone: "Zatím žádný předpoklad na dnešek.",
    morningExpect: "Očekávání", morningRisks: "Rizika",
    chargeForecast: "Aktuální předpověď nabití", chargeNow: "Aktualizovat předpověď",
    chargeRunning: "Aktualizuji…", chargeNone: "Zatím žádná předpověď nabití na dnešek.",
    chargeBattery: "Baterie", chargeDevices: "Zařízení", chargeRisks: "Rizika",
    good: "Co fungovalo", problems: "Problémy", suggestions: "Návrhy úprav", watchOnlyDay: "den v režimu Jen sledovat",
    proposalApply: "Použít", proposalDismiss: "Zamítnout",
    proposalApplied: "použito", proposalDismissed: "zamítnuto", proposalInvalid: "neplatné",
    proposalFromTo: "z", proposalTo: "na",
    statsHint: "Spotřeba dnes, náklady za energii ze sítě (NT/VT) a podíl ze slunce",
    statusTitle: "Stav",
    outlook: "Předpoklad dne", outlookHint: "Co Optimizer očekává do konce dne z predikce, termínů a HDO – ne AI odhad.",
    outlookSurplus: "jen při přebytku", outlookSolar: "pokryje slunce", outlookMet: "minimum splněno",
    outlookFrom: "od", aiOutlook: "Zbytek dne",
    chargeOrder: "objednávka", boost: "rychlé nabíjení", away: "odjezd", eta: "hotovo cca",
    orderSoc: "Cíl %", orderWhen: "Termín", orderCreate: "Objednat", orderClear: "Zrušit objednávku",
    boostStart: "Rychle teď", boostStop: "Stop rychlé",
    awayLeave: "Odjezd", awayReturn: "Návrat", awaySet: "Naplánovat odjezd", awayClear: "Zrušit odjezd",
    awayLend: "z baterie",
    holdHint: "Do 80 % dřív · 80–100 % až těsně před termínem · Odjezd: při dobré predikci uvolní přebytek z baterie do auta (ne nabíjení naplno)",
    orderOpen: "Objednávka", orderModalTitle: "Objednávka", orderClose: "Zavřít",
    orderTemp: "Cíl °C", orderDate: "Datum", orderTime: "Čas",
    orderError: "Nepodařilo se uložit – zkus to znovu",
    holdHintBoiler: "Nahřeje bojler na cílovou teplotu do zvoleného termínu (přebytky, jinak NT / těsně před termínem).",
  },
  en: {
    pv: "PV", grid: "Grid", battery: "Battery", house: "House",
    import: "import", export: "export", charging: "charging", discharging: "discharging", idle: "idle",
    gridImport: "import", gridExport: "export", allowedExport: "allowed export",
    target: "target", surplus: "Surplus", allocated: "allocated", exportRaised: "Export limit raised",
    exportNormal: "Export limit normal", nt: "Low tariff", vt: "High tariff", borrow: "Rounding up from battery",
    forecast: "Forecast", need: "need", forecastOk: "covers battery", forecastShort: "short of battery",
    fcBattery: "battery", fcHouse: "house", fcMargin: "margin", fcMark: "forecast", fcNeed: "need",
    fcUntilSunset: "until sunset",
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
    budgetPartDevices: "managed devices", budgetPartExport: "export", budgetPartImport: "grid import",
    budgetPartBattery: "battery", budgetPartReserved: "reserved for battery", budgetPartReserve: "headroom",
    budgetPartEq: "plan",
    toSplit: "To allocate", toSplitHint: "Budget for managed devices (after battery reserve). Vertical line on the chart.",
    allocatedRow: "Allocated to devices", allocatedHint: "Sum of power assigned to managed devices.",
    overBudget: "over budget", overBudgetHint: "Devices take more than “to allocate” – usually borrowing power that would otherwise charge the battery.",
    rest: "rest", restHint: "What devices do not take – left for the battery or the grid.",
    toBattery: "Battery", toBatteryGrid: "Battery / grid",
    toGrid: "Grid", toExport: "Grid export",
    budgetTargets: "Allocation",
    budgetFlowHint: "Colored bars = device plan. Vertical line = to allocate. Below: actual battery and grid.",
    forecastHint: "Coloured segments = need until sunset (house, battery, margin). Vertical line = remaining production forecast on the same scale.",
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
    reviewAsk: "Ask", reviewAsking: "Answering…", reviewAskPlaceholder: "Question about the review…",
    reviewYou: "You", reviewAi: "AI",
    morningPlan: "Morning plan", morningNow: "Prepare day plan", morningRunning: "Preparing…",
    morningNone: "No morning plan for today yet.",
    morningExpect: "Expectations", morningRisks: "Risks",
    chargeForecast: "Current charge forecast", chargeNow: "Refresh forecast",
    chargeRunning: "Refreshing…", chargeNone: "No charge forecast for today yet.",
    chargeBattery: "Battery", chargeDevices: "Devices", chargeRisks: "Risks",
    good: "What worked", problems: "Problems", suggestions: "Suggested changes", watchOnlyDay: "watch-only day",
    proposalApply: "Apply", proposalDismiss: "Dismiss",
    proposalApplied: "applied", proposalDismissed: "dismissed", proposalInvalid: "invalid",
    proposalFromTo: "from", proposalTo: "to",
    statsHint: "Consumption today, cost of grid energy (NT/VT) and solar share",
    statusTitle: "Status",
    outlook: "Today’s outlook", outlookHint: "What the Optimizer expects for the rest of the day from forecast, deadlines and HDO – not an AI guess.",
    outlookSurplus: "surplus only", outlookSolar: "covered by sun", outlookMet: "minimum met",
    outlookFrom: "from", aiOutlook: "Rest of day",
    chargeOrder: "order", boost: "fast charge", away: "away", eta: "ready ~",
    orderSoc: "Target %", orderWhen: "Deadline", orderCreate: "Order", orderClear: "Clear order",
    boostStart: "Fast now", boostStop: "Stop boost",
    awayLeave: "Leave", awayReturn: "Return", awaySet: "Plan away", awayClear: "Clear away",
    awayLend: "from battery",
    holdHint: "To 80 % earlier · 80–100 % only just before the deadline · Away: with a good forecast, release surplus from the battery to the car (not full-power dump)",
    orderOpen: "Order", orderModalTitle: "Order", orderClose: "Close",
    orderTemp: "Target °C", orderDate: "Date", orderTime: "Time",
    orderError: "Could not save – try again",
    holdHintBoiler: "Heats the boiler to the target temperature by the chosen deadline (surplus, otherwise off-peak / just in time).",
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
/** Signed watts for budget-part tooltips (+900 W / −100 W). */
const fmtWSigned = (w) => {
  const n = Math.round(Number(w) || 0);
  if (n === 0) return "0 W";
  return `${n > 0 ? "+" : "−"}${fmtW(Math.abs(n))}`;
};
const num = (v, d = 1) => (v == null || Number.isNaN(Number(v)) ? "?" : Number(v).toFixed(d).replace(".", ","));
const esc = (x) => String(x ?? "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
/** Tooltip for Návrh / Plan: short explanation + live budget_parts breakdown. */
const budgetAvailableHint = (t, parts, budget) => {
  const p = parts && typeof parts === "object" ? parts : {};
  const lines = [t.availableHint, ""];
  const row = (label, watts, sign) => {
    const n = Number(watts) || 0;
    if (!n && sign !== "=") return;
    const shown = sign === "=" ? fmtW(watts) : sign === "-" ? fmtWSigned(-Math.abs(n)) : fmtWSigned(n);
    lines.push(`${label}: ${shown}`);
  };
  row(t.budgetPartDevices, p.devices, "+");
  row(t.budgetPartExport, p.export, "+");
  row(t.budgetPartImport, p.import, "-");
  // Battery: charging (+) adds to the plan, discharging (−) reduces it.
  if (p.battery) row(t.budgetPartBattery, p.battery, "+");
  row(t.budgetPartReserved, p.battery_reserved, "-");
  row(t.budgetPartReserve, p.reserve, "-");
  if (lines.length > 2) {
    lines.push(`= ${t.budgetPartEq}: ${fmtW(budget)}`);
  }
  return lines.join("\n");
};
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

  static findStatusEntity(hass) {
    return Object.keys(hass?.states || {}).find(
      (e) => e.startsWith("sensor.") && hass.states[e].attributes.data?.devices
    ) || "sensor.fve_optimizer_status";
  }

  static getStubConfig(hass) {
    return {
      entity: FveOptimizerCard.findStatusEntity(hass),
      sections: ["summary", "devices", "log"],
    };
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
    // Preserve AI ask draft + focus across coordinator re-renders.
    const askEl = root.querySelector?.("input.rv-q");
    if (askEl && document.activeElement === askEl) {
      this._askDraft = {
        value: askEl.value,
        start: askEl.selectionStart,
        end: askEl.selectionEnd,
        focus: true,
      };
    } else if (askEl && askEl.value && !this._askDraft?.sent) {
      this._askDraft = { ...(this._askDraft || {}), value: askEl.value, focus: false };
    }
    // Preserve in-progress modal edits across coordinator re-renders.
    if (this._evModalId) {
      const soc = root.querySelector?.(".ord-soc")?.value;
      const temp = root.querySelector?.(".ord-temp")?.value;
      const whenDate = root.querySelector?.(".ord-when-date")?.value;
      const whenTime = root.querySelector?.(".ord-when-time")?.value;
      const leaveDate = root.querySelector?.(".away-leave-date")?.value;
      const leaveTime = root.querySelector?.(".away-leave-time")?.value;
      const retDate = root.querySelector?.(".away-return-date")?.value;
      const retTime = root.querySelector?.(".away-return-time")?.value;
      if (soc != null || temp != null || whenDate != null || leaveDate != null) {
        this._evModalDraft = {
          id: this._evModalId,
          soc,
          temp,
          whenDate,
          whenTime,
          leaveDate,
          leaveTime,
          retDate,
          retTime,
        };
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
    // Outlook rows (battery priority + device plans) – merged under the forecast chart.
    const outlookRows = (() => {
      const o = d.outlook;
      if (!o) return [];
      const rows = [];
      const b = o.battery || {};
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
        } else if (x.mode === "away") {
          const bits = [t.away];
          if (x.deadline) bits.push(`${t.until} ${hhmm(x.deadline)}`);
          if (x.target != null) bits.push(`${Math.round(x.target)} %`);
          if (x.car_budget_kwh > 0.05) bits.push(`→ ${num(x.car_budget_kwh)} kWh`);
          else if (x.releases_battery && x.battery_lend_kwh > 0.05) {
            bits.push(`${t.awayLend} ${num(x.battery_lend_kwh)} kWh`);
          }
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
          if (x.charge_order || x.heat_order || x.source === "order") bits.push(t.chargeOrder);
          text = bits.join(" · ") || t.outlookSurplus;
        } else {
          text = x.reason || x.mode || "";
        }
        if (!text) continue;
        rows.push({ name: x.name, text, cls, hint: t.outlookHint });
      }
      return rows;
    })();

    const forecastHtml = (() => {
      const hasForecast = d.forecast_kwh != null;
      if (!hasForecast && !outlookRows.length) return "";
      let chart = "";
      let statusCls = "";
      let statusTxt = "";
      if (hasForecast) {
        const parts = d.forecast_parts || {};
        const bat = Math.max(0, Number(parts.battery_kwh) || 0);
        const house = Math.max(0, Number(parts.house_kwh) || 0);
        const margin = Math.max(0, Number(parts.margin_kwh) || 0);
        const need = Math.max(0, Number(d.forecast_need_kwh) || bat + house + margin);
        const rem = Math.max(0, Number(d.forecast_kwh) || 0);
        const scale = Math.max(need, rem, 0.01);
        const pct = (v) => `${Math.min(100, Math.max(0, (100 * v) / scale)).toFixed(2)}%`;
        const segs = [
          house > 0.005 ? { cls: "house", w: pct(house), title: `${t.fcHouse} ${num(house)} kWh` } : null,
          bat > 0.005 ? { cls: "bat", w: pct(bat), title: `${t.fcBattery} ${num(bat)} kWh` } : null,
          margin > 0.005 ? { cls: "margin", w: pct(margin), title: `${t.fcMargin} ${num(margin)} kWh` } : null,
        ].filter(Boolean);
        if (!segs.length && need > 0) {
          segs.push({ cls: "need", w: pct(need), title: `${t.fcNeed} ${num(need)} kWh` });
        }
        const hours = parts.hours_until_sunset;
        const hoursTxt = hours != null && hours > 0
          ? ` · ${t.fcUntilSunset} ${num(hours, 1)} h`
          : "";
        const status = d.forecast_covers ? t.forecastOk : t.forecastShort;
        const coverPct = need > 0 ? Math.min(100, Math.round((100 * rem) / need)) : (rem > 0 ? 100 : 0);
        statusCls = d.forecast_covers ? "ok" : "warn";
        statusTxt = `${status} · ${coverPct} %${hoursTxt}`;
        const legend = [
          `<span class="fc-leg mark">${t.fcMark} ${num(rem)}</span>`,
          house > 0.005 ? `<span class="fc-leg house">${t.fcHouse} ${num(house)}</span>` : "",
          bat > 0.005 ? `<span class="fc-leg bat">${t.fcBattery} ${num(bat)}</span>` : "",
          margin > 0.005 ? `<span class="fc-leg margin">${t.fcMargin} ${num(margin)}</span>` : "",
        ].filter(Boolean).join("");
        // One track: need segments + forecast marker (same idea as allocation “to split” line).
        const markLeft = pct(rem);
        chart = `
          <div class="fc-track" title="${esc(t.forecastHint)}">
            <div class="fc-bar">
              ${segs.map((s) => `<div class="fc-seg ${s.cls}" style="width:${s.w}" title="${esc(s.title)}"></div>`).join("")}
            </div>
            <div class="fc-mark" style="left:${markLeft}" title="${esc(`${t.fcMark} ${num(rem)} kWh`)}"></div>
          </div>
          <div class="fc-legend">${legend}<span class="fc-unit">kWh</span></div>`;
      }
      const ol = !outlookRows.length ? "" : `
        <div class="fc-outlook">
          ${outlookRows.map((r) => `
            <div class="ol-row ${r.cls || ""}" title="${esc(r.hint || t.outlookHint)}">
              <span class="ol-name">${esc(r.name)}</span>
              <span class="ol-text">${esc(r.text)}</span>
            </div>`).join("")}
        </div>`;
      return `
        <div class="fc ${statusCls}" title="${esc(t.outlookHint)}">
          <div class="fc-head">
            <span class="meta-label">${t.outlook}</span>
            ${statusTxt ? `<span class="fc-status">${statusTxt}</span>` : ""}
          </div>
          ${chart}
          ${ol}
        </div>`;
    })();

    const metaTiles = [tariffTile(), priceTile()].filter(Boolean);
    const metaHtml = !metaTiles.length ? "" : `
      <div class="meta meta-${metaTiles.length}">
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
      const batW = Number(d.battery_w) || 0;
      const gridW = Number(d.grid_w) || 0;
      const batAbs = Math.abs(batW);
      const gridAbs = Math.abs(gridW);
      if (budget < 30 && allocated < 30 && batAbs < 30 && gridAbs < 30) return "";
      const availableTitle = budgetAvailableHint(t, d.budget_parts, budget);
      const palette = [
        "var(--primary-color, #03a9f4)",
        "var(--accent-color, #ff9800)",
        "#ab47bc",
        "#26a69a",
        "#ec407a",
      ];
      const cBat = "var(--info-color, #039be5)";
      const cExp = "var(--success-color, #43a047)";
      const cImp = "var(--error-color, #db4437)";
      // Device plan in the stacked bar; battery + grid as always-visible actuals below.
      const deviceRows = [];
      let di = 0;
      for (const x of devices) {
        const w = Number(x.allocated_w) || 0;
        if (w <= 30) continue;
        deviceRows.push({
          name: x.name || "?",
          w,
          label: fmtW(w),
          hint: x.state || "",
          color: palette[di % palette.length],
        });
        di += 1;
      }
      const actualRows = [
        {
          name: t.toBattery,
          w: batAbs > 30 ? batAbs : 0,
          label: batAbs > 30
            ? `${batW > 0 ? t.charging : t.discharging} ${fmtW(batAbs)}`
            : "–",
          hint: t.batteryHint,
          color: cBat,
          dim: batAbs <= 30,
        },
        {
          name: t.toGrid,
          w: gridAbs > 30 ? gridAbs : 0,
          label: gridAbs > 30
            ? `${gridW > 0 ? t.import : t.export} ${fmtW(gridAbs)}`
            : "–",
          hint: t.gridHint,
          color: gridW > 0 ? cImp : cExp,
          dim: gridAbs <= 30,
        },
      ];
      // Same scale for bar + mark: both "k rozdělení" and allocated fit.
      const scale = Math.max(budget, allocated, 0.01);
      const pct = (v) => `${Math.min(100, Math.max(0, (100 * v) / scale)).toFixed(2)}%`;
      const markPct = pct(budget);
      const over = Math.max(allocated - budget, 0);
      const stack = deviceRows.length
        ? deviceRows.map((r) =>
          `<div class="bf-seg" style="width:${pct(r.w)};background:${r.color}" title="${esc(`${r.name}: ${r.label}`)}"></div>`
        ).join("")
        : `<div class="bf-seg bf-empty" style="width:${pct(Math.max(budget, 0))}"></div>`;
      const allRows = [...deviceRows.map((r) => ({ ...r, dim: false })), ...actualRows];
      const rowScale = Math.max(...allRows.map((r) => r.w), budget, 0.01);
      const pctRow = (v) => `${Math.min(100, Math.max(0, (100 * v) / rowScale)).toFixed(2)}%`;
      const rowHtml = allRows.map((r) => `
        <div class="bf-row ${r.dim ? "dim" : ""}" title="${esc(r.hint)}">
          <span class="bf-dot" style="background:${r.color}"></span>
          <span class="bf-name">${esc(r.name)}</span>
          <div class="bf-track"><div class="bf-fill" style="width:${pctRow(r.w)};background:${r.color}"></div></div>
          <span class="bf-val">${esc(r.label)}</span>
        </div>`).join("");
      return `
        <div class="budget-flow" title="${esc(t.budgetFlowHint)}">
          <div class="bf-head">
            <span class="meta-label">${t.budgetTargets}</span>
            <span class="bf-total">${allocated > 30 ? fmtW(allocated) : "–"}</span>
          </div>
          <div class="bf-stack-wrap">
            <div class="bf-stack">${stack}</div>
            <div class="bf-mark" style="left:${markPct}" title="${esc(`${t.toSplit}: ${fmtW(budget)}`)}"></div>
          </div>
          <div class="bf-mark-label" style="margin-left:min(${markPct}, 72%)">
            <span title="${esc(availableTitle)}">${esc(t.toSplit)} ${fmtW(budget)}</span>
          </div>
          <div class="bf-rows">${rowHtml}</div>
          <div class="bf-foot">
            <div class="bf-foot-row" title="${esc(availableTitle)}">
              <span>${esc(t.toSplit)}</span><span>${fmtW(budget)}</span>
            </div>
            <div class="bf-foot-row" title="${esc(t.allocatedHint)}">
              <span>${esc(t.allocatedRow)}</span><span>${fmtW(allocated)}</span>
            </div>
            ${over > 30 ? `
            <div class="bf-foot-row warn" title="${esc(t.overBudgetHint)}">
              <span>${esc(t.overBudget)}</span><span>+${fmtW(over)}</span>
            </div>` : ""}
          </div>
        </div>`;
    })();

    const recs = Array.isArray(d.recommendations) ? d.recommendations.filter((r) => r && r.id != null) : [];
    const recById = Object.fromEntries(recs.map((r) => [r.id, r]));
    const blocks = [];

    const exportControlled = d.export_limit_controlled !== false && d.export_limit_target != null;
    const exportDiff = exportControlled
      && (d.export_limit_now == null || Math.abs(d.export_limit_now - d.export_limit_target) >= 0.5);
    const exportRec = exportDiff ? recById.export_limit : null;
    const limitNow = d.export_limit_now != null ? `${d.export_limit_now}${unit}` : null;
    const limitWant = d.export_limit_target != null ? `${d.export_limit_target}${unit}` : null;
    const gridState = gridIdle ? t.idle : (g > 0 ? t.gridImport : t.gridExport);
    const gridCls = gridIdle ? "" : g > 0 ? "imp" : "ok";
    const gridPower = gridIdle ? "–" : fmtW(Math.abs(g));
    const limitLine = exportDiff
      ? `${t.allowedExport} ${limitNow ?? "?"} → ${limitWant}`
      : (limitNow != null ? `${t.allowedExport} ${limitNow}` : "");
    blocks.push({
      kind: "grid",
      id: exportRec ? "export_limit" : undefined,
      icon: ICON.grid,
      name: t.grid,
      sub: gridState,
      cls: `${gridCls}${exportDiff ? " pending" : ""}`,
      on: !gridIdle || exportControlled,
      hint: t.gridHint,
      valueHtml: `<div class="pw" title="${esc(t.gridHint)}">${gridPower}</div>
        ${limitLine ? `<div class="det" title="${esc(t.exportHint)}">${esc(limitLine)}</div>` : ""}`,
      rec: exportRec,
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
      // Temperature / SoC are the right-hand headline (like EV SoC); only show target in the subtitle.
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
      if (x.heat_order?.temp != null) {
        det.push(`${t.chargeOrder} ${num(x.heat_order.temp)} °C${x.heat_order.deadline ? ` ${t.until} ${hhmm(x.heat_order.deadline)}` : ""}`);
      }
      if (x.boost?.soc != null) {
        det.push(`${t.boost} → ${Math.round(x.boost.soc)} %${x.deadline_eta ? ` · ${t.eta} ${hhmm(x.deadline_eta)}` : ""}`);
      }
      if (x.away?.leave_at) {
        const bits = [`${t.away} ${hhmm(x.away.leave_at)}`];
        if (x.away.return_at) bits.push(`→ ${hhmm(x.away.return_at)}`);
        if (x.car_budget_kwh > 0.05) bits.push(`→ auto ${num(x.car_budget_kwh)} kWh`);
        else if (x.battery_lend_kwh > 0.05) bits.push(`${t.awayLend} ${num(x.battery_lend_kwh)} kWh`);
        det.push(bits.join(" · "));
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
      const headline = x.soc != null ? `${Math.round(x.soc)} %`
        : x.temperature != null ? `${num(x.temperature)} °C`
        : power;
      const valueHtml = wanted
        ? `<div class="cmp" title="${esc(cmpHint)}">
            <span class="cmp-now"><small>${t.nowLabel}</small> ${headline}</span>
            <span class="cmp-arrow">→</span>
            <span class="cmp-want"><small>${t.wantLabel}</small> <b>${wantPower}</b>${wanted ? ` <span class="cmp-det">${wanted}</span>` : ""}</span>
          </div>`
        : (x.soc != null || x.temperature != null
          ? `<div class="pw" title="${esc(t.deviceHint)}">${headline}</div>
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

    const pending = blocks.filter((b) => b.rec);
    const canOrder = (b) => b.kind === "device" && devices.some((x) =>
      x.id === b.id && (x.kind === "ev_charger" || x.supports_order || x.heat_order != null || x.temperature != null)
    );
    const renderBlock = (b) => `
      <div class="block ${b.on ? "on" : ""} ${b.cls || ""}"${b.hint ? ` title="${esc(b.hint)}"` : ""}>
        <ha-icon icon="${b.icon}"></ha-icon>
        <div class="main">
          <div class="name">${b.name}${b.tags || ""}</div>
          ${b.sub ? `<div class="det">${b.sub}</div>` : ""}
          ${canOrder(b) ? `<button type="button" class="btn ghost ev-open" data-evid="${b.id}">${t.orderOpen}</button>` : ""}
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
          <p class="ev-hint"></p>
          <div class="ev-actions" data-evid="" data-kind="">
            <div class="ev-row ord-target-row">
              <label class="ord-soc-wrap">${t.orderSoc}<input type="number" class="ord-soc" min="1" max="100" step="1" value="90"></label>
              <label class="ord-temp-wrap" hidden>${t.orderTemp}<input type="number" class="ord-temp" min="20" max="95" step="0.5" value="55"></label>
            </div>
            <div class="ev-row">
              <label>${t.orderDate}<input type="date" class="ord-when-date"></label>
              <label>${t.orderTime}<input type="time" class="ord-when-time"></label>
            </div>
            <div class="ev-row">
              <button type="button" class="btn" data-ev="order">${t.orderCreate}</button>
              <button type="button" class="btn ghost" data-ev="clear-order">${t.orderClear}</button>
            </div>
            <div class="ev-row ev-only">
              <button type="button" class="btn" data-ev="boost">${t.boostStart}</button>
              <button type="button" class="btn warn" data-ev="stop-boost">${t.boostStop}</button>
            </div>
            <div class="ev-row ev-only">
              <label>${t.awayLeave}<input type="date" class="away-leave-date"><input type="time" class="away-leave-time"></label>
              <label>${t.awayReturn}<input type="date" class="away-return-date"><input type="time" class="away-return-time"></label>
            </div>
            <div class="ev-row ev-only">
              <button type="button" class="btn" data-ev="away">${t.awaySet}</button>
              <button type="button" class="btn ghost" data-ev="clear-away">${t.awayClear}</button>
            </div>
            <div class="ev-err" hidden></div>
          </div>
        </div>
      </div>`;
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
    const discussion = Array.isArray(rv?.discussion) ? rv.discussion : [];
    const chatBusy = d.review_running || d.review_asking || d.morning_running || d.charge_running;
    const mp = d.morning_plan;
    const cf = d.charge_forecast;
    const morningHtml = `
      <div class="rv-morning">
        <div class="rv-morning-top">
          <div class="rv-h">${t.morningPlan}</div>
          <button class="btn morning-now" ${chatBusy ? "disabled" : ""}>${d.morning_running ? t.morningRunning : t.morningNow}</button>
        </div>
        ${mp ? `<div class="rv-meta">${new Date(mp.at).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" })}${mp.dry_run ? ` · ${t.watchOnlyDay}` : ""}</div>
          <div class="rv-sum">${esc(mp.summary)}</div>
          ${list(t.morningExpect, mp.expectations, "outlook")}${list(t.morningRisks, mp.risks, "bad")}`
          : `<div class="rv-meta">${t.morningNone}</div>`}
      </div>`;
    const chargeHtml = `
      <div class="rv-morning rv-charge">
        <div class="rv-morning-top">
          <div class="rv-h">${t.chargeForecast}</div>
          <button class="btn charge-now" ${chatBusy ? "disabled" : ""}>${d.charge_running ? t.chargeRunning : t.chargeNow}</button>
        </div>
        ${cf ? `<div class="rv-meta">${new Date(cf.at).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" })}${cf.dry_run ? ` · ${t.watchOnlyDay}` : ""}</div>
          <div class="rv-sum">${esc(cf.summary)}</div>
          <div class="rv-sec outlook"><div class="rv-h">${t.chargeBattery}</div>
            <ul><li>~${esc(String(cf.battery_expected_soc ?? "–"))} %${cf.battery_note ? ` – ${esc(cf.battery_note)}` : ""}</li></ul>
          </div>
          ${list(t.chargeDevices, cf.devices, "outlook")}${list(t.chargeRisks, cf.risks, "bad")}`
          : `<div class="rv-meta">${t.chargeNone}</div>`}
      </div>`;
    const chatHtml = !rv ? "" : `
      <div class="rv-chat">
        ${discussion.map((turn) => `
          <div class="rv-turn q"><span class="who">${t.reviewYou}</span>${esc(turn.question)}</div>
          <div class="rv-turn a"><span class="who">${t.reviewAi}</span>${esc(turn.answer)}</div>
        `).join("")}
        <div class="rv-ask">
          <input class="rv-q" type="text" maxlength="500" placeholder="${esc(t.reviewAskPlaceholder)}" ${chatBusy ? "disabled" : ""} />
          <button class="btn rv-ask-btn" ${chatBusy ? "disabled" : ""}>${d.review_asking ? t.reviewAsking : t.reviewAsk}</button>
        </div>
      </div>`;
    const reviewBlock = !d.review_enabled ? `<div class="none">${t.reviewOff}</div>` : `
      <div class="review">
        ${morningHtml}
        ${chargeHtml}
        <div class="rv-top">
          ${rv ? `<div class="score ${scoreCls(rv.score)}">${rv.score}<small>/10</small></div>` : ""}
          <div class="rv-meta">
            ${rv ? `<div>${new Date(rv.at).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" })}${rv.dry_run ? ` · ${t.watchOnlyDay}` : ""}</div>` : `<div>${t.noReview}</div>`}
            ${d.review_error ? `<div class="err">${esc(d.review_error)}</div>` : ""}
          </div>
          <button class="btn review-now" ${chatBusy ? "disabled" : ""}>${d.review_running ? t.reviewing : t.reviewNow}</button>
        </div>
        ${rv ? `<div class="rv-sum">${esc(rv.summary)}</div>
          ${list(t.good, rv.good, "good")}${list(t.problems, rv.problems, "bad")}
          ${(() => {
            const props = Array.isArray(rv.proposals) ? rv.proposals : [];
            if (!props.length) return list(t.suggestions, rv.suggestions, "sugg");
            const fmtVal = (v) => (typeof v === "boolean" ? (v ? "on" : "off") : String(v));
            const statusLabel = (st) => (
              st === "applied" ? t.proposalApplied
                : st === "dismissed" ? t.proposalDismissed
                  : st === "invalid" ? t.proposalInvalid : ""
            );
            const rows = props.map((p) => {
              const st = p.status || "pending";
              const head = `${esc(p.target)} – ${esc(p.key)}: ${t.proposalFromTo} ${esc(fmtVal(p.from))} ${t.proposalTo} ${esc(fmtVal(p.to))}`;
              const reason = p.reason ? ` – ${esc(p.reason)}` : "";
              const err = p.error ? ` (${esc(p.error)})` : "";
              if (st === "pending") {
                return `<li class="rv-prop">
                  <div class="rv-prop-text">${head}${reason}</div>
                  <div class="rv-prop-actions">
                    <button class="btn prop-apply" data-id="${esc(p.id)}" ${chatBusy ? "disabled" : ""}>${t.proposalApply}</button>
                    <button class="btn prop-dismiss" data-id="${esc(p.id)}" ${chatBusy ? "disabled" : ""}>${t.proposalDismiss}</button>
                  </div>
                </li>`;
              }
              return `<li class="rv-prop done"><span class="rv-prop-text">${head}${reason}${err}</span><span class="rv-prop-st">${statusLabel(st)}</span></li>`;
            }).join("");
            return `<div class="rv-sec sugg"><div class="rv-h">${t.suggestions}</div><ul>${rows}</ul></div>`;
          })()}
          ${list(t.aiOutlook, rv.outlook, "outlook")}
          ${chatHtml}` : ""}
        ${history.length > 1 ? `<div class="rv-hist">${history.map((h) => `<div class="hb ${scoreCls(h.score)}" title="${h.date}: ${h.score}/10" style="height:${8 + h.score * 3}px"></div>`).join("")}</div>` : ""}
      </div>`;
    const time = (() => {
      if (!d.changed_at) return "";
      const dt = new Date(d.changed_at);
      if (Number.isNaN(dt.getTime())) return "";
      try { return dt.toLocaleTimeString(lang); } catch { return ""; }
    })();
    // sections: which parts to show (split the card over several columns).
    // summary = outlook + allocation + status (backward compatible).
    // flow is optional – Power Flow Card Plus does energy flows better.
    const sections = Array.isArray(cfg.sections) ? cfg.sections : ["summary", "devices", "log"];
    const show = new Set(sections);
    if (show.has("summary")) {
      show.add("outlook");
      show.add("allocation");
      show.add("status");
    }
    if (show.has("chips")) show.add("status"); // old name
    if (show.has("recommendations")) show.add("devices");
    const showStack = show.has("status") || show.has("devices");
    const chipsHtml = showStack ? `
      <div class="chips">
        ${modeChip}
        ${chip(
          d.battery_priority ? t.prioShortBat : t.prioShortDev,
          d.battery_priority ? "warn" : "",
          d.battery_priority ? t.prioBatHint : t.prioDevHint,
        )}
        ${d.hdo != null ? chip(d.hdo ? "NT" : "VT", d.hdo ? "ok" : "", t.tariffHint) : ""}
        ${d.borrow ? chip(t.borrowShort, "warn", t.borrowHint) : ""}
      </div>` : "";
    const keep = new Set();
    if (show.has("status")) { keep.add("grid"); keep.add("battery"); }
    if (show.has("devices")) { keep.add("device"); keep.add("export"); }
    const body = blocks.filter((b) => keep.has(b.kind)).map(renderBlock).join("");
    const doAllHtml = showStack && d.dry_run && pending.length > 1
      ? `<div class="doall"><span>${t.manualHint}</span>
        <button class="btn all" data-id="">${t.doAll}</button></div>` : "";
    const stackHtml = [
      chipsHtml,
      show.has("outlook") ? forecastHtml : "",
      show.has("outlook") ? metaHtml : "",
      show.has("allocation") ? budgetHtml : "",
      doAllHtml,
      body ? `<div class="stack">${body}</div>` : "",
    ].join("");
    const only = [...show].filter((s) => !["summary", "chips", "recommendations"].includes(s));
    const defaultTitle = only.length === 1 && only[0] === "log" ? t.decisions
      : only.length === 1 && only[0] === "review" ? t.review
        : only.length === 1 && only[0] === "outlook" ? t.outlook
          : only.length === 1 && only[0] === "allocation" ? t.budgetTargets
            : only.length === 1 && only[0] === "status" ? t.statusTitle
              : only.length === 2 && show.has("status") && show.has("devices") ? t.statusTitle
                : "FVE Optimizer";
    root.innerHTML = `
      <ha-card>
        ${cfg.title !== false ? `<h1 class="title">${cfg.title || defaultTitle}</h1>` : ""}
        ${show.has("flow") ? `<div class="headline">${d.headline || ""}</div>${svg}` : ""}
        ${stackHtml}
        ${show.has("review") ? reviewBlock : ""}
        ${show.has("log") ? logBlock.replace(`<div class="log-head">${t.decisions}</div>`, only.length === 1 && only[0] === "log" ? "" : `<div class="log-head">${t.decisions}</div>`) : ""}
        ${showStack ? `<div class="foot">${time}</div>` : ""}
        ${evModal}
      </ha-card>${STYLE}`;
    root.querySelector("button.review-now")?.addEventListener("click", (ev) => {
      ev.currentTarget.disabled = true;
      ev.currentTarget.textContent = t.reviewing;
      this._hass.callService("fve_optimizer", "run_review", {});
    });
    root.querySelector("button.morning-now")?.addEventListener("click", (ev) => {
      ev.currentTarget.disabled = true;
      ev.currentTarget.textContent = t.morningRunning;
      this._hass.callService("fve_optimizer", "run_morning_brief", {});
    });
    root.querySelector("button.charge-now")?.addEventListener("click", (ev) => {
      ev.currentTarget.disabled = true;
      ev.currentTarget.textContent = t.chargeRunning;
      this._hass.callService("fve_optimizer", "run_charge_forecast", {});
    });
    root.querySelectorAll("button.prop-apply").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        const id = ev.currentTarget.getAttribute("data-id");
        if (!id) return;
        ev.currentTarget.disabled = true;
        this._hass.callService("fve_optimizer", "apply_ai_proposal", { id });
      });
    });
    root.querySelectorAll("button.prop-dismiss").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        const id = ev.currentTarget.getAttribute("data-id");
        if (!id) return;
        ev.currentTarget.disabled = true;
        this._hass.callService("fve_optimizer", "dismiss_ai_proposal", { id });
      });
    });
    const askBtn = root.querySelector("button.rv-ask-btn");
    const askInput = root.querySelector("input.rv-q");
    if (askInput && this._askDraft?.value != null && !askInput.disabled) {
      askInput.value = this._askDraft.value;
      if (this._askDraft.focus) {
        askInput.focus();
        try {
          const s = this._askDraft.start ?? askInput.value.length;
          const e = this._askDraft.end ?? s;
          askInput.setSelectionRange(s, e);
        } catch { /* ignore */ }
      }
    }
    const sendAsk = () => {
      const q = (askInput?.value || "").trim();
      if (!q || !askBtn || askBtn.disabled) return;
      askBtn.disabled = true;
      askBtn.textContent = t.reviewAsking;
      if (askInput) askInput.disabled = true;
      this._askDraft = { value: "", sent: true };
      this._hass.callService("fve_optimizer", "ask_review", { question: q });
    };
    askBtn?.addEventListener("click", sendAsk);
    askInput?.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        sendAsk();
      }
    });
    askInput?.addEventListener("input", () => {
      this._askDraft = {
        value: askInput.value,
        start: askInput.selectionStart,
        end: askInput.selectionEnd,
        focus: document.activeElement === askInput,
      };
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
    const splitLocal = (d) => {
      try {
        const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
        const iso = local.toISOString();
        return { date: iso.slice(0, 10), time: iso.slice(11, 16) };
      } catch {
        return { date: "", time: "" };
      }
    };
    const joinLocal = (date, time) => {
      if (!date || !time) return "";
      const tpart = time.length === 5 ? `${time}:00` : time;
      return `${date} ${tpart}`;
    };
    const fillEvForm = (x, draft) => {
      if (!actions) return;
      const isEv = x.kind === "ev_charger";
      actions.dataset.kind = isEv ? "ev" : "boiler";
      const hint = root.querySelector(".ev-hint");
      if (hint) hint.textContent = isEv ? t.holdHint : t.holdHintBoiler;
      actions.querySelectorAll(".ev-only").forEach((el) => { el.hidden = !isEv; });
      actions.querySelector(".ord-soc-wrap")?.toggleAttribute("hidden", !isEv);
      actions.querySelector(".ord-temp-wrap")?.toggleAttribute("hidden", isEv);
      const socEl = actions.querySelector(".ord-soc");
      const tempEl = actions.querySelector(".ord-temp");
      const whenDate = actions.querySelector(".ord-when-date");
      const whenTime = actions.querySelector(".ord-when-time");
      const leaveDate = actions.querySelector(".away-leave-date");
      const leaveTime = actions.querySelector(".away-leave-time");
      const retDate = actions.querySelector(".away-return-date");
      const retTime = actions.querySelector(".away-return-time");
      if (socEl) {
        socEl.value = draft?.soc != null && draft.soc !== ""
          ? draft.soc
          : Math.round(x.charge_order?.soc || x.deadline_soc || x.target_soc || 90);
      }
      if (tempEl) {
        tempEl.value = draft?.temp != null && draft.temp !== ""
          ? draft.temp
          : (x.heat_order?.temp ?? x.deadline_temperature ?? x.max_temperature ?? 55);
      }
      const orderDeadline = isEv ? x.charge_order?.deadline : x.heat_order?.deadline;
      if (whenDate && whenTime) {
        if (draft?.whenDate) {
          whenDate.value = draft.whenDate;
          whenTime.value = draft.whenTime || "07:00";
        } else {
          try {
            const base = orderDeadline ? new Date(orderDeadline) : new Date(Date.now() + 86400000);
            base.setMinutes(0, 0, 0);
            if (!orderDeadline) base.setHours(isEv ? 7 : 18);
            const parts = splitLocal(base);
            whenDate.value = parts.date;
            whenTime.value = parts.time;
          } catch {
            whenDate.value = "";
            whenTime.value = "";
          }
        }
      }
      if (leaveDate && leaveTime) {
        if (draft?.leaveDate) {
          leaveDate.value = draft.leaveDate;
          leaveTime.value = draft.leaveTime || "12:00";
        } else if (x.away?.leave_at) {
          const parts = splitLocal(new Date(x.away.leave_at));
          leaveDate.value = parts.date;
          leaveTime.value = parts.time;
        } else {
          const leave = new Date();
          leave.setMinutes(0, 0, 0);
          leave.setHours(leave.getHours() + 3);
          const parts = splitLocal(leave);
          leaveDate.value = parts.date;
          leaveTime.value = parts.time;
        }
      }
      if (retDate && retTime) {
        if (draft?.retDate != null) {
          retDate.value = draft.retDate;
          retTime.value = draft.retTime || "";
        } else if (x.away?.return_at) {
          const parts = splitLocal(new Date(x.away.return_at));
          retDate.value = parts.date;
          retTime.value = parts.time;
        } else {
          retDate.value = "";
          retTime.value = "";
        }
      }
      const hasOrder = isEv ? !!x.charge_order : !!x.heat_order;
      actions.querySelector('[data-ev="clear-order"]')?.toggleAttribute("hidden", !hasOrder);
      actions.querySelector('[data-ev="stop-boost"]')?.toggleAttribute("hidden", !x.boost);
      actions.querySelector('[data-ev="boost"]')?.toggleAttribute("hidden", !!x.boost);
      actions.querySelector('[data-ev="clear-away"]')?.toggleAttribute("hidden", !x.away);
      actions.querySelector('[data-ev="away"]')?.toggleAttribute("hidden", !!x.away);
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
      const isEv = actions?.dataset.kind !== "boiler";
      const soc = Number(actions.querySelector(".ord-soc")?.value);
      const temp = Number(actions.querySelector(".ord-temp")?.value);
      const when = joinLocal(
        actions.querySelector(".ord-when-date")?.value,
        actions.querySelector(".ord-when-time")?.value,
      );
      const leave = joinLocal(
        actions.querySelector(".away-leave-date")?.value,
        actions.querySelector(".away-leave-time")?.value,
      );
      const ret = joinLocal(
        actions.querySelector(".away-return-date")?.value,
        actions.querySelector(".away-return-time")?.value,
      );
      btn.disabled = true;
      showEvErr("");
      let ok = true;
      if (act === "order") {
        if (!when || (isEv ? !soc : !temp)) { btn.disabled = false; return; }
        ok = await callEv(isEv ? "set_ev_charge_order" : "set_heat_order", isEv
          ? { device_id: id, target_soc: soc, deadline: when }
          : { device_id: id, target_temp: temp, deadline: when });
      } else if (act === "clear-order") {
        ok = await callEv(isEv ? "clear_ev_charge_order" : "clear_heat_order", { device_id: id });
      } else if (act === "boost") {
        const data = { device_id: id };
        if (soc) data.target_soc = soc;
        ok = await callEv("start_ev_boost", data);
      } else if (act === "stop-boost") {
        ok = await callEv("stop_ev_boost", { device_id: id });
      } else if (act === "away") {
        if (!leave) { btn.disabled = false; return; }
        const data = { device_id: id, leave_at: leave };
        if (ret) data.return_at = ret;
        ok = await callEv("set_ev_away", data);
      } else if (act === "clear-away") {
        ok = await callEv("clear_ev_away", { device_id: id });
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
  .meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin: 0 0 10px; }
  .meta.meta-1 { grid-template-columns: 1fr; }
  .meta.meta-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  @media (max-width: 420px) { .meta, .meta.meta-3 { grid-template-columns: 1fr; } }
  .meta-tile { padding: 10px 12px; border-radius: 10px; background: var(--secondary-background-color); min-width: 0; }
  .meta-label { font-size: 11px; text-transform: uppercase; letter-spacing: .02em;
    color: var(--secondary-text-color); margin-bottom: 2px; }
  .meta-value { font-size: 16px; font-weight: 500; font-variant-numeric: tabular-nums; line-height: 1.2;
    color: var(--primary-text-color); word-break: break-word; }
  .meta-sub { font-size: 12px; color: var(--secondary-text-color); margin-top: 3px; line-height: 1.3; }
  .meta-tile.ok .meta-value { color: var(--success-color, #43a047); }
  .meta-tile.warn .meta-value { color: var(--warning-color, #ff9800); }
  .fc { padding: 10px 12px; border-radius: 10px; background: var(--secondary-background-color); margin: 0 0 10px; }
  .fc-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 8px; }
  .fc-head .meta-label { margin: 0; }
  .fc-status { font-size: 12px; color: var(--secondary-text-color); text-align: right; }
  .fc.warn .fc-status { color: var(--warning-color, #ff9800); }
  .fc.ok .fc-status { color: var(--success-color, #43a047); }
  .fc-track { position: relative; height: 14px; margin: 2px 0 4px; }
  .fc-bar { display: flex; height: 100%; border-radius: 6px; overflow: hidden;
    background: color-mix(in srgb, var(--divider-color, #555) 35%, transparent); }
  .fc-seg { height: 100%; min-width: 0; }
  .fc-seg.bat { background: var(--info-color, #039be5); }
  .fc-seg.house { background: var(--primary-color, #03a9f4); opacity: .75; }
  .fc-seg.margin { background: var(--divider-color, #888); opacity: .85; }
  .fc-seg.need { background: var(--warning-color, #ff9800); opacity: .55; }
  .fc-mark { position: absolute; top: -2px; bottom: -2px; width: 2px; margin-left: -1px;
    background: var(--warning-color, #ff9800); border-radius: 1px; pointer-events: none;
    box-shadow: 0 0 0 1px rgba(0,0,0,.35); z-index: 1; }
  .fc.ok .fc-mark { background: var(--success-color, #43a047); }
  .fc-legend { display: flex; flex-wrap: wrap; gap: 8px 12px; margin-top: 6px; font-size: 11px;
    color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .fc-leg::before { content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 2px;
    margin-right: 4px; vertical-align: 0; }
  .fc-leg.bat::before { background: var(--info-color, #039be5); }
  .fc-leg.house::before { background: var(--primary-color, #03a9f4); opacity: .85; }
  .fc-leg.margin::before { background: var(--divider-color, #888); }
  .fc-leg.mark::before { width: 2px; height: 10px; border-radius: 1px; background: var(--warning-color, #ff9800); }
  .fc.ok .fc-leg.mark::before { background: var(--success-color, #43a047); }
  .fc-unit { margin-left: auto; opacity: .8; }
  .fc-outlook { margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--divider-color, #ddd); }
  .fc-outlook .ol-row { display: flex; gap: 10px; font-size: 13px; line-height: 1.35; padding: 2px 0; }
  .fc-outlook .ol-name { flex: 0 0 28%; min-width: 4.5em; color: var(--secondary-text-color); }
  .fc-outlook .ol-text { flex: 1; min-width: 0; }
  .fc-outlook .ol-row.warn .ol-text { color: var(--warning-color, #ff9800); }
  .budget-flow { padding: 10px 12px; border-radius: 10px;
    background: var(--secondary-background-color); margin: 0 0 10px; }
  .bf-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 8px; }
  .bf-head .meta-label { margin: 0; }
  .bf-total { font-size: 14px; font-weight: 500; font-variant-numeric: tabular-nums; }
  .bf-stack-wrap { position: relative; margin-bottom: 2px; }
  .bf-stack { display: flex; height: 16px; border-radius: 8px; overflow: hidden;
    background: color-mix(in srgb, var(--divider-color, #555) 35%, transparent); }
  .bf-seg { height: 100%; min-width: 0; flex-shrink: 0; }
  .bf-seg.bf-empty { background: transparent; }
  .bf-mark { position: absolute; top: -3px; bottom: -3px; width: 2px; margin-left: -1px;
    background: var(--primary-text-color); border-radius: 1px; box-shadow: 0 0 0 1px rgba(0,0,0,.35); z-index: 1; }
  .bf-mark-label { font-size: 10px; color: var(--secondary-text-color); margin: 2px 0 8px;
    white-space: nowrap; transform: translateX(-50%); max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
  .bf-rows { display: flex; flex-direction: column; gap: 5px; }
  .bf-row { display: grid; grid-template-columns: 10px minmax(4em, 26%) 1fr auto; gap: 8px; align-items: center; }
  .bf-row.dim { opacity: .55; }
  .bf-dot { width: 8px; height: 8px; border-radius: 2px; }
  .bf-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bf-track { height: 8px; border-radius: 4px; overflow: hidden;
    background: color-mix(in srgb, var(--divider-color, #555) 30%, transparent); }
  .bf-fill { height: 100%; border-radius: 4px; min-width: 0; }
  .bf-val { font-size: 12px; font-weight: 500; font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
  .bf-foot { margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--divider-color, #ddd);
    display: flex; flex-direction: column; gap: 2px; font-size: 12px; color: var(--secondary-text-color);
    font-variant-numeric: tabular-nums; }
  .bf-foot-row { display: flex; justify-content: space-between; gap: 8px; }
  .bf-foot-row.warn { color: var(--warning-color, #ff9800); }
  .stack { display: flex; flex-direction: column; gap: 6px; margin: 0 0 8px; }
  .block { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px;
    background: var(--secondary-background-color); opacity: .78; }
  .block.on { opacity: 1; }
  .block.pending { outline: 1px solid var(--warning-color, #ff9800); opacity: 1; }
  .block.ok .pw { color: var(--success-color, #43a047); }
  .block.ok ha-icon { color: var(--success-color, #43a047); }
  .block.warn .pw { color: var(--warning-color, #ff9800); }
  .block.imp .pw { color: var(--error-color, #db4437); }
  .block.imp ha-icon { color: var(--error-color, #db4437); }
  .block ha-icon { color: var(--secondary-text-color); --mdc-icon-size: 22px; flex-shrink: 0; }
  .block.on:not(.ok):not(.imp) ha-icon { color: var(--primary-color); }
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
    color: var(--secondary-text-color); flex: 1 1 8em; min-width: 6em; }
  .ev-row .ord-temp-wrap[hidden], .ev-row .ord-soc-wrap[hidden], .ev-row.ev-only[hidden] { display: none !important; }
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
  .rv-prop { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px; margin-bottom: 4px; }
  .rv-prop.done { opacity: 0.7; }
  .rv-prop-text { flex: 1 1 12em; }
  .rv-prop-actions { display: flex; gap: 4px; }
  .rv-prop-actions .btn { font-size: 12px; padding: 2px 8px; }
  .rv-prop-st { font-size: 11px; color: var(--secondary-text-color); text-transform: lowercase; }
  .rv-hist { display: flex; align-items: flex-end; gap: 3px; height: 42px; margin-top: 8px; }
  .hb { width: 10px; border-radius: 2px; }
  .hb.ok { background: var(--success-color, #43a047); }
  .hb.mid { background: var(--warning-color, #ff9800); }
  .hb.bad { background: var(--error-color, #db4437); }
  .rv-morning { margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid var(--divider-color); }
  .rv-morning-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px; }
  .rv-chat { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--divider-color); }
  .rv-turn { font-size: 13px; margin: 6px 0; white-space: pre-wrap; }
  .rv-turn .who { display: block; font-size: 11px; color: var(--secondary-text-color); margin-bottom: 2px; }
  .rv-turn.q { color: var(--primary-text-color); }
  .rv-turn.a { color: var(--info-color, #039be5); }
  .rv-ask { display: flex; gap: 8px; margin-top: 8px; align-items: center; }
  .rv-q { flex: 1; min-width: 0; font: inherit; font-size: 13px; padding: 6px 8px;
    border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color);
    color: var(--primary-text-color); }
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

/** Thin picker presets: same card, different default sections. */
function definePreset(tag, { name, description, sections }) {
  const Base = customElements.get(TAG) || FveOptimizerCard;
  class Preset extends Base {
    setConfig(config) {
      super.setConfig({
        ...config,
        sections: config?.sections?.length ? config.sections : sections,
      });
    }
    static getStubConfig(hass) {
      return {
        entity: FveOptimizerCard.findStatusEntity(hass),
        sections: [...sections],
      };
    }
  }
  if (!customElements.get(tag)) customElements.define(tag, Preset);
  else {
    for (const key of Object.getOwnPropertyNames(Preset.prototype)) {
      if (key === "constructor") continue;
      const desc = Object.getOwnPropertyDescriptor(Preset.prototype, key);
      if (desc) Object.defineProperty(customElements.get(tag).prototype, key, desc);
    }
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === tag)) {
    window.customCards.push({ type: tag, name, description, preview: false });
  }
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === TAG)) {
  window.customCards.push({
    type: TAG,
    name: "FVE Optimizer",
    description: "Celý přehled: předpoklad, rozdělení, stav, zařízení a rozhodnutí.",
    preview: false,
  });
}

definePreset("fve-optimizer-outlook-card", {
  name: "FVE Optimizer – Předpoklad dne",
  description: "Predikce výroby a předpoklad dne (baterie, zařízení).",
  sections: ["outlook"],
});
definePreset("fve-optimizer-allocation-card", {
  name: "FVE Optimizer – Rozdělení",
  description: "Rozpočet a rozdělení mezi zařízení, baterii a síť.",
  sections: ["allocation"],
});
definePreset("fve-optimizer-status-card", {
  name: "FVE Optimizer – Stav",
  description: "Síť, baterie a řízená zařízení.",
  sections: ["status", "devices"],
});
definePreset("fve-optimizer-log-card", {
  name: "FVE Optimizer – Rozhodnutí",
  description: "Log rozhodnutí Optimizeru.",
  sections: ["log"],
});
definePreset("fve-optimizer-review-card", {
  name: "FVE Optimizer – Hodnocení",
  description: "AI hodnocení, ranní předpoklad a předpověď nabití.",
  sections: ["review"],
});
