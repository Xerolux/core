#!/usr/bin/env python3
from typing import Any, TypedDict

from modules.common.abstract_device import AbstractInverter
from modules.common.component_state import InverterState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType, Endian, ModbusTcpClient_
from modules.common.simcount import SimCounter
from modules.common.store import get_inverter_value_store
from modules.devices.sungrow.sungrow.config import SungrowInverterSetup, Sungrow
from modules.devices.sungrow.sungrow.version import Version


class KwargsDict(TypedDict):
    client: ModbusTcpClient_
    device_config: Sungrow


class SungrowInverter(AbstractInverter):
    def __init__(self, component_config: SungrowInverterSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.device_config: Sungrow = self.kwargs['device_config']
        self.__tcp_client: ModbusTcpClient_ = self.kwargs['client']
        self.sim_counter = SimCounter(self.device_config.id, self.component_config.id, prefix="pv")
        self.store = get_inverter_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self) -> float:
        unit = self.device_config.configuration.modbus_id
        power = 0.0 # Default in case of error before assignment
        try:
            if self.device_config.configuration.version in (Version.SH, Version.SH_winet_dongle):
                power = self.__tcp_client.read_input_registers(13033, ModbusDataType.INT_32,
                                                               wordorder=Endian.Little, unit=unit) * -1
                # Note: dc_power (reg 5016) is read as UINT_32 and then negated.
                # This might be specific to how Sungrow reports this value (e.g., always positive,
                # and negation implies direction relative to system context) or could indicate
                # that it might be better represented as INT_32 if it can have intrinsic sign.
                # Assuming current typing and scaling are based on device behavior.
                dc_power = self.__tcp_client.read_input_registers(5016, ModbusDataType.UINT_32,
                                                                  wordorder=Endian.Little, unit=unit) * -1
            else:
                power = self.__tcp_client.read_input_registers(5030, ModbusDataType.INT_32,
                                                               wordorder=Endian.Little, unit=unit) * -1
                # Same note for dc_power as above.
                dc_power = self.__tcp_client.read_input_registers(5016, ModbusDataType.UINT_32,
                                                                  wordorder=Endian.Little, unit=unit) * -1

            _, exported = self.sim_counter.sim_count(power)

            inverter_state = InverterState(
                power=power,
                dc_power=dc_power,
                exported=exported
            )
            self.store.set(inverter_state)
            self.fault_state.set_fault(False)
            return power
        except Exception as e:
            log.error(
                f"Error updating Sungrow Inverter id: {self.component_config.id}: {e}",
                exc_info=True
            )
            self.fault_state.set_fault(True)
            return power # Return default or last known power if required, though state is not stored.


component_descriptor = ComponentDescriptor(configuration_factory=SungrowInverterSetup)
