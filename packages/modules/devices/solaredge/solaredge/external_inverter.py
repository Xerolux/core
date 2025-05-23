#!/usr/bin/env python3
import logging
from typing import Dict, TypedDict, Any

from modules.common import modbus
from modules.common.abstract_device import AbstractInverter
from modules.common.component_state import InverterState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType
from modules.common.store import get_inverter_value_store
from modules.devices.solaredge.solaredge.config import SolaredgeExternalInverterSetup
from modules.devices.solaredge.solaredge.scale import create_scaled_reader
from modules.devices.solaredge.solaredge.meter import SolaredgeMeterRegisters, set_component_registers

log = logging.getLogger(__name__)


class KwargsDict(TypedDict):
    client: modbus.ModbusTcpClient_
    components: Dict


class SolaredgeExternalInverter(AbstractInverter):
    def __init__(self,
                 component_config: SolaredgeExternalInverterSetup,
                 **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__tcp_client = self.kwargs['client']
        self.registers = SolaredgeMeterRegisters(self.component_config.configuration.meter_id)
        self.store = get_inverter_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

        components = list(self.kwargs['components'].values())
        components.append(self)
        set_component_registers(self.component_config, self.__tcp_client, components)

        self._read_scaled_int16 = create_scaled_reader(
            self.__tcp_client, self.component_config.configuration.modbus_id, ModbusDataType.INT_16
        )
        self._read_scaled_uint32 = create_scaled_reader(
            self.__tcp_client, self.component_config.configuration.modbus_id, ModbusDataType.UINT_32 # wordorder will default to Big, which is fine for this if not specified.
        )

    def update(self) -> None:
        log.debug("Updating SolaredgeExternalInverter id: %s", self.component_config.id)
        try:
            state = self.read_state()
            self.store.set(state)
            self.fault_state.set_fault(False)
        except Exception as e:
            log.error("Error updating SolaredgeExternalInverter id %s: %s", self.component_config.id, e, exc_info=True)
            self.fault_state.set_fault(True)

    def read_state(self) -> InverterState:
        log.debug("Reading state for SolaredgeExternalInverter id: %s", self.component_config.id)
        factor = self.component_config.configuration.factor
        
        # self.registers.powers by default is 40206. For a meter, this is Total Real Power.
        # Reading 4 registers gives: Total Power, PhA Power, PhB Power, PhC Power
        # External inverter might only care about total power.
        power_total = self._read_scaled_int16(self.registers.powers, 4)[0] * factor
        log.debug("ExternalInverter %s: Total Power: %s W (after factor %s)", self.component_config.id, power_total, factor)

        # self.registers.imp_exp by default is 40226. For a meter, index 0 is Total Exported Real Energy.
        exported = self._read_scaled_uint32(self.registers.imp_exp, 8)[0]
        log.debug("ExternalInverter %s: Exported: %s Wh", self.component_config.id, exported)

        # self.registers.currents by default is 40191. For a meter, this reads 3 phase currents.
        currents = self._read_scaled_int16(self.registers.currents, 3)
        log.debug("ExternalInverter %s: Currents: %s A", self.component_config.id, currents)

        # Note: InverterState for external_inverter does not have dc_power or imported fields.
        # It also doesn't have a 'powers' (plural) field for individual phase powers.
        # If individual phase powers are needed, InverterState and this mapping would need adjustment.
        return InverterState(
            exported=exported,
            power=power_total, # Using total power
            currents=currents
        )


component_descriptor = ComponentDescriptor(configuration_factory=SolaredgeExternalInverterSetup)
