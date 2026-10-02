"""Switches: master enable and per-device control."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

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
    async_add_entities(
        [
            MasterSwitch(coordinator),
            *(HubTunableSwitch(coordinator, t) for t in hub_tunables(coordinator.conf, "switch")),
        ]
    )
    for subentry_id, subentry in entry.subentries.items():
        if subentry_id not in coordinator.devices:
            continue
        async_add_entities(
            [
                DeviceControlSwitch(coordinator, subentry_id),
                *(
                    DeviceTunableSwitch(coordinator, subentry_id, t)
                    for t in device_tunables(subentry, "switch")
                ),
            ],
            config_subentry_id=subentry_id,
        )


class MasterSwitch(FveOptimizerEntity, SwitchEntity, RestoreEntity):
    """Turns the whole optimizer on or off."""

    def __init__(self, coordinator: FveOptimizerCoordinator) -> None:
        super().__init__(coordinator, "enabled")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self.coordinator.enabled = not (last and last.state == STATE_OFF)

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_enabled(False)
        self.async_write_ha_state()


class DeviceControlSwitch(FveDeviceEntity, SwitchEntity, RestoreEntity):
    """Lets the optimizer control this device (off = hands off)."""

    def __init__(self, coordinator: FveOptimizerCoordinator, subentry_id: str) -> None:
        super().__init__(coordinator, subentry_id, "control")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self.device.enabled = not (last and last.state == STATE_OFF)

    @property
    def is_on(self) -> bool:
        return self.device.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_device_enabled(self.subentry_id, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_device_enabled(self.subentry_id, False)
        self.async_write_ha_state()


class DeviceTunableSwitch(FveDeviceEntity, SwitchEntity):
    """On/off setting stored in the device subentry (e.g. deadline heating)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: FveOptimizerCoordinator, subentry_id: str, tunable: Tunable) -> None:
        super().__init__(coordinator, subentry_id, tunable.key)
        self.tunable = tunable

    @property
    def is_on(self) -> bool:
        return bool(self.tunable_value(self.tunable.key))

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.write_tunable(self.tunable.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.write_tunable(self.tunable.key, False)


class HubTunableSwitch(FveOptimizerEntity, SwitchEntity):
    """On/off setting stored in the entry options (e.g. export limit control)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: FveOptimizerCoordinator, tunable: Tunable) -> None:
        super().__init__(coordinator, tunable.key)
        self.tunable = tunable

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.conf.get(self.tunable.key))

    def _write(self, value: bool) -> None:
        entry = self.coordinator.config_entry
        options = {**entry.data, **entry.options, self.tunable.key: value}
        self.hass.config_entries.async_update_entry(entry, options=options)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._write(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._write(False)
