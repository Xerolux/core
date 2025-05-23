#!/usr/bin/env python3
from typing import Any, Callable, TypedDict
from modules.common.abstract_device import AbstractCounter
from modules.common.component_state import CounterState
import logging
from typing import Optional

from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType
from modules.common.simcount import SimCounter
from modules.common.store import get_counter_value_store
from modules.devices.kostal.kostal_plenticore.config import KostalPlenticoreCounterSetup

log = logging.getLogger(__name__)


class KwargsDict(TypedDict):
    device_id: int


class KostalPlenticoreCounter(AbstractCounter):
    def __init__(self, component_config: KostalPlenticoreCounterSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__device_id: int = self.kwargs['device_id']
        self.store = get_counter_value_store(self.component_config.id)
        self.sim_counter = SimCounter(self.__device_id, self.component_config.id, prefix="bezug")
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def get_values(self, reader: Callable[[int, ModbusDataType], Any]) -> Optional[CounterState]:
        try:
            # Wordorder is handled by the reader's partial function in device.py (corrected to Big Endian)
            power_factor = reader(150, ModbusDataType.FLOAT_32)
            currents = [reader(register, ModbusDataType.FLOAT_32) for register in [222, 232, 242]]
            voltages = [reader(register, ModbusDataType.FLOAT_32) for register in [230, 240, 250]]
            powers = [reader(register, ModbusDataType.FLOAT_32) for register in [224, 234, 244]]
            power = reader(252, ModbusDataType.FLOAT_32)
            frequency = reader(220, ModbusDataType.FLOAT_32)

            # Ensure all list comprehensions didn't encounter None if reader could return None on sub-errors
            if any(v is None for v in currents + voltages + powers):
                 log.warning(f"Some list values were None during Kostal Counter read for id: {self.component_config.id}")
                 # This might indicate an issue if reader is expected to throw or if None means specific error
                 # For now, this will likely lead to an error in CounterState or be caught by outer try-except.
                 # If reader is robust enough to return None for individual failed reads within a list,
                 # more granular error handling for list items might be needed here.
                 # Assuming reader throws an exception if any part of a multi-read request fails.

            state = CounterState(
                powers=powers,
                currents=currents,
                voltages=voltages,
                power=power,
                power_factors=[power_factor] * 3, # Python list multiplication is fine here.
                frequency=frequency
            )
            self.fault_state.set_fault(False)
            return state
        except Exception as e:
            log.error(
                f"Error reading Kostal Plenticore Counter id: {self.component_config.id}: {e}",
                exc_info=True
            )
            self.fault_state.set_fault(True)
            return None

    def update_imported_exported(self, state: CounterState) -> CounterState:
        # This check is important if state can be None
        if state is None:
            # Or handle this case appropriately, maybe return None or an empty/default state
            # For now, let's assume this function is only called with a valid state.
            # If get_values returns None, update method should not call this.
            raise ValueError("update_imported_exported called with None state")
            
        state.imported, state.exported = self.sim_counter.sim_count(state.power)
        return state

    def update(self, reader: Callable[[int, ModbusDataType], Any]):
        values_state = self.get_values(reader)
        if values_state is not None:
            # If get_values was successful, update imported/exported and set to store
            final_state = self.update_imported_exported(values_state)
            self.store.set(final_state)
        # If values_state is None, get_values already logged error and set fault_state. Nothing to store.


component_descriptor = ComponentDescriptor(configuration_factory=KostalPlenticoreCounterSetup)
