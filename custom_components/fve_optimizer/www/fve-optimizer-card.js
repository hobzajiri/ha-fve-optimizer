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
    forecast: "Predikce", need: "potřeba", breaker: "Jistič", noData: "Čekám na data z FVE Optimizeru…",
    urgent: "termín", minFirst: "před baterií", atRisk: "nestihne", plan: "plán",
    batteryFirst: "Přednost baterie", devicesFirst: "Přednost zařízení",
    dryRun: "Jen sledování – povely proveď ručně", failsafe: "Pojistka – chybí data ze střídače",
    recs: "Doporučení", doIt: "Provést", doAll: "Provést vše", since: "od",
    device: "Zařízení", wanted: "Doporučeno", now: "Teď", on: "Zap", off: "Vyp",
    charge: "Nabíjet", noCharge: "Nenabíjet", exportLimit: "Limit přetoku", manual: "proveď ručně",
    decisions: "Rozhodnutí", planned: "doporučeno",
    mode: "Režim", auto: "Řídí automaticky", priority: "Priorita", prioBattery: "baterie",
    prioDevices: "zařízení", tariff: "Tarif", raised: "zvýšený", normal: "běžný", reserve: "rezerva",
    borrowShort: "dorovnání z baterie", turnOn: "zapnout", turnOff: "vypnout", stop: "zastavit nabíjení",
    setTo: "nastavit", inProgress: "provádí se", manualHint: "Doporučení proveď ručně",
    until: "do", then: "pak", price: "Cena", today: "dnes", notControlled: "neřízeno",
    review: "AI hodnocení", reviewNow: "Vyhodnotit nyní", reviewing: "Vyhodnocuji…", noReview: "Zatím žádné hodnocení.",
    reviewOff: "AI hodnocení není nastavené – vyber AI Task entitu v nastavení FVE Optimizeru (krok Řízení).",
    good: "Co fungovalo", problems: "Problémy", suggestions: "Návrhy úprav", watchOnlyDay: "den v režimu Jen sledovat",
    statsHint: "Spotřeba dnes, náklady za energii ze sítě (NT/VT) a podíl ze slunce",
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
    recs: "Recommendations", doIt: "Do it", doAll: "Do all", since: "since",
    device: "Device", wanted: "Recommended", now: "Now", on: "On", off: "Off",
    charge: "Charge", noCharge: "Don't charge", exportLimit: "Export limit", manual: "do by hand",
    decisions: "Decisions", planned: "recommended",
    mode: "Mode", auto: "Automatic control", priority: "Priority", prioBattery: "battery",
    prioDevices: "devices", tariff: "Tariff", raised: "raised", normal: "normal", reserve: "headroom",
    borrowShort: "rounding up from battery", turnOn: "turn on", turnOff: "turn off", stop: "stop charging",
    setTo: "set", inProgress: "in progress", manualHint: "Carry out the recommendations by hand",
    until: "until", then: "then", price: "Price", today: "today", notControlled: "not controlled",
    review: "AI review", reviewNow: "Review now", reviewing: "Reviewing…", noReview: "No review yet.",
    reviewOff: "AI review is not set up – choose an AI Task entity in the FVE Optimizer settings (Control step).",
    good: "What worked", problems: "Problems", suggestions: "Suggested changes", watchOnlyDay: "watch-only day",
    statsHint: "Consumption today, cost of grid energy (NT/VT) and solar share",
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

    const lang = this._hass?.locale?.language || this._hass?.language || undefined;
    const tf = new Intl.DateTimeFormat(lang, { hour: "2-digit", minute: "2-digit" });
    const hhmm = (iso) => (iso ? tf.format(new Date(iso)) : "");

    // --- Tariff: current window, the next one and prices -----------------------
    const tariffText = () => {
      const nt = d.hdo === true;
      const name = d.hdo == null ? "" : nt ? "NT" : "VT";
      const win = d.hdo_window, next = d.hdo_next_window;
      let span = "";
      if (nt && win) span = ` ${t.until} ${hhmm(win[1])}${next ? `, ${t.then} VT ${t.until} ${hhmm(next[0])}` : ""}`;
      else if (!nt && next) span = ` ${t.until} ${hhmm(next[0])}, ${t.then} NT ${hhmm(next[0])}–${hhmm(next[1])}`;
      return `${name}${span}`.trim();
    };
    const priceText = () => {
      const nt = d.hdo === true;
      const cur = d.hdo == null ? null : nt ? d.price_nt : d.price_vt;
      const other = nt ? d.price_vt : d.price_nt;
      if (cur) return `${num(cur, 2)} Kč/kWh${other ? ` (${nt ? "VT" : "NT"} ${num(other, 2)})` : ""}`;
      return `NT ${num(d.price_nt, 2)} / VT ${num(d.price_vt, 2)} Kč/kWh`;
    };

    // --- Summary: labelled key/value pairs (replaces the old badges) ------------
    const kv = (label, value, cls = "") => `<div class="k">${label}</div><div class="v ${cls}">${value}</div>`;
    const unit = d.export_limit_unit ? ` ${d.export_limit_unit}` : "";
    const summary = [
      kv(t.mode, d.reason === "failsafe" ? t.failsafe : d.dry_run ? t.dryRun : t.auto,
        d.reason === "failsafe" ? "warn" : d.dry_run ? "info" : "ok"),
      kv(t.priority, `${d.battery_priority ? t.prioBattery : t.prioDevices} · ${t.battery.toLowerCase()} ${Math.round(Number(d.battery_soc) || 0)} % (${t.target} ${Math.round(Number(d.battery_target_soc) || 0)} %)`,
        d.battery_priority ? "warn" : ""),
      kv(t.surplus, `${fmtW(d.budget_w)} · ${t.allocated} ${fmtW(d.allocated_w)}${d.borrow ? ` · ${t.borrowShort}` : ""}`),
      d.forecast_kwh != null
        ? kv(t.forecast, `${num(d.forecast_kwh)} kWh, ${t.need} ${num(d.forecast_need_kwh)} kWh ${d.forecast_covers ? "✔" : "✘"}`,
          d.forecast_covers ? "" : "warn") : "",
      d.hdo != null ? kv(t.tariff, tariffText()) : "",
      d.price_vt || d.price_nt ? kv(t.price, priceText()) : "",
      d.headroom_a != null ? kv(t.breaker, `${t.reserve} ${num(d.headroom_a)} A`, d.headroom_a < 3 ? "warn" : "") : "",
    ].join("");

    // --- Devices with their recommendation --------------------------------------
    const recs = d.recommendations || [];
    const recById = Object.fromEntries(recs.map((r) => [r.id, r]));
    const items = devices.map((x) => {
      const now = x.now || {};
      const det = [];
      const curA = now.current != null ? Math.round(now.current) : null;
      if (now.on && curA) det.push(`${now.phases ?? "?"}f · ${curA} A`);
      if (x.temperature != null) det.push(`${num(x.temperature)} °C`);
      if (x.soc != null) det.push(`SoC ${Math.round(x.soc)} %`);
      if (x.plan && x.plan.length) det.push(`${t.plan} ${x.plan.join(", ")}`);
      const td = x.today || {};
      const stats = td.total > 0.005
        ? `${t.today} ${num(td.total, 1)} kWh · ${num(td.cost, 2)} Kč · ☀ ${Math.round((100 * (td.solar || 0)) / td.total)} %`
        : "";
      let wanted = "";
      if (x.pending) {
        wanted = x.kind === "ev_charger"
          ? (x.active ? `${t.charge.toLowerCase()} ${fmtW(x.allocated_w)} (${x.current} A · ${x.phases}f)` : t.stop)
          : (x.active ? `${t.turnOn} (${fmtW(x.allocated_w)})` : t.turnOff);
      }
      return {
        id: x.id, icon: ICON[x.kind] || "mdi:power-plug", name: x.name, state: x.state,
        on: !!now.on, power: fmtW(x.actual_w), det, stats, wanted, rec: recById[x.id],
        tags: [
          x.urgent ? `<span class="tag urg">⚡ ${t.urgent}</span>` : "",
          x.min_first ? `<span class="tag min">⬆ ${t.minFirst}</span>` : "",
          x.at_risk ? `<span class="tag urg">⚠ ${t.atRisk}</span>` : "",
        ].join(""),
      };
    });
    // Export limit: always listed (current value), with a recommendation when it should change.
    if (d.export_limit_now != null || d.export_limit_target != null) {
      const controlled = d.export_limit_controlled !== false && d.export_limit_target != null;
      const diff = controlled
        && (d.export_limit_now == null || Math.abs(d.export_limit_now - d.export_limit_target) >= 0.5);
      items.push({
        id: "export_limit", icon: "mdi:transmission-tower-export", name: t.exportLimit,
        state: controlled ? (d.export_raised ? t.raised : t.normal) : t.notControlled,
        on: controlled, power: `${d.export_limit_now ?? "?"}${unit}`, det: [], stats: "", tags: "",
        wanted: diff ? `${t.setTo} ${d.export_limit_target}${unit}` : "", rec: recById.export_limit,
      });
    }
    const pending = items.filter((i) => i.rec);
    const rows = `
      ${d.dry_run && pending.length > 1 ? `<div class="doall"><span>${t.manualHint}</span>
        <button class="btn all" data-id="">${t.doAll}</button></div>` : ""}
      ${items.map((i) => `
        <div class="row ${i.on ? "on" : ""} ${i.wanted ? "pending" : ""}">
          <ha-icon icon="${i.icon}"></ha-icon>
          <div class="main">
            <div class="name">${i.name}${i.state ? ` <span class="state">${i.state}</span>` : ""} ${i.tags}</div>
            ${i.det.length ? `<div class="det">${i.det.join(" · ")}</div>` : ""}
            ${i.stats ? `<div class="det stats" title="${t.statsHint}">${i.stats}</div>` : ""}
            ${i.wanted ? `<div class="want">➜ ${t.planned}: <b>${i.wanted}</b>${!d.dry_run ? ` · ${t.inProgress}` : ""}</div>` : ""}
          </div>
          <div class="side">
            <div class="pw">${i.power}</div>
            ${d.dry_run && i.rec ? `<button class="btn" data-id="${i.id}" title="${t.since} ${hhmm(i.rec.since)}">${t.doIt}</button>` : ""}
          </div>
        </div>`).join("")}`;
    const logSize = this._config.log === false ? 0 : Number(this._config.log ?? 20);
    const log = (d.log || []).slice(0, logSize);
    // Show only what changed against the previous (older) decision.
    const all = d.log || [];
    const changed = (i) => {
      const parts = all[i].text.split(" · ");
      const older = all[i + 1] ? new Set(all[i + 1].text.split(" · ")) : null;
      const diff = older ? parts.filter((p) => !older.has(p)) : parts;
      return (diff.length ? diff : parts).join(" · ");
    };
    const esc = (x) => x.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
    const logBlock = !log.length ? "" : `
      <div class="log">
        <div class="log-head">${t.decisions}</div>
        ${log.map((l, i) => `<div class="le${i === 0 ? " newest" : ""}" title="${esc(l.text)}"><span class="lt">${hhmm(l.at)}</span><span class="lx">${esc(changed(i))}</span></div>`).join("")}
      </div>`;
    // --- AI review ----------------------------------------------------------------
    const rv = d.review;
    const lines = (txt) => (txt || "").split("\n").map((l) => l.replace(/^\s*[-•*]\s*/, "").trim())
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
          ${list(t.good, rv.good, "good")}${list(t.problems, rv.problems, "bad")}${list(t.suggestions, rv.suggestions, "sugg")}` : ""}
        ${history.length > 1 ? `<div class="rv-hist">${history.map((h) => `<div class="hb ${scoreCls(h.score)}" title="${h.date}: ${h.score}/10" style="height:${8 + h.score * 3}px"></div>`).join("")}</div>` : ""}
      </div>`;
    const time = d.changed_at ? new Date(d.changed_at).toLocaleTimeString(lang) : "";
    // sections: which parts to show (split the card over several columns).
    // The power flow diagram is optional – Power Flow Card Plus does it better.
    const show = new Set(this._config.sections || ["summary", "devices", "log"]);
    if (show.has("chips")) show.add("summary"); // old names
    if (show.has("recommendations")) show.add("devices");
    const defaultTitle = show.size === 1 && show.has("log") ? t.decisions
      : show.size === 1 && show.has("review") ? t.review : "FVE Optimizer";
    root.innerHTML = `
      <ha-card>
        ${this._config.title !== false ? `<h1 class="title">${this._config.title || defaultTitle}</h1>` : ""}
        ${show.has("flow") ? `<div class="headline">${d.headline || ""}</div>${svg}` : ""}
        ${show.has("summary") ? `<div class="summary">${summary}</div>` : ""}
        ${show.has("devices") ? `<div class="rows">${rows}</div>` : ""}
        ${show.has("review") ? reviewBlock : ""}
        ${show.has("log") ? logBlock.replace(`<div class="log-head">${t.decisions}</div>`, show.size === 1 ? "" : `<div class="log-head">${t.decisions}</div>`) : ""}
        ${show.has("summary") ? `<div class="foot">${time}</div>` : ""}
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
  .summary { display: grid; grid-template-columns: max-content 1fr; gap: 3px 12px; font-size: 13px;
    margin: 4px 0 12px; }
  .summary .k { color: var(--secondary-text-color); }
  .summary .v.ok { color: var(--success-color, #43a047); }
  .summary .v.warn { color: var(--warning-color, #ff9800); }
  .summary .v.info { color: var(--info-color, #039be5); }
  .row.pending { outline: 1px solid var(--warning-color, #ff9800); }
  .det.stats { opacity: .85; }
  .want { font-size: 12px; color: var(--warning-color, #ff9800); margin-top: 2px; }
  .side { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
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
  .rv-hist { display: flex; align-items: flex-end; gap: 3px; height: 42px; margin-top: 8px; }
  .hb { width: 10px; border-radius: 2px; }
  .hb.ok { background: var(--success-color, #43a047); }
  .hb.mid { background: var(--warning-color, #ff9800); }
  .hb.bad { background: var(--error-color, #db4437); }
  .foot { text-align: right; font-size: 11px; color: var(--secondary-text-color); margin-top: 6px; }
</style>`;

customElements.define("fve-optimizer-card", FveOptimizerCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "fve-optimizer-card",
  name: "FVE Optimizer",
  description: "Power flow and decisions of the FVE Optimizer integration.",
});
