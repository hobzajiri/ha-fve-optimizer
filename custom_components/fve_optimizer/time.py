"""Time entities for tunables such as the boiler deadline."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import FveOptimizerConfigEntry
from .const import Tunable
from .coordinator import FveOptimizerCoordinator
from .entity import FveDeviceEntity, FveOptimizerEntity, device_tunables, hub_tunables


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FveOptimizerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(HubTime(coordinator, t) for t in hub_tunables(coordinator.conf, "time"))
    for subentry_id, subentry in entry.subentries.items():
        if subentry_id not in coordinator.devices:
            continue
        async_add_entities(
            [DeviceTime(coordinator, subentry_id, t) for t in device_tunables(subentry, "time")],
            config_subentry_id=subentry_id,
        )


class DeviceTime(FveDeviceEntity, TimeEntity):
    """Time of day stored in the device subentry as HH:MM:SS."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: FveOptimizerCoordinator, subentry_id: str, tunable: Tunable) -> None:
        super().__init__(coordinator, subentry_id, tunable.key)
        self.tunable = tunable

    @property
    def native_value(self) -> time | None:
        return dt_util.parse_time(str(self.tunable_value(self.tunable.key)))

    async def async_set_value(self, value: time) -> None:
        self.write_tunable(self.tunable.key, value.strftime("%H:%M:%S"))


class HubTime(FveOptimizerEntity, TimeEntity):
    """Optimizer-wide time of day (e.g. the AI review time)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: FveOptimizerCoordinator, tunable: Tunable) -> None:
        super().__init__(coordinator, tunable.key)
        self.tunable = tunable

    @property
    def native_value(self) -> time | None:
        return dt_util.parse_time(str(self.coordinator.conf.get(self.tunable.key) or ""))

    async def async_set_value(self, value: time) -> None:
        entry = self.coordinator.config_entry
        options = {**entry.data, **entry.options, self.tunable.key: value.strftime("%H:%M:%S")}
        self.hass.config_entries.async_update_entry(entry, options=options)
