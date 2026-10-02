"""Button: run the AI review of today's decisions now."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FveOptimizerConfigEntry
from .const import CONF_AI_TASK_ENTITY
from .coordinator import FveOptimizerCoordinator
from .entity import FveOptimizerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FveOptimizerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.conf.get(CONF_AI_TASK_ENTITY):
        async_add_entities([ReviewNowButton(coordinator)])


class ReviewNowButton(FveOptimizerEntity, ButtonEntity):
    """Ask the AI for today's review now."""

    def __init__(self, coordinator: FveOptimizerCoordinator) -> None:
        super().__init__(coordinator, "review_now")

    async def async_press(self) -> None:
        await self.coordinator.async_run_review()
