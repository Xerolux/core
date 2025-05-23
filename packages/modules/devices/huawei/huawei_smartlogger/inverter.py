#!/usr/bin/env python3
import logging
from typing import TypedDict, Any

from modules.common import modbus
from modules.common.abstract_device import AbstractInverter
from modules.common.component_state import InverterState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType
from modules.common.simcount import SimCounter
from modules.common.store import get_inverter_value_store
from modules.devices.huawei.huawei_smartlogger.config import Huawei_SmartloggerInverterSetup

log = logging.getLogger(__name__)


class KwargsDict(TypedDict):
    device_id: int
    tcp_client: modbus.ModbusTcpClient_


class Huawei_SmartloggerInverter(AbstractInverter):
    def __init__(self, component_config: Huawei_SmartloggerInverterSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__device_id: int = self.kwargs['device_id']
        self.client: modbus.ModbusTcpClient_ = self.kwargs['tcp_client']
        self.sim_counter = SimCounter(self.__device_id, self.component_config.id, prefix="pv")
        self.store = get_inverter_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self) -> None:
        modbus_id = self.component_config.configuration.modbus_id
        try:
            # Wordorder for multi-register reads defaults to Big Endian via common.modbus.py.
            # This is generally appropriate for Huawei devices.
            power = self.client.read_holding_registers(32080, ModbusDataType.INT_32, unit=modbus_id) * -1
            
            # Note: Exported energy (reg 32106) is read as INT_32. Typically, energy accumulation registers are UINT_32 or UINT_64.
            # If this register can indeed be negative or represents a net value, INT_32 is appropriate.
            # Otherwise, if it's always positive and accumulating, UINT_32 might be more standard.
            # Assuming current INT_32 typing is based on specific device behavior.
            exported = self.client.read_holding_registers(32106, ModbusDataType.INT_32, unit=modbus_id) * 10
            
            inverter_state = InverterState(
                power=power,
                exported=exported
            )
            self.store.set(inverter_state)
            self.fault_state.set_fault(False)
        except Exception as e:
            log.error(
                f"Error updating Huawei Smartlogger Inverter id: {self.component_config.id}: {e}",
                exc_info=True
            )
            self.fault_state.set_fault(True)


component_descriptor = ComponentDescriptor(configuration_factory=Huawei_SmartloggerInverterSetup)
