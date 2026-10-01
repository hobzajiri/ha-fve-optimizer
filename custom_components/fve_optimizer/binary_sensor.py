"""Binary sensors describing the dispatcher's decisions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FveOptimizerConfigEntry
from .coordinator import DispatchSnapshot, FveOptimizerCoordinator
from .entity import FveDeviceEntity, FveOptimizerEntity


@dataclass(frozen=True, kw_only=True)
class HubBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[DispatchSnapshot], bool]


HUB_BINARY: tuple[HubBinaryDescription, ...] = (
    HubBinaryDescription(
        key="battery_priority",
        translation_key="battery_priority",
        value_fn=lambda s: s.battery_priority,
    ),
    HubBinaryDescription(
        key="forecast_covers_battery",
        translation_key="forecast_covers_battery",
        value_fn=lambda s: s.forecast_covers_battery,
    ),
    HubBinaryDescription(
        key="export_limit_raised",
        translation_key="export_limit_raised",
        value_fn=lambda s: s.export_limit_raised,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FveOptimizerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(HubBinary(coordinator, d) for d in HUB_BINARY)
    if coordinator.hdo.enabled:
        async_add_entities([HdoBinary(coordinator)])
    for subentry_id in coordinator.devices:
        async_add_entities(
            [DeviceActiveBinary(coordinator, subentry_id)],
            config_subentry_id=subentry_id,
        )


class HubBinary(FveOptimizerEntity, BinarySensorEntity):
    entity_description: HubBinaryDescription

    def __init__(self, coordinator: FveOptimizerCoordinator, description: HubBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class DeviceActiveBinary(FveDeviceEntity, BinarySensorEntity):
    def __init__(self, coordinator: FveOptimizerCoordinator, subentry_id: str) -> None:
        super().__init__(coordinator, subentry_id, "active")

    @property
    def is_on(self) -> bool | None:
        return self.device_data.get("active")


class HdoBinary(FveOptimizerEntity, BinarySensorEntity):
    """Low tariff now, with today's / tomorrow's windows in the attributes."""

    def __init__(self, coordinator: FveOptimizerCoordinator) -> None:
        super().__init__(coordinator, "hdo")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.hdo.is_active(dt_util.now())

    @property
    def extra_state_attributes(self) -> dict:
        return self.coordinator.hdo.attributes(dt_util.now())
