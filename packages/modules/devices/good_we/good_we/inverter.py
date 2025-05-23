#!/usr/bin/env python3
from typing import TypedDict, Any

from modules.common import modbus
from modules.common.abstract_device import AbstractInverter
from modules.common.component_state import InverterState
import logging

from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType, Endian # Added Endian for comment clarity
from modules.common.store import get_inverter_value_store
from modules.devices.good_we.good_we.config import GoodWeInverterSetup
from modules.devices.good_we.good_we.version import GoodWeVersion

log = logging.getLogger(__name__)


class KwargsDict(TypedDict):
    modbus_id: int
    version: GoodWeVersion
    firmware: int
    client: modbus.ModbusTcpClient_


class GoodWeInverter(AbstractInverter):
    def __init__(self, component_config: GoodWeInverterSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__modbus_id: int = self.kwargs['modbus_id']
        self.version: GoodWeVersion = self.kwargs['version']
        self.firmware: int = self.kwargs['firmware']
        self.__tcp_client: modbus.ModbusTcpClient_ = self.kwargs['client']
        self.store = get_inverter_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self) -> None:
        try:
            with self.__tcp_client:
                # Wordorder for multi-register reads defaults to Big Endian via common.modbus.py.
                # Manufacturer documentation should be checked to confirm this is correct for GoodWe.
                power = sum([self.__tcp_client.read_holding_registers(
                    reg, ModbusDataType.INT_32, unit=self.__modbus_id)
                    for reg in [35105, 35109, 35113, 35117]]) * -1
                
                # Wordorder for multi-register reads defaults to Big Endian via common.modbus.py.
                # Manufacturer documentation should be checked to confirm this is correct for GoodWe.
                exported = self.__tcp_client.read_holding_registers(
                    35191, ModbusDataType.UINT_32, unit=self.__modbus_id) * 100

            inverter_state = InverterState(
                power=power,
                exported=exported
            )
            self.store.set(inverter_state)
            self.fault_state.set_fault(False)
        except Exception as e:
            log.error(
                f"Error updating GoodWe Inverter id: {self.component_config.id}: {e}",
                exc_info=True
            )
            self.fault_state.set_fault(True)


component_descriptor = ComponentDescriptor(configuration_factory=GoodWeInverterSetup)
