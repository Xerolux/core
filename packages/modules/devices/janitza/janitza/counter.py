#!/usr/bin/env python3
from typing import TypedDict, Any

from modules.common import modbus
from modules.common.abstract_device import AbstractCounter
from modules.common.component_state import CounterState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType
from modules.common.simcount import SimCounter
from modules.common.store import get_counter_value_store
from modules.devices.janitza.janitza.config import JanitzaCounterSetup


class KwargsDict(TypedDict):
    device_id: int
    tcp_client: modbus.ModbusTcpClient_
    modbus_id: int


class JanitzaCounter(AbstractCounter):
    def __init__(self, component_config: JanitzaCounterSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__device_id: int = self.kwargs['device_id']
        self.__tcp_client: modbus.ModbusTcpClient_ = self.kwargs['tcp_client']
        self.__modbus_id: int = self.kwargs['modbus_id']
        self.sim_counter = SimCounter(self.__device_id, self.component_config.id, prefix="bezug")
        self.store = get_counter_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self) -> None:
        with self.__tcp_client:
            power = self.__tcp_client.read_holding_registers(19026, ModbusDataType.FLOAT_32, unit=self.__modbus_id)
            powers = self.__tcp_client.read_holding_registers(
                19020, [ModbusDataType.FLOAT_32] * 3, unit=self.__modbus_id)
            currents = self.__tcp_client.read_holding_registers(
                19012, [ModbusDataType.FLOAT_32] * 3, unit=self.__modbus_id)
            voltages = self.__tcp_client.read_holding_registers(
                19000, [ModbusDataType.FLOAT_32] * 3, unit=self.__modbus_id)
            power_factors = self.__tcp_client.read_holding_registers(
                19044, [ModbusDataType.FLOAT_32] * 3, unit=self.__modbus_id)
            frequency = self.__tcp_client.read_holding_registers(19050, ModbusDataType.FLOAT_32, unit=self.__modbus_id)

        imported, exported = self.sim_counter.sim_count(power)

        counter_state = CounterState(
            imported=imported,
            exported=exported,
            power=power,
            powers=powers,
            currents=currents,
            voltages=voltages,
            frequency=frequency,
            power_factors=power_factors
        )
        self.store.set(counter_state)


component_descriptor = ComponentDescriptor(configuration_factory=JanitzaCounterSetup)
