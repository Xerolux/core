#!/usr/bin/env python3
from typing import TypedDict, Any

from modules.common import modbus
import logging

from modules.common.abstract_device import AbstractBat
from modules.common.component_state import BatState
from modules.common.component_type import ComponentDescriptor
from modules.common.modbus import ModbusDataType, Endian # Added Endian for comment clarity
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.store import get_bat_value_store
from modules.devices.good_we.good_we.config import GoodWeBatSetup
from modules.devices.good_we.good_we.version import GoodWeVersion

log = logging.getLogger(__name__)


class KwargsDict(TypedDict):
    modbus_id: int
    version: GoodWeVersion
    firmware: int
    client: modbus.ModbusTcpClient_


class GoodWeBat(AbstractBat):
    def __init__(self, component_config: GoodWeBatSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__modbus_id: int = self.kwargs['modbus_id']
        self.version: GoodWeVersion = self.kwargs['version']
        self.firmware: int = self.kwargs['firmware']
        self.__tcp_client: modbus.ModbusTcpClient_ = self.kwargs['client']
        self.store = get_bat_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self) -> None:
        try:
            with self.__tcp_client:
                if self.version == GoodWeVersion.V_1_7:
                    power = self.__tcp_client.read_holding_registers(
                        35183, ModbusDataType.INT_16, unit=self.__modbus_id
                    ) * -1
                else:
                    # Wordorder for multi-register reads defaults to Big Endian via common.modbus.py.
                    # Manufacturer documentation should be checked to confirm this is correct for GoodWe.
                    power = self.__tcp_client.read_holding_registers(
                        35182, ModbusDataType.INT_32, unit=self.__modbus_id
                    ) * -1
                
                soc = self.__tcp_client.read_holding_registers(
                    37007, ModbusDataType.UINT_16, unit=self.__modbus_id
                )
                
                # Wordorder for multi-register reads defaults to Big Endian via common.modbus.py.
                # Manufacturer documentation should be checked to confirm this is correct for GoodWe.
                imported = self.__tcp_client.read_holding_registers(
                    35206, ModbusDataType.UINT_32, unit=self.__modbus_id
                ) * 100
                
                # Wordorder for multi-register reads defaults to Big Endian via common.modbus.py.
                # Manufacturer documentation should be checked to confirm this is correct for GoodWe.
                exported = self.__tcp_client.read_holding_registers(
                    35209, ModbusDataType.UINT_32, unit=self.__modbus_id
                ) * 100

            bat_state = BatState(
                power=power,
                soc=soc,
                imported=imported,
                exported=exported
            )
            self.store.set(bat_state)
            self.fault_state.set_fault(False)
        except Exception as e:
            log.error(
                f"Error updating GoodWe Battery id: {self.component_config.id}: {e}",
                exc_info=True
            )
            self.fault_state.set_fault(True)


component_descriptor = ComponentDescriptor(configuration_factory=GoodWeBatSetup)
