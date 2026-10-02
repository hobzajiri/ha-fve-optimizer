/*
 * FVE Optimizer sidebar panel – registered by the integration itself.
 *
 * Finds the integration's entities in the entity registry (by platform and
 * translation key, so entity IDs / languages / areas do not matter) and lays
 * out standard Home Assistant cards around the FVE Optimizer card:
 * power flow + recommendations, decision timeline, power history, decision
 * log, control switches and the settings of every managed device.
 */

const L = {
  cs: {
    title: "FVE Optimizer", timeline: "Rozhodnutí (24 h)", power: "Výkon (6 h)", log: "Historie rozhodnutí",
    control: "Řízení", settings: "Nastavení", noEntry: "FVE Optimizer zatím není nastavený.",
    noHelpers: "Panel vyžaduje novější Home Assistant (chybí loadCardHelpers).",
  },
  en: {
    title: "FVE Optimizer", timeline: "Decisions (24 h)", power: "Power (6 h)", log: "Decision history",
    control: "Control", settings: "Settings", noEntry: "FVE Optimizer is not set up yet.",
    noHelpers: "The panel needs a newer Home Assistant (loadCardHelpers missing).",
  },
};

class FveOptimizerPanel extends HTMLElement {
  set hass(hass) {
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
    root.innerHTML = `${STYLE}<div class="toolbar"><ha-menu-button></ha-menu-button><h1>${t.title}</h1></div>
      <div class="grid"></div>`;
    const menu = root.querySelector("ha-menu-button");
    if (menu) { menu.hass = this._hass; menu.narrow = this._narrow; }
    const grid = root.querySelector(".grid");

    if (!window.loadCardHelpers) {
      grid.innerHTML = `<div class="msg">${t.noHelpers}</div>`;
      this._cards = [];
      return;
    }
    const helpers = await window.loadCardHelpers();
    await Promise.race([customElements.whenDefined("fve-optimizer-card"), new Promise((r) => setTimeout(r, 3000))]);

    const { hub, devices } = this._entities();
    if (!hub.status) {
      grid.innerHTML = `<div class="msg">${t.noEntry}</div>`;
      this._cards = [];
      this._building = false;
      return;
    }
    const id = (e) => e && e.entity_id;
    const ids = (...list) => list.map(id).filter(Boolean);
    const devList = Object.entries(devices).map(([deviceId, ents]) => ({
      deviceId, ents, name: this._hass.devices?.[deviceId]?.name || "",
    }));

    const hubDevice = hub.status?.device_id;
    const link = (deviceId, name) => `[${name}](/config/devices/device/${deviceId})`;
    const configs = [
      { type: "custom:fve-optimizer-card", entity: id(hub.status) },
      {
        type: "entities", title: t.control, show_header_toggle: false,
        entities: ids(hub.enabled, hub.dry_run, ...devList.map((d) => d.ents.control)),
      },
      {
        type: "history-graph", title: t.timeline, hours_to_show: 24,
        entities: ids(hub.status, hub.battery_priority, hub.export_limit_raised, hub.hdo,
          ...devList.map((d) => d.ents.reason)),
      },
      { type: "logbook", title: t.log, hours_to_show: 24, entities: ids(hub.last_decision, hub.recommendations) },
      {
        type: "markdown", title: t.settings,
        content: [hubDevice ? link(hubDevice, t.title) : "", ...devList.map((d) => link(d.deviceId, d.name))]
          .filter(Boolean).map((l) => `- ${l}`).join("\n"),
      },
    ].filter((c) => !c.entities || c.entities.length);

    this._cards = configs.map((config) => {
      const card = helpers.createCardElement(config);
      card.hass = this._hass;
      const cell = document.createElement("div");
      cell.className = config.type === "custom:fve-optimizer-card" ? "cell wide" : "cell";
      cell.appendChild(card);
      grid.appendChild(cell);
      return card;
    });
    this._building = false;
  }
}

const STYLE = `<style>
  :host { display: block; background: var(--primary-background-color); min-height: 100vh; }
  .toolbar { display: flex; align-items: center; gap: 8px; height: 56px; padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); }
  .toolbar h1 { font-size: 20px; font-weight: 400; margin: 0; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 12px; padding: 12px;
    align-items: start; }
  .cell.wide { grid-row: span 2; }
  .msg { padding: 24px; color: var(--secondary-text-color); }
</style>`;

customElements.define("fve-optimizer-panel", FveOptimizerPanel);
