#!/usr/bin/env python3
import logging
from typing import Optional, Dict, Tuple, Union

from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder
from dataclass_utils import dataclass_from_dict
from modules.common import modbus
from modules.common.abstract_device import AbstractBat
from modules.common.component_state import BatState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
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
        """
        Liest SOC (State of Charge) und Leistung aus den Modbus-Registern.
        
        :return: SOC und Leistung als Float-Werte
        """
        unit = self.component_config.configuration.modbus_id

        # SOC (State of Charge) lesen
        soc_registers = self.__tcp_client.read_holding_registers(0xE184, count=2, unit=unit)
        if not soc_registers.isError():
            soc_decoder = BinaryPayloadDecoder.fromRegisters(
                soc_registers.registers, byteorder=Endian.Little, wordorder=Endian.Little
            )
            soc = soc_decoder.decode_32bit_float()
        else:
            raise Exception(f"Fehler beim Lesen von SOC: {soc_registers}")

        # Leistung lesen
        power_registers = self.__tcp_client.read_holding_registers(0xE174, count=2, unit=unit)
        if not power_registers.isError():
            power_decoder = BinaryPayloadDecoder.fromRegisters(
                power_registers.registers, byteorder=Endian.Little, wordorder=Endian.Little
            )
            power = power_decoder.decode_32bit_float()
        else:
            raise Exception(f"Fehler beim Lesen der Leistung: {power_registers}")

        return power, soc

    def set_power_limit(self, power_limit: Optional[float]) -> None:
        """
        Setzt die Leistungsbegrenzung des Speichers (Float32-Unterstützung).

        :param power_limit: Lade-/Entladeleistung in Watt.
                            - Eine Zahl aktiviert die aktive Speichersteuerung.
                            - None aktiviert die Null-Punkt-Ausregelung.
        """
        REGISTER_LOAD_UNLOAD = 0xE00E
        REGISTER_ZERO_BALANCE = 0xE010
        unit = self.component_config.configuration.modbus_id

        try:
            if power_limit is None:
                # Null-Punkt-Ausregelung aktivieren
                self.__tcp_client.write_registers(REGISTER_ZERO_BALANCE, [0, 0], unit=unit)
            else:
                if power_limit < 0:
                    raise ValueError("Die Leistungsbegrenzung muss eine positive Zahl sein.")
                
                # Float32 in Modbus-kompatibles Little-Endian-Format konvertieren
                builder = BinaryPayloadBuilder(byteorder=Endian.Little, wordorder=Endian.Little)
                builder.add_32bit_float(power_limit)
                registers = builder.to_registers()
                
                # Lade-/Entladeleistung setzen
                self.__tcp_client.write_registers(REGISTER_LOAD_UNLOAD, registers, unit=unit)
        except Exception as e:
            logging.error(f"Fehler beim Setzen der Leistungsbegrenzung: {e}")
            raise


component_descriptor = ComponentDescriptor(configuration_factory=SolaredgeBatSetup)
