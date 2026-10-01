"""Number entities for every tunable parameter.

Values live in the config entry (options) and device subentries, so the
entities and the config flow always show the same numbers. Writing a value
goes through the update listener, which applies it without a reload.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FveOptimizerConfigEntry
from .const import (
    CONF_EXPORT_LIMIT_ENTITY,
    CONF_EXPORT_LIMIT_NORMAL,
    CONF_EXPORT_LIMIT_RAISED,
    DEFAULTS,
    HUB_TUNABLES,
    Tunable,
)
from .coordinator import FveOptimizerCoordinator
from .entity import FveDeviceEntity, FveOptimizerEntity, device_tunables


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FveOptimizerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(HubNumber(coordinator, t) for t in HUB_TUNABLES if t.kind == "number")
    for subentry_id, subentry in entry.subentries.items():
        if subentry_id not in coordinator.devices:
            continue
        async_add_entities(
            [DeviceNumber(coordinator, subentry_id, t) for t in device_tunables(subentry, "number")],
            config_subentry_id=subentry_id,
        )


def _setup_number(entity: NumberEntity, tunable: Tunable) -> None:
    entity._attr_entity_category = EntityCategory.CONFIG
    entity._attr_mode = NumberMode.BOX
    entity._attr_native_min_value = tunable.minimum
    entity._attr_native_max_value = tunable.maximum
    entity._attr_native_step = tunable.step
    entity._attr_native_unit_of_measurement = tunable.unit


class HubNumber(FveOptimizerEntity, NumberEntity):
    """Optimizer-wide parameter (stored in entry options)."""

    def __init__(self, coordinator: FveOptimizerCoordinator, tunable: Tunable) -> None:
        super().__init__(coordinator, tunable.key)
        self.tunable = tunable
        _setup_number(self, tunable)

    @property
    def native_unit_of_measurement(self) -> str | None:
        # Export limits use whatever unit the inverter entity has (W, kW or %).
        if self.tunable.key in (CONF_EXPORT_LIMIT_NORMAL, CONF_EXPORT_LIMIT_RAISED):
            entity_id = self.coordinator.conf.get(CONF_EXPORT_LIMIT_ENTITY)
            state = self.hass.states.get(entity_id) if entity_id else None
            return state.attributes.get("unit_of_measurement") if state else None
        return self.tunable.unit

    @property
    def native_value(self) -> float:
        return float(self.coordinator.conf.get(self.tunable.key, DEFAULTS.get(self.tunable.key, 0)))

    async def async_set_native_value(self, value: float) -> None:
        entry = self.coordinator.config_entry
        options = {**entry.data, **entry.options, self.tunable.key: value}
        self.hass.config_entries.async_update_entry(entry, options=options)


class DeviceNumber(FveDeviceEntity, NumberEntity):
    """Per-device parameter (stored in the device subentry)."""

    def __init__(self, coordinator: FveOptimizerCoordinator, subentry_id: str, tunable: Tunable) -> None:
        super().__init__(coordinator, subentry_id, tunable.key)
        self.tunable = tunable
        _setup_number(self, tunable)

    @property
    def native_value(self) -> float:
        return float(self.tunable_value(self.tunable.key) or 0)

    async def async_set_native_value(self, value: float) -> None:
        self.write_tunable(self.tunable.key, value)
