#!/usr/bin/env python3
import logging
from typing import Dict, TypedDict, Any

from modules.common import modbus
from modules.common.abstract_device import AbstractCounter
from modules.common.component_state import CounterState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType
from modules.common.store import get_counter_value_store
from modules.devices.solaredge.solaredge.config import SolaredgeCounterSetup
from modules.devices.solaredge.solaredge.scale import create_scaled_reader, scale_registers
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
            self.__tcp_client, self.component_config.configuration.modbus_id, ModbusDataType.UINT_32
        )

    def update(self):
        # Batch-Read für zusammenhängende Register (currents, voltages, frequency)
        # Diese liegen bei Standard-Konfiguration direkt hintereinander: 40191-40205
        if (self.registers.frequency == self.registers.currents + 13 and 
            self.registers.voltages == self.registers.currents + 5):
            # Register sind zusammenhängend - optimierter Batch-Read möglich
            try:
                # Lese alle Register von currents bis frequency_scale in einem Read
                # 40191: current phase A
                # 40192: current phase B  
                # 40193: current phase C
                # 40194: current scale factor
                # 40195: reserved
                # 40196-40202: voltages (7 Register)
                # 40203: voltage scale factor
                # 40204: frequency
                # 40205: frequency scale factor
                batch_data = self.__tcp_client.read_holding_registers(
                    self.registers.currents,
                    15,  # 15 Register total
                    unit=self.component_config.configuration.modbus_id
                )
                
                # Extrahiere die einzelnen Werte mit scale_registers
                # Dies garantiert identisches Verhalten zur Original-Implementierung
                currents = scale_registers(batch_data[0:3] + [batch_data[3]])
                voltages_all = scale_registers(batch_data[5:12] + [batch_data[12]])
                voltages = voltages_all[:3]  # Nur erste 3 Phasen wie im Original
                frequency = scale_registers([batch_data[13]] + [batch_data[14]])[0]
                
                log.debug("Batch read successful for currents, voltages, frequency")
                
            except Exception as e:
                log.debug(f"Batch read failed, using individual reads: {e}")
                # Fallback auf Original-Methode
                currents = self._read_scaled_int16(self.registers.currents, 3)
                voltages = self._read_scaled_int16(self.registers.voltages, 7)[:3]
                frequency = self._read_scaled_int16(self.registers.frequency, 1)[0]
        else:
            # Register nicht zusammenhängend oder nicht-standard Layout
            currents = self._read_scaled_int16(self.registers.currents, 3)
            voltages = self._read_scaled_int16(self.registers.voltages, 7)[:3]
            frequency = self._read_scaled_int16(self.registers.frequency, 1)[0]
        
        # Rest wie im Original - keine Änderungen
        powers = [-power for power in self._read_scaled_int16(self.registers.powers, 4)]
        power_factors = [power_factor /
                         100 for power_factor in self._read_scaled_int16(self.registers.power_factors, 3)]
        counter_values = self._read_scaled_uint32(self.registers.imp_exp, 8)
        counter_exported, counter_imported = [counter_values[i] for i in [0, 4]]
        
        counter_state = CounterState(
            imported=counter_imported,
            exported=counter_exported,
            power=powers[0],
            powers=powers[1:],
            voltages=voltages,
            currents=currents,
            power_factors=power_factors,
            frequency=frequency
        )
        self.store.set(counter_state)


component_descriptor = ComponentDescriptor(configuration_factory=SolaredgeCounterSetup)
