#!/usr/bin/env python3
import logging
from typing import Any, Callable, Optional

from modules.common.abstract_device import AbstractInverter
from modules.common.component_state import InverterState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.modbus import ModbusDataType
from modules.common.store import get_inverter_value_store
from modules.devices.kostal.kostal_plenticore.config import KostalPlenticoreInverterSetup

log = logging.getLogger(__name__)


class KostalPlenticoreInverter(AbstractInverter):
    def __init__(self, component_config: KostalPlenticoreInverterSetup) -> None:
        self.component_config = component_config

    def initialize(self) -> None:
        self.store = get_inverter_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def read_state(self, reader: Callable[[int, ModbusDataType], Any]) -> Optional[InverterState]:
        try:
            # PV-Anlage kann nichts verbrauchen, also ggf. Register-/Rundungsfehler korrigieren.
            # Wordorder is handled by the reader's partial function in device.py (corrected to Big Endian)
            power = reader(575, ModbusDataType.INT_16) * -1
            exported = reader(320, ModbusDataType.FLOAT_32)

            state = InverterState(
                power=power,
                exported=exported
            )
            self.fault_state.set_fault(False)
            return state
        except Exception as e:
            log.error(
                f"Error reading Kostal Plenticore Inverter id: {self.component_config.id}: {e}",
                exc_info=True
            )
            self.fault_state.set_fault(True)
            return None

    def dc_in_string_1_2(self, reader: Callable[[int, ModbusDataType], Any]) -> Optional[float]:
        # This method is called by the device.py's update function but its result isn't directly
        # used to set a fault state on this component. For now, just let exceptions propagate
        # or add similar try-except if specific fault handling for this read is needed.
        # Considering it's read alongside other values, an error here would likely be caught
        # by a broader try-except in the device.py or if read_state itself fails.
        # For component-level fault state, read_state is the primary method.
        # However, if this method failing should set the component fault, it needs its own try-except.
        # For now, let's assume errors here are less critical or handled by device.py's general update loop.
        # If not, a similar try-except to read_state would be needed.
        try:
            # Wordorder is handled by the reader's partial function in device.py (corrected to Big Endian)
            val = reader(260, ModbusDataType.FLOAT_32) + reader(270, ModbusDataType.FLOAT_32)
            return val
        except Exception as e:
            log.error(
                f"Error reading Kostal Plenticore Inverter DC strings id: {self.component_config.id}: {e}",
                exc_info=True
            )
            # Not setting component fault state here as this method is auxiliary to read_state.
            # The main fault should be based on read_state's success.
            return None


    def update(self, state: Optional[InverterState]):
        # This update method is called by the device specific update logic.
        # It assumes that if 'state' is None, an error has already been handled (logged, fault set)
        # by the method that tried to read the state (e.g., self.read_state or logic in device.py).
        if state is not None:
            self.store.set(state)
        # If state is None, implies read failed, fault_state should have been set by the reader method.


component_descriptor = ComponentDescriptor(configuration_factory=KostalPlenticoreInverterSetup)
