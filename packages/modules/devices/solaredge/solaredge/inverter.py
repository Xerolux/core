#!/usr/bin/env python3
from typing import TypedDict, Any

from modules.common import modbus
from modules.common.abstract_device import AbstractInverter
from pymodbus.constants import Endian

from modules.common.component_state import InverterState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType
from modules.common.store import get_inverter_value_store
from modules.devices.solaredge.solaredge.config import SolaredgeInverterSetup
from modules.devices.solaredge.solaredge.scale import create_scaled_reader
import logging

from modules.common.simcount import SimCounter

log = logging.getLogger(__name__)

# Inverter Register Definitions
REG_AC_POWER_VALUE = 40083  # AC Power value (Watt)
REG_AC_POWER_SF = 40084  # AC Power scale factor (SF)
REG_AC_LIFETIME_ENERGY = 40093  # AC Lifetime Energy production (Watt hours)
REG_AC_LIFETIME_ENERGY_SF = 40095  # AC Lifetime Energy production scale factor (SF)
REG_AC_CURRENT_A = 40072  # AC Phase A Current value (Amps)
REG_AC_CURRENT_B = 40073  # AC Phase B Current value (Amps)
REG_AC_CURRENT_C = 40074  # AC Phase C Current value (Amps)
REG_AC_CURRENT_SF = 40075  # AC Current scale factor (SF)
REG_DC_POWER_VALUE = 40100  # DC Power value (Watt)
REG_DC_POWER_SF = 40101  # DC Power scale factor (SF)


class KwargsDict(TypedDict):
    client: modbus.ModbusTcpClient_
    device_id: int


class SolaredgeInverter(AbstractInverter):
    def __init__(self,
                 component_config: SolaredgeInverterSetup,
                 **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__tcp_client = self.kwargs['client']
        self.store = get_inverter_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))
        self._read_scaled_int16 = create_scaled_reader(
            self.__tcp_client, self.component_config.configuration.modbus_id, ModbusDataType.INT_16
        )
        self._read_scaled_uint16 = create_scaled_reader(
            self.__tcp_client, self.component_config.configuration.modbus_id, ModbusDataType.UINT_16
        )
        self._read_scaled_uint32 = create_scaled_reader(
            self.__tcp_client, self.component_config.configuration.modbus_id, ModbusDataType.UINT_32, wordorder=Endian.Little
        )
        self.sim_counter = SimCounter(self.kwargs['device_id'], self.component_config.id, prefix="Wechselrichter")

    def update(self) -> None:
        log.debug("Updating SolaredgeInverter id: %s", self.component_config.id)
        try:
            state = self.read_state()
            self.store.set(state)
            self.fault_state.set_fault(False)
        except Exception as e:
            log.error("Error updating SolaredgeInverter id %s: %s", self.component_config.id, e, exc_info=True)
            self.fault_state.set_fault(True)

    def read_state(self):
        # AC Power value (Watt) - Register 40083, SF Register 40084
        power = self._read_scaled_int16(REG_AC_POWER_VALUE, 1)[0] * -1
        log.debug("Inverter %s: Power: %s W", self.component_config.id, power)

        # AC Lifetime Energy production (Watt hours) - Register 40093, SF Register 40095
        exported = self._read_scaled_uint32(REG_AC_LIFETIME_ENERGY, 1)[0]
        log.debug("Inverter %s: Exported: %s Wh", self.component_config.id, exported)

        # AC Phase A/B/C Current value (Amps) - Registers 40072-40074, SF Register 40075
        currents = self._read_scaled_uint16(REG_AC_CURRENT_A, 3)
        log.debug("Inverter %s: Currents: %s A", self.component_config.id, currents)

        # DC Power value (Watt) - Register 40100, SF Register 40101
        # Wenn bei Hybrid-Systemen der Speicher aus dem Netz geladen wird, ist die DC-Leistung negativ.
        dc_power = self._read_scaled_int16(REG_DC_POWER_VALUE, 1)[0] * -1
        log.debug("Inverter %s: DC Power: %s W", self.component_config.id, dc_power)

        imported, _ = self.sim_counter.sim_count(power)
        log.debug("Inverter %s: Imported: %s Wh (simulated)", self.component_config.id, imported)

        return InverterState(
            power=power,
            exported=exported,
            currents=currents,
            dc_power=dc_power,
            imported=imported,
        )


component_descriptor = ComponentDescriptor(configuration_factory=SolaredgeInverterSetup)
