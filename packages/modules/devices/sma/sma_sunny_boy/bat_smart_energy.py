#!/usr/bin/env python3
import pymodbus
from typing import TypedDict, Any, Dict, Union, Optional
import logging

from modules.devices.sma.sma_sunny_boy.config import SmaSunnyBoySmartEnergyBatSetup
from modules.common.store import get_bat_value_store
from modules.common.modbus import ModbusTcpClient_, ModbusDataType
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.component_type import ComponentDescriptor
from modules.common.component_state import BatState
from modules.common.abstract_device import AbstractBat


log = logging.getLogger(__name__)


class KwargsDict(TypedDict):
    client: ModbusTcpClient_


class SunnyBoySmartEnergyBat(AbstractBat):
    SMA_UINT32_NAN = 0xFFFFFFFF  # SMA uses this value to represent NaN
    SMA_UINT_64_NAN = 0xFFFFFFFFFFFFFFFF  # SMA uses this value to represent NaN

    # Define all possible registers with their data types
    REGISTERS = {
        "Battery_SoC": (30845, ModbusDataType.UINT_32),
        "Battery_ChargePower": (31393, ModbusDataType.INT_32),
        "Battery_DischargePower": (31395, ModbusDataType.INT_32),
        "Battery_ChargedEnergy": (31397, ModbusDataType.UINT_64),
        "Battery_DischargedEnergy": (31401, ModbusDataType.UINT_64),
        "Inverter_Type": (30053, ModbusDataType.UINT_32),
        "Externe_Steuerung": (40151, ModbusDataType.UINT_32),
        "Wirkleistungsvorgabe": (40149, ModbusDataType.UINT_32),
    }

    def __init__(self, component_config: SmaSunnyBoySmartEnergyBatSetup, **kwargs: Any) -> None:
        self.component_config = component_config
        self.kwargs: KwargsDict = kwargs

    def initialize(self) -> None:
        self.__tcp_client: ModbusTcpClient_ = self.kwargs['client']
        self.store = get_bat_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))
        self.last_mode = 'Undefined'
        self.inverter_type = None

    def update(self) -> None:
        try:
            state = self.read()
            if state:  # read() now returns Optional[BatState]
                self.store.set(state)
                self.fault_state.set_fault(False)
            # If read() returns None, it means an error occurred and fault_state was set there.
        except Exception as e:
            # This outer try-except is a fallback if read() itself has an unhandled exception
            # or if an error occurs outside the Modbus calls within read().
            log.error(
                f"Unhandled error in SMA Sunny Boy Smart Energy Bat update for id: {self.component_config.id}: {e}",
                exc_info=True
            )
            self.fault_state.set_fault(True)

    def read(self) -> Optional[BatState]:
        unit = self.component_config.configuration.modbus_id
        try:

        registers_to_read = [
            "Battery_SoC",
            "Battery_ChargePower",
            "Battery_DischargePower",
            "Battery_ChargedEnergy",
            "Battery_DischargedEnergy"
        ]

        if self.inverter_type is None:  # Only read Inverter_Type if not already set
            registers_to_read.append("Inverter_Type")

        values = self._read_registers(registers_to_read, unit)

        if values["Battery_SoC"] == self.SMA_UINT32_NAN:
            # If the storage is empty and nothing is produced on the DC side, the inverter does not supply any values.
            values["Battery_SoC"] = 0
            power = 0
        else:
            if values["Battery_ChargePower"] > 5:
                power = values["Battery_ChargePower"]
            else:
                power = values["Battery_DischargePower"] * -1

        if (values["Battery_ChargedEnergy"] == self.SMA_UINT_64_NAN or
                values["Battery_DischargedEnergy"] == self.SMA_UINT_64_NAN):
            raise ValueError(
                f'Batterie lieferte nicht plausible Werte. Geladene Energie: {values["Battery_ChargedEnergy"]}, '
                f'Entladene Energie: {values["Battery_DischargedEnergy"]}. ',
                'Sobald die Batterie geladen/entladen wird sollte sich dieser Wert ändern, ',
                'andernfalls kann ein Defekt vorliegen.'
            )

        bat_state = BatState(
            power=power,
            soc=values["Battery_SoC"],
            exported=values["Battery_DischargedEnergy"],
            imported=values["Battery_ChargedEnergy"]
        )
        if self.inverter_type is None:
            self.inverter_type = values["Inverter_Type"]
        log.debug(f"Inverter Type: {self.inverter_type}")
        log.debug(f"Bat {self.__tcp_client.address}: {bat_state}")
        # Successfully read and processed data
        # self.fault_state.set_fault(False) # Moved to update()
        return bat_state
        except Exception as e:
            log.error(
                f"Error reading SMA Sunny Boy Smart Energy Bat id: {self.component_config.id}: {e}",
                exc_info=True
            )
            self.fault_state.set_fault(True) # Set fault state here as read failed
            return None

    def set_power_limit(self, power_limit: Optional[int]) -> None:
        unit = self.component_config.configuration.modbus_id
        try:
            if power_limit is None:
                if self.last_mode is not None:
                    log.debug("Keine Batteriesteuerung gefordert, deaktiviere externe Steuerung.")
                    values_to_write = {
                        "Externe_Steuerung": 803,
                        "Wirkleistungsvorgabe": 0,
                    }
                    self._write_registers(values_to_write, unit)
                    self.last_mode = None
            else:
                log.debug("Aktive Batteriesteuerung vorhanden. Setze externe Steuerung.")
                values_to_write = {
                    "Externe_Steuerung": 802,
                    "Wirkleistungsvorgabe": power_limit
                }
                self._write_registers(values_to_write, unit)
                self.last_mode = 'limited'
            # Assuming if _write_registers doesn't throw, the operation was successful regarding fault state.
            # If granular fault for write is needed, _write_registers should return status or handle fault.
            # For now, if no exception, assume success for this operation's impact on component health.
            # self.fault_state.set_fault(False) # This might wrongly clear a fault from a failed read.
            # Fault state for writes is tricky; usually, if a write fails, an exception is thrown.
            # If it completes, it's "successful" but doesn't necessarily mean the overall component is fault-free
            # if a previous read failed. Let's leave fault state primarily managed by read operations.
        except Exception as e:
            log.error(
                f"Error setting power limit for SMA Sunny Boy Smart Energy Bat id: {self.component_config.id}: {e}",
                exc_info=True
            )
            self.fault_state.set_fault(True) # A failed write operation is a fault.


    def _read_registers(self, register_names: list, unit: int) -> Dict[str, Union[int, float]]:
        # This internal method does not handle exceptions itself; expects caller (read()) to handle.
        # Wordorder for multi-register reads defaults to Big Endian via common.modbus.py.
        # This is generally appropriate for SMA devices.
        values = {}
        for key in register_names:
            address, data_type = self.REGISTERS[key]
            values[key] = self.__tcp_client.read_holding_registers(address, data_type, unit=unit)
        log.debug(f"Bat raw values {self.__tcp_client.address}: {values}")
        return values

    def _write_registers(self, values_to_write: Dict[str, Union[int, float]], unit: int) -> None:
        # This internal method does not handle exceptions itself; expects caller (set_power_limit()) to handle.
        for key, value in values_to_write.items():
            address, data_type = self.REGISTERS[key]
            encoded_value = self._encode_value(value, data_type)
            self.__tcp_client.write_registers(address, encoded_value, unit=unit)
            log.debug(f"Neuer Wert {encoded_value} in Register {address} geschrieben.")

    def _encode_value(self, value: Union[int, float], data_type: ModbusDataType) -> list:
        # Wordorder is explicitly Big Endian here, which is correct for SMA.
        builder = pymodbus.payload.BinaryPayloadBuilder(
            byteorder=pymodbus.constants.Endian.Big,
            wordorder=pymodbus.constants.Endian.Big
        )
        encode_methods = {
            ModbusDataType.UINT_32: builder.add_32bit_uint,
            ModbusDataType.INT_32: builder.add_32bit_int,
            ModbusDataType.UINT_16: builder.add_16bit_uint,
            ModbusDataType.INT_16: builder.add_16bit_int,
        }

        if data_type in encode_methods:
            encode_methods[data_type](int(value))
        else:
            raise ValueError(f"Unsupported data type: {data_type}")

        return builder.to_registers()

    def power_limit_controllable(self) -> bool:
        return True


component_descriptor = ComponentDescriptor(configuration_factory=SmaSunnyBoySmartEnergyBatSetup)
