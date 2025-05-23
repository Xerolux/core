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
from modules.devices.victron.victron.config import VictronInverterSetup

log = logging.getLogger(__name__)


class KwargsDict(TypedDict):
    device_id: int
    client: modbus.ModbusTcpClient_


class VictronInverter(AbstractInverter):
    def __init__(self, component_config: VictronInverterSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__device_id: int = self.kwargs['device_id']
        self.__tcp_client: modbus.ModbusTcpClient_ = self.kwargs['client']
        self.sim_counter = SimCounter(self.__device_id, self.component_config.id, prefix="pv")
        self.store = get_inverter_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self) -> None:
        modbus_id = self.component_config.configuration.modbus_id
        power = 0  # Default power to 0 in case of specific handled errors
        try:
            with self.__tcp_client:
                if self.component_config.configuration.mppt:
                    try:
                        power = self.__tcp_client.read_holding_registers(
                            789, ModbusDataType.UINT_16, unit=modbus_id
                        ) / -10
                    except Exception as e_mppt:
                        if "GatewayPathUnavailable" in str(e_mppt):
                            power = 0
                            log.debug(
                                f"{self.component_config.name}: Register 789 (MPPT power) "
                                "could not be read (GatewayPathUnavailable). Power set to 0."
                            )
                            # This specific error is handled by setting power to 0, consider it a success for fault state.
                        else:
                            raise  # Re-raise other exceptions to be caught by the outer try-except
                else:
                    # Adresse 808-810 ac output connected pv
                    # Adresse 811-813 ac input connected pv
                    # Adresse 850 mppt Leistung
                    # Wordorder not applicable for UINT_16 list reads.
                    power_temp1 = self.__tcp_client.read_holding_registers(
                        808, [ModbusDataType.UINT_16]*6, unit=100  # Assuming modbus_id 100 is intended here
                    )
                    power_temp2 = self.__tcp_client.read_holding_registers(
                        850, ModbusDataType.UINT_16, unit=100 # Assuming modbus_id 100 is intended here
                    )
                    power = (sum(power_temp1) + power_temp2) * -1
            
            _, exported = self.sim_counter.sim_count(power)
            inverter_state = InverterState(
                power=power,
                exported=exported
            )
            self.store.set(inverter_state)
            self.fault_state.set_fault(False)
        except Exception as e:
            log.error(
                f"Error updating Victron Inverter id: {self.component_config.id}: {e}",
                exc_info=True
            )
            # If power was set to a default due to a handled "GatewayPathUnavailable",
            # but another error occurred later (e.g., sim_counter), this will correctly set fault.
            self.fault_state.set_fault(True)


component_descriptor = ComponentDescriptor(configuration_factory=VictronInverterSetup)
