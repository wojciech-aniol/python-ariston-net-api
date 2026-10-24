"""Velis device class for Ariston module."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from .ariston_api import AristonAPI
from .const import VelisDeviceProperties
from .device import AristonDevice
from .velis_base_device import AristonVelisBaseDevice

_LOGGER = logging.getLogger(__name__)


class AristonVelisDevice(AristonDevice, AristonVelisBaseDevice, ABC):
    """Class representing a physical device, it's state and properties."""

    def __init__(
        self,
        api: AristonAPI,
        attributes: dict[str, Any],
    ) -> None:
        super().__init__(api, attributes)
        self.plant_settings: dict[str, Any] = {}

    @property
    @abstractmethod
    def anti_legionella_on_off(self) -> str:
        """Final string to get anti-legionella-on-off"""

    @property
    @abstractmethod
    def max_setpoint_temp(self) -> str:
        """Final string to get max setpoint temperature"""

    @property
    def water_anti_leg_value(self) -> bool | None:
        """Get water heater anti-legionella value"""
        return self.plant_settings.get(self.anti_legionella_on_off, None)

    @property
    def proc_req_temp_value(self) -> float | None:
        """Get process requested tempereature value"""
        return self.data.get(VelisDeviceProperties.PROC_REQ_TEMP, None)

    def set_antilegionella(self, anti_leg: bool):
        """Set water heater anti-legionella"""
        self.api.set_velis_plant_setting(
            self.plant_data,
            self.gw,
            self.anti_legionella_on_off,
            1.0 if anti_leg else 0.0,
            1.0 if self.plant_settings[self.anti_legionella_on_off] else 0.0,
        )
        self.plant_settings[self.anti_legionella_on_off] = anti_leg

    async def async_set_antilegionella(self, anti_leg: bool):
        """Async set water heater anti-legionella"""
        await self.api.async_set_velis_plant_setting(
            self.plant_data,
            self.gw,
            self.anti_legionella_on_off,
            1.0 if anti_leg else 0.0,
            1.0 if self.plant_settings[self.anti_legionella_on_off] else 0.0,
        )
        self.plant_settings[self.anti_legionella_on_off] = anti_leg

    def set_max_setpoint_temp(self, max_setpoint_temp: float):
        """Set water heater maximum setpoint temperature"""
        self.api.set_velis_plant_setting(
            self.plant_data,
            self.gw,
            self.max_setpoint_temp,
            max_setpoint_temp,
            self.plant_settings[self.max_setpoint_temp],
        )
        self.plant_settings[self.max_setpoint_temp] = max_setpoint_temp

    async def async_set_max_setpoint_temp(self, max_setpoint_temp: float):
        """Async set water heater maximum setpoint temperature"""
        await self.api.async_set_velis_plant_setting(
            self.plant_data,
            self.gw,
            self.max_setpoint_temp,
            max_setpoint_temp,
            self.plant_settings[self.max_setpoint_temp],
        )
        self.plant_settings[self.max_setpoint_temp] = max_setpoint_temp

    @property
    @abstractmethod
    def water_heater_maximum_setpoint_temperature_minimum(self) -> float | None:
        """Get water heater maximum setpoint temperature minimum"""
        raise NotImplementedError

    @property
    @abstractmethod
    def water_heater_maximum_setpoint_temperature_maximum(self) -> float | None:
        """Get water heater maximum setpoint maximum temperature"""
        raise NotImplementedError

    @property
    def water_heater_maximum_setpoint_temperature(self) -> float | None:
        """Get water heater maximum setpoint temperature value"""
        return self.plant_settings.get(self.max_setpoint_temp, None)

    @property
    def water_heater_minimum_temperature(self) -> float:
        """Get water heater minimum temperature"""
        return 40.0

    @property
    def water_heater_maximum_temperature(self) -> float | None:
        """Get water heater maximum temperature"""
        return self.water_heater_maximum_setpoint_temperature

    @property
    def water_heater_temperature_step(self) -> int:
        """Get water heater temperature step"""
        return 1

    @property
    def water_heater_temperature_decimals(self) -> int:
        """Get water heater temperature decimals"""
        return 0

    @property
    def water_heater_temperature_unit(self) -> str:
        """Get water heater temperature unit"""
        return "°C"
