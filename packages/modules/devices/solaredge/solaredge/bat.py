#!/usr/bin/env python3
import logging
from typing import Optional, Dict, Tuple, Union

from pymodbus.constants import Endian
from dataclass_utils import dataclass_from_dict
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

class SolaredgeBat(AbstractBat):
    def __init__(self,
                 device_id: int,
                 component_config: Union[Dict, SolaredgeBatSetup],
                 tcp_client: modbus.ModbusTcpClient_) -> None:
        self.__device_id = device_id
        self.component_config = dataclass_from_dict(SolaredgeBatSetup, component_config)
        self.__tcp_client = tcp_client
        self.sim_counter = SimCounter(self.__device_id, self.component_config.id, prefix="speicher")
        self.store = get_bat_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self) -> None:
        self.store.set(self.read_state())

    def read_state(self):
        power, soc = self.get_values()
        imported, exported = self.get_imported_exported(power)
        return BatState(
            power=power,
            soc=soc,
            imported=imported,
            exported=exported
        )

    def get_values(self) -> Tuple[float, float]:
        unit = self.component_config.configuration.modbus_id
        soc = self.__tcp_client.read_holding_registers(
            0xE184, ModbusDataType.FLOAT_32, wordorder=Endian.Little, unit=unit)  # SOC
        power = self.__tcp_client.read_holding_registers(
            0xE174, ModbusDataType.FLOAT_32, wordorder=Endian.Little, unit=unit)  # Leistung
        return power, soc

    def set_power_limit(self, power_limit: Optional[int]) -> None:
        """
        Setzt die Leistungsbegrenzung des Speichers.

        :param power_limit: Lade-/Entladeleistung in Watt.
                            - Eine Zahl schaltet auf aktive Speichersteuerung um.
                            - None übergibt die Null-Punkt-Ausregelung an den Speicher.
        """
        unit = self.component_config.configuration.modbus_id
        reg = 0xE00E if power_limit is not None else 0xE010  # Unterschiedliche Register für Laden/Entladen

        if power_limit is None:
            # Null-Punkt-Ausregelung aktivieren
            self.__tcp_client.write_registers(0xE010, 0, unit=unit)
        else:
            # Lade-/Entladeleistung setzen
            self.__tcp_client.write_registers(reg, power_limit, unit=unit)


component_descriptor = ComponentDescriptor(configuration_factory=SolaredgeBatSetup)
