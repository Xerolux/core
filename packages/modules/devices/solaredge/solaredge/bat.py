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

# Initialisiere Logger für die Debug- und Fehlerausgabe
log = logging.getLogger(__name__)


class SolaredgeConfig:
    """
    Konfigurationsklasse für SolarEdge-Registeradressen. 
    Diese Klasse zentralisiert Adressen, um Änderungen einfach umzusetzen.
    """

    def __init__(self):
        # Register für den Steuerungsmodus (Control Mode)
        self.control_mode_register = 0xE00E  # Setzt oder liest den Lade-/Entlademodus
        # Register für Leistungsbegrenzung
        self.power_limit_register = 0xE010  # Maximal erlaubte Lade-/Entladeleistung
        # Register für den Ladezustand der Batterie (State of Charge - SOC)
        self.soc_register = 0xE184  # SOC in Prozent
        # Register für aktuelle Batterieleistung
        self.power_register = 0xE174  # Momentanleistung der Batterie


class SolaredgeBat(AbstractBat):
    """
    Klasse zur Steuerung eines SolarEdge-Speichersystems.
    Ermöglicht Modbus-Kommunikation zum Lesen und Schreiben von Parametern.
    """

    def __init__(self,
                 device_id: int,
                 component_config: Union[Dict, SolaredgeBatSetup],
                 tcp_client: modbus.ModbusTcpClient_,
                 config: SolaredgeConfig) -> None:
        """
        Initialisiert die SolarEdge-Batterie-Klasse.

        :param device_id: Eindeutige ID des Geräts für die Kommunikation.
        :param component_config: Konfigurationseinstellungen für die Batterie.
        :param tcp_client: Modbus-TCP-Client für die Kommunikation.
        :param config: Instanz der Konfigurationsklasse mit Registeradressen.
        """
        self.__device_id = device_id  # Geräte-ID
        self.component_config = dataclass_from_dict(SolaredgeBatSetup, component_config)
        self.__tcp_client = tcp_client  # Modbus-TCP-Client für Lese-/Schreiboperationen
        self.config = config  # SolarEdge-Registerkonfiguration
        self.sim_counter = SimCounter(self.__device_id, self.component_config.id, prefix="speicher")
        self.store = get_bat_value_store(self.component_config.id)  # Interner Zustandsspeicher
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self) -> None:
        """
        Aktualisiert den internen Zustand des Speichers.
        """
        self.store.set(self.read_state())  # Liest den aktuellen Zustand und speichert ihn

    def read_state(self):
        """
        Liest den aktuellen Zustand des Speichers, einschließlich:
        - Leistung (Power)
        - Ladezustand (SOC)
        - Importierte und exportierte Energie.

        :return: Ein BatState-Objekt mit allen wichtigen Zustandswerten.
        """
        power, soc = self.get_values()  # Leistung und SOC abrufen
        imported, exported = self.get_imported_exported(power)  # Import/Export berechnen
        return BatState(
            power=power,
            soc=soc,
            imported=imported,
            exported=exported
        )

    def get_values(self) -> Tuple[float, float]:
        """
        Liest SOC (State of Charge) und Leistung aus den Modbus-Registers.

        :return: SOC (in Prozent) und Leistung (in Watt) als Tupel von Float-Werten.
        """
        unit = self.component_config.configuration.modbus_id  # Modbus-ID des Geräts

        # SOC aus dem konfigurierten Register lesen
        soc_registers = self.__tcp_client.read_holding_registers(self.config.soc_register, count=2, unit=unit)
        if not soc_registers.isError():
            # Dekodiert 32-Bit-Float-Wert für SOC
            soc_decoder = BinaryPayloadDecoder.fromRegisters(
                soc_registers.registers, byteorder=Endian.Little, wordorder=Endian.Little
            )
            soc = soc_decoder.decode_32bit_float()  # SOC-Wert
        else:
            raise Exception(f"Fehler beim Lesen von SOC: {soc_registers}")

        # Momentanleistung aus dem konfigurierten Register lesen
        power_registers = self.__tcp_client.read_holding_registers(self.config.power_register, count=2, unit=unit)
        if not power_registers.isError():
            # Dekodiert 32-Bit-Float-Wert für Leistung
            power_decoder = BinaryPayloadDecoder.fromRegisters(
                power_registers.registers, byteorder=Endian.Little, wordorder=Endian.Little
            )
            power = power_decoder.decode_32bit_float()  # Leistung in Watt
        else:
            raise Exception(f"Fehler beim Lesen der Leistung: {power_registers}")

        return power, soc  # Gibt Leistung und SOC zurück

    def get_control_mode(self) -> int:
        """
        Liest den Steuerungsmodus (Control Mode) aus dem entsprechenden Register.

        :return: Der aktuelle Control Mode als Integer-Wert.
        """
        unit = self.component_config.configuration.modbus_id

        try:
            response = self.__tcp_client.read_holding_registers(self.config.control_mode_register, count=1, unit=unit)
            if not response.isError():
                return response.registers[0]  # Gibt den aktuellen Control Mode zurück
            else:
                raise Exception(f"Fehler beim Lesen des Control Modes: {response}")
        except Exception as e:
            log.error(f"Fehler beim Abrufen des Control Modes: {e}")
            raise

    def set_control_mode(self, mode: int) -> None:
        """
        Setzt den Steuerungsmodus (Control Mode), falls dieser nicht bereits aktiv ist.

        :param mode: Der gewünschte Steuerungsmodus (z. B. 4 für dynamische Leistungsbegrenzung).
        """
        unit = self.component_config.configuration.modbus_id

        try:
            # Aktuellen Steuerungsmodus abrufen
            current_mode = self.get_control_mode()
            if current_mode == mode:
                log.info(f"Control Mode ist bereits auf {mode} gesetzt.")
                return  # Kein Schreibvorgang erforderlich

            # Steuerungsmodus in das Register schreiben
            self.__tcp_client.write_register(self.config.control_mode_register, mode, unit=unit)
            log.info(f"Control Mode erfolgreich auf {mode} gesetzt.")
        except Exception as e:
            log.error(f"Fehler beim Setzen des Control Modes: {e}")
            raise

    def set_power_limit(self, power_limit: Optional[float]) -> None:
        """
        Setzt die Leistungsbegrenzung für das Laden/Entladen.

        :param power_limit: Die gewünschte Begrenzung in Watt.
                            - Ein Wert aktiviert die Steuerung.
                            - None setzt die Begrenzung zurück.
        """
        unit = self.component_config.configuration.modbus_id

        try:
            # Sicherstellen, dass der Modus für Leistungsbegrenzung aktiv ist
            self.set_control_mode(4)

            if power_limit is None:
                # Begrenzung zurücksetzen
                self.__tcp_client.write_registers(self.config.power_limit_register, [0, 0], unit=unit)
            else:
                if power_limit < 0:
                    raise ValueError("Die Leistungsbegrenzung muss positiv sein.")

                # Konvertiere Float-Wert in Modbus-kompatibles Registerformat
                builder = BinaryPayloadBuilder(byteorder=Endian.Little, wordorder=Endian.Little)
                builder.add_32bit_float(power_limit)
                registers = builder.to_registers()

                # Schreibvorgang für die Leistungsbegrenzung
                self.__tcp_client.write_registers(self.config.power_limit_register, registers, unit=unit)
                log.info(f"Leistungsbegrenzung erfolgreich auf {power_limit} W gesetzt.")
        except Exception as e:
            log.error(f"Fehler beim Setzen der Leistungsbegrenzung: {e}")
            raise


# Beschreibung der Konfigurationskomponente
component_descriptor = ComponentDescriptor(configuration_factory=SolaredgeBatSetup)
