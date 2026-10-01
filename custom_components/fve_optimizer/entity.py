"""Shared entity base classes."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_DEFAULTS, DEVICE_TUNABLES, DOMAIN, Tunable
from .coordinator import FveOptimizerCoordinator


def device_tunables(subentry: ConfigSubentry, kind: str) -> list[Tunable]:
    """Tunables of one kind offered for this device."""
    return [
        t
        for t in DEVICE_TUNABLES.get(subentry.subentry_type, ())
        if t.kind == kind and (t.requires is None or subentry.data.get(t.requires))
    ]


class FveOptimizerEntity(CoordinatorEntity[FveOptimizerCoordinator]):
    """Entity on the optimizer hub device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FveOptimizerCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="FVE Optimizer",
            entry_type=DeviceEntryType.SERVICE,
        )


class FveDeviceEntity(CoordinatorEntity[FveOptimizerCoordinator]):
    """Entity belonging to one managed device (config subentry)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FveOptimizerCoordinator, subentry_id: str, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.subentry_id = subentry_id
        self.device = coordinator.devices[subentry_id]
        self._attr_translation_key = f"device_{key}"
        self._attr_unique_id = f"{entry.entry_id}_{subentry_id}_{key}"
        info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{subentry_id}")},
            name=self.device.name,
            manufacturer="FVE Optimizer",
            model=self.device.kind,
            entry_type=DeviceEntryType.SERVICE,
        )
        # HA 2026.8+ links by registry id; older versions by identifier.
        if "via_device_id" in DeviceInfo.__annotations__ and coordinator.hub_device_id:
            info["via_device_id"] = coordinator.hub_device_id
        else:
            info["via_device"] = (DOMAIN, entry.entry_id)
        self._attr_device_info = info

    def tunable_value(self, key: str) -> Any:
        return self.device.config.get(key, DEVICE_DEFAULTS.get(key))

    def write_tunable(self, key: str, value: Any) -> None:
        """Store a tunable in the subentry; the update listener applies it."""
        entry = self.coordinator.config_entry
        subentry = entry.subentries[self.subentry_id]
        self.hass.config_entries.async_update_subentry(
            entry, subentry, data={**subentry.data, key: value}
        )

    @property
    def device_data(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        return self.coordinator.data.devices.get(self.subentry_id, {})
