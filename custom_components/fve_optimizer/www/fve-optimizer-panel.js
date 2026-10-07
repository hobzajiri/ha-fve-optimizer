/*
 * FVE Optimizer sidebar panel – registered by the integration itself.
 *
 * Finds the integration's entities in the entity registry (by platform and
 * translation key, so entity IDs / languages / areas do not matter) and lays
 * out standard Home Assistant cards around the FVE Optimizer card:
 * overview, power history + decision logbook, stats, AI review, settings.
 */

const L = {
  cs: {
    title: "FVE Optimizer", power: "Výkon (24 h)", log: "Rozhodnutí (24 h)",
    control: "Řízení", settings: "Nastavení", costs: "Náklady po dnech (Kč)", energy: "Energie po dnech podle zdroje",
    tabOverview: "Přehled", tabHistory: "Historie", tabStats: "Statistiky", tabReview: "Hodnocení",
    reviewLog: "Hodnocení za 14 dní", noEntry: "FVE Optimizer zatím není nastavený.",
    noHelpers: "Grafy a nastavení se nepodařilo načíst (karty Home Assistantu nejsou k dispozici).",
    loading: "Načítám…", retry: "Zkusit znovu",
  },
  en: {
    title: "FVE Optimizer", power: "Power (24 h)", log: "Decisions (24 h)",
    control: "Control", settings: "Settings", costs: "Cost per day", energy: "Energy per day by source",
    tabOverview: "Overview", tabHistory: "History", tabStats: "Statistics", tabReview: "Review",
    reviewLog: "Reviews (14 days)", noEntry: "FVE Optimizer is not set up yet.",
    noHelpers: "Graphs and settings could not be loaded (Home Assistant cards are not available).",
    loading: "Loading…", retry: "Try again",
  },
};

const timeout = (ms) => new Promise((resolve) => setTimeout(() => resolve("timeout"), ms));
const PANEL_INSTANCES = (window.__fveOptimizerPanels = window.__fveOptimizerPanels || new Set());

/*
 * window.loadCardHelpers exists only after the frontend loaded Lovelace (any
 * dashboard visited). After a page reload straight into this panel it does
 * not, so make the frontend load the Lovelace panel code: the panel resolver
 * loads it and a hidden ha-panel-lovelace pulls in the card helpers. Every
 * step has a time limit – the panel never waits forever.
 */
async function loadHelpers(hass) {
  if (!window.loadCardHelpers) {
    try {
      await Promise.race([customElements.whenDefined("partial-panel-resolver"), timeout(3000)]);
      const resolver = document.createElement("partial-panel-resolver");
      resolver.hass = { panels: [{ url_path: "tmp", component_name: "lovelace" }] };
      resolver._updateRoutes?.();
      const route = resolver.routerOptions?.routes?.tmp;
      if (route?.load) await Promise.race([route.load(), timeout(5000)]);
      if (customElements.get("ha-panel-lovelace")) {
        const lovelace = document.createElement("ha-panel-lovelace");
        lovelace.hass = hass;
        lovelace.panel = { config: { mode: null } };
        lovelace._fetchConfig?.();
      }
    } catch (e) {
      console.debug("FVE Optimizer: loading Lovelace failed", e);
    }
  }
  for (let i = 0; i < 50 && !window.loadCardHelpers; i++) await timeout(100);
  if (!window.loadCardHelpers) return null;
  const helpers = await Promise.race([window.loadCardHelpers(), timeout(5000)]);
  return helpers === "timeout" ? null : helpers;
}

class FveOptimizerPanel extends HTMLElement {
  connectedCallback() {
    PANEL_INSTANCES.add(this);
  }

  disconnectedCallback() {
    PANEL_INSTANCES.delete(this);
  }

  set hass(hass) {
    if (!hass) return;
    this._hass = hass;
    if (!this._building && !this._cards) this._build();
    (this._cards || []).forEach((c) => (c.hass = hass));
  }

  set narrow(v) { this._narrow = v; }
  set panel(v) { this._panel = v; }

  _t() {
    const lang = this._hass?.locale?.language || this._hass?.language || "en";
    return lang.startsWith("cs") ? L.cs : L.en;
  }

  _entities() {
    const all = Object.values(this._hass.entities || {}).filter((e) => e.platform === "fve_optimizer");
    const hub = {};
    const devices = {};
    for (const e of all) {
      const key = e.translation_key || "";
      if (key.startsWith("device_")) {
        (devices[e.device_id] ||= {})[key.slice(7)] = e;
      } else if (key) {
        hub[key] = e;
      }
    }
    return { hub, devices, all };
  }

  async _build() {
    this._building = true;
    const t = this._t();
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const root = this.shadowRoot;
    root.innerHTML = `${PANEL_STYLE}<div class="toolbar"><ha-menu-button></ha-menu-button><h1>${t.title}</h1></div>
      <div class="tabs"></div><div class="content"></div>`;
    const menu = root.querySelector("ha-menu-button");
    if (menu) { menu.hass = this._hass; menu.narrow = this._narrow; }
    const content = root.querySelector(".content");

    content.innerHTML = `<div class="msg">${t.loading}</div>`;
    const helpers = await loadHelpers(this._hass);
    content.innerHTML = "";
    if (!helpers) {
      // Fallback: our own card needs no Lovelace helpers.
      await Promise.race([customElements.whenDefined("fve-optimizer-card"), timeout(3000)]);
      const { hub } = this._entities();
      content.innerHTML = `<div class="msg">${t.noHelpers} <button class="retry">${t.retry}</button></div>`;
      content.querySelector(".retry").addEventListener("click", () => {
        this._cards = null;
        this._build();
      });
      this._cards = [];
      if (hub.status && customElements.get("fve-optimizer-card")) {
        const page = document.createElement("div");
        page.className = "page";
        for (const sections of [["summary", "devices"], ["log"]]) {
          const col = document.createElement("div");
          col.className = "col";
          const card = document.createElement("fve-optimizer-card");
          card.setConfig({ entity: hub.status.entity_id, sections });
          card.hass = this._hass;
          col.appendChild(card);
          page.appendChild(col);
          this._cards.push(card);
        }
        content.appendChild(page);
      }
      this._building = false;
      return;
    }
    await Promise.race([customElements.whenDefined("fve-optimizer-card"), new Promise((r) => setTimeout(r, 3000))]);

    const { hub, devices } = this._entities();
    if (!hub.status) {
      content.innerHTML = `<div class="msg">${t.noEntry}</div>`;
      this._cards = [];
      this._building = false;
      return;
    }
    const id = (e) => e && e.entity_id;
    const ids = (...list) => list.map(id).filter(Boolean);
    const devList = Object.entries(devices).map(([deviceId, ents]) => ({
      deviceId, ents, name: this._hass.devices?.[deviceId]?.name || "",
    }));
    const configOf = (ents) => Object.values(ents).filter((e) => e.entity_category === "config")
      .map((e) => e.entity_id).sort();
    const status = id(hub.status);

    // Each tab: columns of cards (side by side on wide screens, stacked on narrow).
    const tabs = [
      {
        key: "overview", title: t.tabOverview, columns: [
          [{ type: "custom:fve-optimizer-card", entity: status, sections: ["summary", "devices"] }],
          [
            { type: "entities", title: t.control, show_header_toggle: false,
              entities: ids(hub.enabled, hub.dry_run, ...devList.map((d) => d.ents.control)) },
            { type: "custom:fve-optimizer-card", entity: status, sections: ["log"] },
          ],
        ],
      },
      {
        key: "history", title: t.tabHistory, columns: [
          [{ type: "history-graph", title: t.power, hours_to_show: 24,
            entities: ids(hub.budget, hub.allocated, ...devList.map((d) => d.ents.allocated)) }],
          [{ type: "logbook", title: t.log, hours_to_show: 24,
            entities: ids(hub.last_decision, hub.recommendations) }],
        ],
      },
      {
        key: "stats", title: t.tabStats, columns: [
          [{ type: "statistics-graph", title: t.costs, chart_type: "bar", period: "day", days_to_show: 14,
            stat_types: ["change"], entities: ids(...devList.map((d) => d.ents.cost)) }],
          [{ type: "statistics-graph", title: t.energy, chart_type: "bar", period: "day", days_to_show: 14,
            stat_types: ["change"],
            entities: ids(...devList.flatMap((d) => [d.ents.energy_solar, d.ents.energy_battery, d.ents.energy_grid])) }],
        ],
      },
      {
        key: "review", title: t.tabReview, columns: [
          [{ type: "custom:fve-optimizer-card", entity: status, sections: ["review"] }],
          [{ type: "logbook", title: t.reviewLog, hours_to_show: 24 * 14, entities: ids(hub.ai_review) }],
        ],
      },
      {
        key: "settings", title: t.settings, columns: [
          [{ type: "entities", title: t.title, entities: configOf(hub) }],
          devList.map((d) => ({ type: "entities", title: d.name, entities: configOf(d.ents) })),
        ],
      },
    ];

    const tabBar = root.querySelector(".tabs");
    let active = "overview";
    try { active = localStorage.getItem("fve-optimizer-tab") || active; } catch (e) { /* private mode */ }
    if (!tabs.some((tab) => tab.key === active)) active = "overview";
    this._cards = [];
    const pages = {};
    for (const tab of tabs) {
      const button = document.createElement("button");
      button.textContent = tab.title;
      button.dataset.key = tab.key;
      tabBar.appendChild(button);
      const page = document.createElement("div");
      page.className = "page";
      for (const column of tab.columns) {
        const col = document.createElement("div");
        col.className = "col";
        for (const config of column) {
          if (config.entities && !config.entities.length) continue;
          const card = helpers.createCardElement(config);
          card.hass = this._hass;
          col.appendChild(card);
          this._cards.push(card);
        }
        if (col.children.length) page.appendChild(col);
      }
      content.appendChild(page);
      pages[tab.key] = { page, button };
    }
    const select = (key) => {
      for (const [k, { page, button }] of Object.entries(pages)) {
        page.hidden = k !== key;
        button.classList.toggle("active", k === key);
      }
      try { localStorage.setItem("fve-optimizer-tab", key); } catch (e) { /* ignore */ }
      // Graphs size themselves when they become visible.
      window.dispatchEvent(new Event("resize"));
    };
    tabBar.addEventListener("click", (ev) => {
      const key = ev.target?.dataset?.key;
      if (key) select(key);
    });
    select(active);
    this._building = false;
  }
}

const PANEL_STYLE = `<style>
  :host { display: block; background: var(--primary-background-color); min-height: 100vh; }
  .toolbar { display: flex; align-items: center; gap: 8px; height: 56px; padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); }
  .toolbar h1 { font-size: 20px; font-weight: 400; margin: 0; }
  .tabs { display: flex; gap: 4px; padding: 0 12px; background: var(--app-header-background-color, var(--primary-color));
    overflow-x: auto; }
  .tabs button { font: inherit; font-size: 14px; color: var(--app-header-text-color, #fff); opacity: .7;
    background: none; border: none; border-bottom: 2px solid transparent; padding: 10px 14px; cursor: pointer; }
  .tabs button.active { opacity: 1; border-bottom-color: var(--app-header-text-color, #fff); }
  .content { padding: 12px; }
  .page { display: flex; gap: 12px; align-items: flex-start; max-width: 1200px; margin: 0 auto; }
  .page[hidden] { display: none; }
  .col { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
  @media (max-width: 800px) { .page { flex-direction: column; align-items: stretch; } }
  .msg { padding: 12px 12px 16px; color: var(--secondary-text-color); }
  .msg .retry { font: inherit; margin-left: 8px; padding: 4px 12px; border-radius: 12px; cursor: pointer;
    border: 1px solid var(--primary-color); background: none; color: var(--primary-color); }
</style>`;

const PANEL_TAG = "fve-optimizer-panel";
const PrevPanel = customElements.get(PANEL_TAG);
if (!PrevPanel) {
  customElements.define(PANEL_TAG, FveOptimizerPanel);
} else {
  for (const key of Object.getOwnPropertyNames(FveOptimizerPanel.prototype)) {
    if (key === "constructor") continue;
    const desc = Object.getOwnPropertyDescriptor(FveOptimizerPanel.prototype, key);
    if (desc) Object.defineProperty(PrevPanel.prototype, key, desc);
  }
  for (const el of PANEL_INSTANCES) {
    el._cards = null;
    if (el._hass) el.hass = el._hass;
  }
}
