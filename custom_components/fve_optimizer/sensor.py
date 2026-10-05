"""Diagnostic sensors: surplus budget, allocation and per-device state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FveOptimizerConfigEntry
from .const import CONF_AI_TASK_ENTITY
from .coordinator import DispatchSnapshot, FveOptimizerCoordinator
from .entity import FveDeviceEntity, FveOptimizerEntity

REASONS = [
    "init",
    "disabled",
    "missing_input",
    "battery_priority",
    "dispatching",
    "failsafe",
]

DEVICE_REASONS = [
    "init",
    "disabled",
    "unavailable",
    "not_connected",
    "temperature_reached",
    "soc_reached",
    "waiting_for_surplus",
    "starting",
    "running",
    "charging",
    "no_surplus",
    "min_on_time",
    "min_off_time",
    "deadline_heating",
    "breaker_limit",
    "waiting_for_hdo",
    "deadline_charging",
    "boost_charging",
    "hold_until_deadline",
]


@dataclass(frozen=True, kw_only=True)
class HubSensorDescription(SensorEntityDescription):
    value_fn: Callable[[DispatchSnapshot], Any]


def _power(key: str, fn: Callable[[DispatchSnapshot], Any]) -> HubSensorDescription:
    return HubSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=fn,
    )


HUB_SENSORS: tuple[HubSensorDescription, ...] = (
    _power("budget", lambda s: s.budget_w),
    _power("allocated", lambda s: s.allocated_w),
    _power("managed", lambda s: s.managed_w),
    HubSensorDescription(
        key="effective_target_soc",
        translation_key="effective_target_soc",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda s: s.effective_target_soc,
    ),
    HubSensorDescription(
        key="breaker_headroom",
        translation_key="breaker_headroom",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value_fn=lambda s: s.headroom_a,
    ),
    HubSensorDescription(
        key="ai_review",
        translation_key="ai_review",
        value_fn=lambda s: None,  # filled by the sensor class from the coordinator
    ),
    HubSensorDescription(
        key="recommendations",
        translation_key="recommendations",
        value_fn=lambda s: len(s.recommendations),
    ),
    HubSensorDescription(
        key="last_decision",
        translation_key="last_decision",
        value_fn=lambda s: s.decision,
    ),
    HubSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=REASONS,
        value_fn=lambda s: s.reason,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FveOptimizerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        HubSensor(coordinator, d)
        for d in HUB_SENSORS
        if d.key != "ai_review" or coordinator.conf.get(CONF_AI_TASK_ENTITY)
    )
    for subentry_id in coordinator.devices:
        async_add_entities(
            [
                DeviceAllocatedSensor(coordinator, subentry_id),
                DeviceReasonSensor(coordinator, subentry_id),
                *(DeviceStatSensor(coordinator, subentry_id, key) for key in STAT_SENSORS),
            ],
            config_subentry_id=subentry_id,
        )


class HubSensor(FveOptimizerEntity, SensorEntity):
    entity_description: HubSensorDescription
    # The structured data changes every cycle – keep it out of the database.
    _unrecorded_attributes = frozenset({"data"})

    def __init__(self, coordinator: FveOptimizerCoordinator, description: HubSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.entity_description.key == "ai_review":
            reviews = self.coordinator.reviews
            return reviews[0]["score"] if reviews else None
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """The status sensor carries the numbers behind the decision."""
        snap = self.coordinator.data
        if snap is None:
            return None
        if self.entity_description.key == "ai_review":
            latest = self.coordinator.reviews[0] if self.coordinator.reviews else {}
            return {
                **{k: latest.get(k) for k in ("date", "at", "summary", "good", "problems", "suggestions", "outlook", "entity_id")},
                "history": [{"date": r.get("date"), "score": r.get("score")} for r in self.coordinator.reviews],
                "error": self.coordinator.review_error,
            }
        if self.entity_description.key == "recommendations":
            return {"items": snap.recommendations}
        if self.entity_description.key == "last_decision":
            return {
                "details": snap.decision_lines,
                "changed_at": snap.decision_changed_at,
                "data": snap.decision_data,
            }
        if self.entity_description.key != "status":
            return None
        return {
            "data": snap.live_data,
            "grid_w": snap.grid_w,
            "battery_w": snap.battery_w,
            "battery_soc": snap.battery_soc,
            "pv_w": snap.pv_w,
            "house_w": snap.house_w,
            "forecast_remaining_kwh": snap.forecast_remaining_kwh,
            "forecast_need_kwh": snap.forecast_need_kwh,
            "hours_until_sunset": snap.hours_until_sunset,
            "hdo_active": snap.hdo_active,
            "night_hours": snap.night_hours,
            "night_kwh": snap.night_kwh,
            "night_target_soc": snap.night_target_soc,
        }


class DeviceAllocatedSensor(FveDeviceEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: FveOptimizerCoordinator, subentry_id: str) -> None:
        super().__init__(coordinator, subentry_id, "allocated")

    @property
    def native_value(self) -> float | None:
        return self.device_data.get("allocated_w")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {k: v for k, v in self.device_data.items() if k not in ("allocated_w", "reason")}


class DeviceReasonSensor(FveDeviceEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = DEVICE_REASONS

    def __init__(self, coordinator: FveOptimizerCoordinator, subentry_id: str) -> None:
        super().__init__(coordinator, subentry_id, "reason")

    @property
    def native_value(self) -> str | None:
        return self.device_data.get("reason")


STAT_SENSORS = ("total", "solar", "battery", "grid", "cost")


class DeviceStatSensor(FveDeviceEntity, SensorEntity):
    """Cumulative energy by source / cost of one device (HA builds daily statistics)."""

    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: FveOptimizerCoordinator, subentry_id: str, key: str) -> None:
        super().__init__(coordinator, subentry_id, f"{'energy_' if key != 'cost' else ''}{key}")
        self.stat_key = key
        if key == "cost":
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_native_unit_of_measurement = "CZK"
        else:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @property
    def native_value(self) -> float:
        return round(self.coordinator.device_stats(self.subentry_id).get(self.stat_key, 0.0), 4)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        today = self.coordinator.device_stats(self.subentry_id).get("today", {})
        return {"today": round(today.get(self.stat_key, 0.0), 3)}
