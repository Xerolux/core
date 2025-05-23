#!/usr/bin/env python3
import logging
from typing import Any, Callable, TypedDict
from modules.common.abstract_device import AbstractBat
from modules.common.component_state import BatState
from modules.common.component_type import ComponentDescriptor
from modules.common.modbus import ModbusDataType
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.simcount import SimCounter
from modules.common.store import get_bat_value_store
from modules.devices.kostal.kostal_plenticore.config import KostalPlenticoreBatSetup

log = logging.getLogger(__name__)


class KwargsDict(TypedDict):
    device_id: int


class KostalPlenticoreBat(AbstractBat):
    def __init__(self, component_config: KostalPlenticoreBatSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__device_id: int = self.kwargs['device_id']
        self.store = get_bat_value_store(self.component_config.id)
        self.sim_counter = SimCounter(self.__device_id, self.component_config.id, prefix="speicher")
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def read_state(self, reader: Callable[[int, ModbusDataType], Any]) -> Optional[BatState]:
        try:
            # Wordorder is handled by the reader's partial function in device.py (corrected to Big Endian)
            power_raw = reader(582, ModbusDataType.INT_16) * -1
            soc = reader(514, ModbusDataType.INT_16)
            
            power = power_raw
            log.debug("raw bat power " + str(power))
            # Speicherladung muss durch Wandlungsverluste und internen Verbrauch korrigiert werden, sonst
            # wird ein falscher Hausverbrauch berechnet. Die Verluste fallen hier unter den Tisch.
            if power < 0:
                # Wordorder for FLOAT_32 is handled by the reader.
                power_float = reader(106, ModbusDataType.FLOAT_32)
                if power_float is not None: # reader might return None if sub-read fails and is handled by reader itself
                    power = power_float * -1
                else: # Handle case where conditional read might fail if reader could return None
                    log.warning(f"Conditional read for battery power (reg 106) for Kostal Plenticore Bat id: {self.component_config.id} returned None.")
                    # Decide if this constitutes a fault or if using power_raw is acceptable
                    # For now, let's assume if this specific read fails, we might still proceed with raw power or fault.
                    # Re-throwing or returning None here would be caught by the outer try-except.
                    # If reader itself handles its exceptions and returns None, this needs to be robust.
                    # Assuming reader propagates exceptions for this logic to work:
                    pass


            imported, exported = self.sim_counter.sim_count(power)

            state = BatState(
                power=power,
                soc=soc,
                imported=imported,
                exported=exported,
            )
            self.fault_state.set_fault(False)
            return state
        except Exception as e:
            log.error(
                f"Error reading Kostal Plenticore Battery id: {self.component_config.id}: {e}",
                exc_info=True
            )
            self.fault_state.set_fault(True)
            return None

    def update(self, state: Optional[BatState]):
        if state is not None:
            self.store.set(state)
        # If state is None, implies read failed, fault_state should have been set by read_state.


component_descriptor = ComponentDescriptor(configuration_factory=KostalPlenticoreBatSetup)
