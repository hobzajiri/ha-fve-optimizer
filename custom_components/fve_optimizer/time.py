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
from .entity import FveDeviceEntity, device_tunables


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FveOptimizerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
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
