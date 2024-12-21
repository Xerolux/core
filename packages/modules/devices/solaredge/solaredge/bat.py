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
    """
    Klasse zur Steuerung eines SolarEdge-Speichers.
    Unterstützt das Lesen und Schreiben von Modbus-Parametern.
    """

    def __init__(self,
                 device_id: int,
                 component_config: Union[Dict, SolaredgeBatSetup],
                 tcp_client: modbus.ModbusTcpClient_) -> None:
        """
        Initialisiert die SolaredgeBat-Klasse.

        :param device_id: ID des Geräts.
        :param component_config: Konfigurationsdaten für das Gerät.
        :param tcp_client: Modbus-TCP-Client zur Kommunikation.
        """
        self.__device_id = device_id
        self.component_config = dataclass_from_dict(SolaredgeBatSetup, component_config)
        self.__tcp_client = tcp_client
        self.sim_counter = SimCounter(self.__device_id, self.component_config.id, prefix="speicher")
        self.store = get_bat_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self) -> None:
        """
        Aktualisiert den Zustand des Speichers im Speicher (State Store).
        """
        self.store.set(self.read_state())

    def read_state(self):
        """
        Liest den Zustand des Speichers aus, einschließlich Leistung und SOC.

        :return: Ein BatState-Objekt mit Leistung, SOC, importierter und exportierter Energie.
        """
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
        Liest den SOC (State of Charge) und die Leistung aus Modbus-Registers.

        :return: SOC (in %) und Leistung (in Watt) als Float-Werte.
        """
        unit = self.component_config.configuration.modbus_id

        # SOC aus zwei aufeinanderfolgenden Registern lesen (0xE184)
        soc_registers = self.__tcp_client.read_holding_registers(0xE184, count=2, unit=unit)
        if not soc_registers.isError():
            soc_decoder = BinaryPayloadDecoder.fromRegisters(
                soc_registers.registers, byteorder=Endian.Little, wordorder=Endian.Little
            )
            soc = soc_decoder.decode_32bit_float()
        else:
            raise Exception(f"Fehler beim Lesen von SOC: {soc_registers}")

        # Leistung aus zwei aufeinanderfolgenden Registern lesen (0xE174)
        power_registers = self.__tcp_client.read_holding_registers(0xE174, count=2, unit=unit)
        if not power_registers.isError():
            power_decoder = BinaryPayloadDecoder.fromRegisters(
                power_registers.registers, byteorder=Endian.Little, wordorder=Endian.Little
            )
            power = power_decoder.decode_32bit_float()
        else:
            raise Exception(f"Fehler beim Lesen der Leistung: {power_registers}")

        return power, soc

    def get_control_mode(self) -> int:
        """
        Liest den aktuellen Steuerungsmodus (Control Mode) aus dem Register.

        :return: Der aktuelle Control Mode als Integer.
        """
        REGISTER_CONTROL_MODE = 0xE00E  # Alte Registeradresse für Control Mode
        unit = self.component_config.configuration.modbus_id

        try:
            # Control Mode aus dem Register lesen
            response = self.__tcp_client.read_holding_registers(REGISTER_CONTROL_MODE, count=1, unit=unit)
            if not response.isError():
                return response.registers[0]
            else:
                raise Exception(f"Fehler beim Lesen des Control Modes: {response}")
        except Exception as e:
            log.error(f"Fehler beim Abrufen des Control Modes: {e}")
            raise

    def set_control_mode(self, mode: int) -> None:
        """
        Setzt den Control Mode, falls er nicht bereits auf dem gewünschten Wert ist.

        :param mode: Der gewünschte Control Mode (z. B. 4 für dynamische Leistungsbegrenzung).
        """
        REGISTER_CONTROL_MODE = 0xE00E  # Alte Registeradresse für Control Mode
        unit = self.component_config.configuration.modbus_id

        try:
            current_mode = self.get_control_mode()
            if current_mode == mode:
                log.info(f"Control Mode ist bereits auf {mode} gesetzt.")
                return  # Kein Schreibvorgang erforderlich

            # Neuen Control Mode schreiben
            self.__tcp_client.write_register(REGISTER_CONTROL_MODE, mode, unit=unit)
            log.info(f"Control Mode erfolgreich auf {mode} gesetzt.")
        except Exception as e:
            log.error(f"Fehler beim Setzen des Control Modes: {e}")
            raise

    def set_power_limit(self, power_limit: Optional[float]) -> None:
        """
        Setzt die Leistungsbegrenzung des Speichers.

        :param power_limit: Lade-/Entladeleistung in Watt als Float.
                            - Eine Zahl aktiviert die aktive Speichersteuerung.
                            - None setzt die Leistungsbegrenzung zurück.
        """
        REGISTER_POWER_LIMIT = 0xE010  # Alte Registeradresse für die Leistungsbegrenzung
        unit = self.component_config.configuration.modbus_id

        try:
            # Sicherstellen, dass der Control Mode 4 aktiv ist
            self.set_control_mode(4)

            if power_limit is None:
                # Null-Punkt-Ausregelung aktivieren
                self.__tcp_client.write_registers(REGISTER_POWER_LIMIT, [0, 0], unit=unit)
            else:
                if power_limit < 0:
                    raise ValueError("Die Leistungsbegrenzung muss eine positive Zahl sein.")
                
                # Float32-Wert in Modbus-kompatibles Format konvertieren
                builder = BinaryPayloadBuilder(byteorder=Endian.Little, wordorder=Endian.Little)
                builder.add_32bit_float(power_limit)
                registers = builder.to_registers()
                
                # Leistungsbegrenzung schreiben
                self.__tcp_client.write_registers(REGISTER_POWER_LIMIT, registers, unit=unit)
                log.info(f"Leistungsbegrenzung erfolgreich auf {power_limit} W gesetzt.")
        except Exception as e:
            log.error(f"Fehler beim Setzen der Leistungsbegrenzung: {e}")
            raise


component_descriptor = ComponentDescriptor(configuration_factory=SolaredgeBatSetup)
