#!/usr/bin/env python3
import logging
from typing import Dict, TypedDict, Any

from modules.common import modbus
from modules.common.abstract_device import AbstractCounter
from pymodbus.constants import Endian

from modules.common.component_state import CounterState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType
from modules.common.store import get_counter_value_store
from modules.devices.solaredge.solaredge.config import SolaredgeCounterSetup
from modules.devices.solaredge.solaredge.scale import create_scaled_reader
from modules.devices.solaredge.solaredge.meter import SolaredgeMeterRegisters, set_component_registers

log = logging.getLogger(__name__)


class KwargsDict(TypedDict):
    client: modbus.ModbusTcpClient_
    components: Dict


class SolaredgeCounter(AbstractCounter):
    def __init__(self, component_config: SolaredgeCounterSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__tcp_client: modbus.ModbusTcpClient_ = self.kwargs['client']
        self.registers = SolaredgeMeterRegisters()
        self.store = get_counter_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

        components = list(self.kwargs['components'].values())
        components.append(self)
        set_component_registers(self.component_config, self.__tcp_client, components)

        self._read_scaled_int16 = create_scaled_reader(
            self.__tcp_client, self.component_config.configuration.modbus_id, ModbusDataType.INT_16
        )
        self._read_scaled_uint32 = create_scaled_reader(
            self.__tcp_client, self.component_config.configuration.modbus_id, ModbusDataType.UINT_32, wordorder=Endian.Little
        )

    def update(self):
        log.debug("Updating SolaredgeCounter id: %s", self.component_config.id)
        try:
            powers = [-power for power in self._read_scaled_int16(self.registers.powers, 4)]
            log.debug("Counter %s: Powers: %s W", self.component_config.id, powers)
            currents = self._read_scaled_int16(self.registers.currents, 3)
            log.debug("Counter %s: Currents: %s A", self.component_config.id, currents)
            voltages = self._read_scaled_int16(self.registers.voltages, 7)[:3] # First 3 are L-N voltages
            log.debug("Counter %s: Voltages (L-N): %s V", self.component_config.id, voltages)
            frequency = self._read_scaled_int16(self.registers.frequency, 1)[0]
            log.debug("Counter %s: Frequency: %s Hz", self.component_config.id, frequency)
            power_factors = [power_factor / 100 for power_factor in self._read_scaled_int16(self.registers.power_factors, 3)]
            log.debug("Counter %s: Power Factors: %s", self.component_config.id, power_factors)
            
            # Registers.imp_exp (default 40226) should give 8 values:
            # Exported Wh Total, Exported Wh PhA, Exported Wh PhB, Exported Wh PhC
            # Imported Wh Total, Imported Wh PhA, Imported Wh PhB, Imported Wh PhC
            counter_values = self._read_scaled_uint32(self.registers.imp_exp, 8)
            counter_exported = counter_values[0]
            counter_imported = counter_values[4]
            log.debug("Counter %s: Exported: %s Wh, Imported: %s Wh", self.component_config.id, counter_exported, counter_imported)
            
            counter_state = CounterState(
                imported=counter_imported,
                exported=counter_exported,
                power=powers[0],      # Total real power
                powers=powers[1:],    # Per-phase real power
                voltages=voltages,
                currents=currents,
                power_factors=power_factors,
                frequency=frequency
            )
            self.store.set(counter_state)
            self.fault_state.set_fault(False)
        except Exception as e:
            log.error("Error updating SolaredgeCounter id %s: %s", self.component_config.id, e, exc_info=True)
            self.fault_state.set_fault(True)


component_descriptor = ComponentDescriptor(configuration_factory=SolaredgeCounterSetup)
