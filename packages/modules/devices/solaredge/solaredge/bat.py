#!/usr/bin/env python3
import logging
from typing import Any, Tuple, TypedDict

from pymodbus.constants import Endian

from modules.common import modbus
from modules.common.abstract_device import AbstractBat
from modules.common.component_state import BatState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType
from modules.common.simcount import SimCounter
from modules.common.store import get_bat_value_store
from modules.devices.solaredge.solaredge.config import SolaredgeBatSetup

log = logging.getLogger(__name__)

# Known value returned by some SolarEdge meters for unsupported float32 registers
FLOAT32_UNSUPPORTED = -0xffffff00000000000000000000000000
# According to SolarEdge documentation, battery registers start at 0xE100.
# Common registers (may vary by specific battery model/firmware):
# Using decimal equivalents for addresses provided in some SE docs (e.g., 57600 for 0xE100)
# For the specific LG Chem RESU, addresses like 62836 (Power) and 62852 (SoC) are used.
REG_BAT_POWER = 62836  # Instantaneous Power (W)
REG_BAT_SOC = 62852    # State of Charge (%)


class KwargsDict(TypedDict):
    device_id: int
    client: modbus.ModbusTcpClient_


class SolaredgeBat(AbstractBat):
    def __init__(self, component_config: SolaredgeBatSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__device_id: int = self.kwargs['device_id']
        self.__tcp_client: modbus.ModbusTcpClient_ = self.kwargs['client']
        self.sim_counter = SimCounter(self.__device_id, self.component_config.id, prefix="speicher")
        self.store = get_bat_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self) -> None:
        log.debug("Updating SolaredgeBat id: %s", self.component_config.id)
        try:
            state = self.read_state()
            self.store.set(state)
            self.fault_state.set_fault(False)
        except Exception as e:
            log.error("Error updating SolaredgeBat id %s: %s", self.component_config.id, e, exc_info=True)
            self.fault_state.set_fault(True)

    def read_state(self):
        log.debug("Reading state for SolaredgeBat id: %s", self.component_config.id)
        power, soc = self.get_values()
        imported, exported = self.get_imported_exported(power)
        log.debug("SolaredgeBat %s: Power: %.2fW, SoC: %.2f%%, Imported: %.2fWh, Exported: %.2fWh",
                  self.component_config.id, power, soc, imported, exported)
        return BatState(
            power=power,
            soc=soc,
            imported=imported,
            exported=exported
        )

    def get_values(self) -> Tuple[float, float]:
        unit = self.component_config.configuration.modbus_id
        log.debug("Reading SoC from reg %s for unit %s", REG_BAT_SOC, unit)
        soc = self.__tcp_client.read_holding_registers(
            REG_BAT_SOC, ModbusDataType.FLOAT_32, wordorder=Endian.Little, unit=unit)
        log.debug("Reading Power from reg %s for unit %s", REG_BAT_POWER, unit)
        power = self.__tcp_client.read_holding_registers(
            REG_BAT_POWER, ModbusDataType.FLOAT_32, wordorder=Endian.Little, unit=unit)

        if power == FLOAT32_UNSUPPORTED:
            log.debug("SolaredgeBat %s: Read power as FLOAT32_UNSUPPORTED, setting to 0.", self.component_config.id)
            power = 0
        if soc == FLOAT32_UNSUPPORTED: # Also check SoC for unsupported value
            log.debug("SolaredgeBat %s: Read SoC as FLOAT32_UNSUPPORTED, setting to 0.", self.component_config.id)
            soc = 0
            
        log.debug("SolaredgeBat %s: Raw values: Power: %.2fW, SoC: %.2f%%", self.component_config.id, power, soc)
        return power, soc

    def get_imported_exported(self, power: float) -> Tuple[float, float]:
        return self.sim_counter.sim_count(power)


component_descriptor = ComponentDescriptor(configuration_factory=SolaredgeBatSetup)
