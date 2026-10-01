"""Select entities for tunables with fixed choices (e.g. phase count)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

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
            [DeviceSelect(coordinator, subentry_id, t) for t in device_tunables(subentry, "select")],
            config_subentry_id=subentry_id,
        )


class DeviceSelect(FveDeviceEntity, SelectEntity):
    """Per-device choice stored in the device subentry."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: FveOptimizerCoordinator, subentry_id: str, tunable: Tunable) -> None:
        super().__init__(coordinator, subentry_id, tunable.key)
        self.tunable = tunable
        self._attr_options = list(tunable.options or ())

    @property
    def current_option(self) -> str | None:
        value = self.tunable_value(self.tunable.key)
        return None if value is None else str(value)

    async def async_select_option(self, option: str) -> None:
        self.write_tunable(self.tunable.key, option)
