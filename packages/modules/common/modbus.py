#!/usr/bin/env python3
"""Modul für einfache Modbus-Operationen.

Das Modul baut eine Modbus-TCP-Verbindung auf. Es gibt verschiedene Funktionen, um die gelesenen Register zu
formatieren.
"""
import logging
import struct
from enum import Enum
import time
from typing import Any, Callable, Iterable, Optional, Union, overload, List

import pymodbus
from pymodbus.client import ModbusTcpClient, ModbusSerialClient  # Geänderter Import für die Clients
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.exceptions import ModbusIOException, ConnectionException  # Import von spezifischen Exceptions
from urllib3.util import parse_url

log = logging.getLogger(__name__)

class ModbusDataType(Enum):
    UINT_8 = 8, "decode_8bit_uint"
    UINT_16 = 16, "decode_16bit_uint"
    UINT_32 = 32, "decode_32bit_uint"
    UINT_64 = 64, "decode_64bit_uint"
    INT_8 = 8, "decode_8bit_int"
    INT_16 = 16, "decode_16bit_int"
    INT_32 = 32, "decode_32bit_int"
    INT_64 = 64, "decode_64bit_int"
    FLOAT_16 = 16, "decode_16bit_float"
    FLOAT_32 = 32, "decode_32bit_float"
    FLOAT_64 = 64, "decode_64bit_float"

    def __init__(self, bits: int, decoding_method: str):
        self.bits = bits
        self.decoding_method = decoding_method


_MODBUS_HOLDING_REGISTER_SIZE = 16
Number = Union[int, float]

NO_CONNECTION = ("Modbus-Client konnte keine Verbindung zu {}:{} aufbauen. Bitte "
                 "Einstellungen, IP-Adresse und Port sowie Netzwerk-Anschluss prüfen.")
NO_VALUES = ("TCP-Client {}:{} konnte keinen Wert abfragen. Falls vorhanden, parallele Verbindungen, zB. node red,"
             "beenden und bei anhaltender Fehlermeldung Zähler neu starten.")


class ModbusClient:
    def __init__(self,
                 delegate: Union[ModbusSerialClient, ModbusTcpClient],
                 address: str, port: int = 502,
                 sleep_after_connect: Optional[int] = 0):
        self._delegate = delegate
        self.address = address
        self.port = port
        self.sleep_after_connect = sleep_after_connect

    def __enter__(self):
        try:
            self._delegate.connect()  # In pymodbus 3.x wird connect() explizit aufgerufen
            time.sleep(self.sleep_after_connect)
        except ConnectionException as e:
            e.args += (NO_CONNECTION.format(self.address, self.port),)
            raise e
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self._delegate.close()

    def connect(self) -> None:
        self._delegate.connect()
        time.sleep(self.sleep_after_connect)

    def close(self) -> None:
        try:
            log.debug("Close Modbus TCP connection")
            self._delegate.close()
        except Exception as e:
            raise Exception(__name__+" "+str(type(e))+" " + str(e)) from e

    def is_socket_open(self) -> bool:
        return self._delegate.is_socket_open()

    def __read_registers(self, read_register_method: Callable,
                         address: int,
                         types: Union[Iterable[ModbusDataType], ModbusDataType],
                         byteorder: Endian = Endian.Big,
                         wordorder: Endian = Endian.Big,
                         **kwargs):
        if not self.is_socket_open():
            self.connect()
        try:
            multi_request = isinstance(types, Iterable)
            if not multi_request:
                types = [types]

            def divide_rounding_up(numerator: int, denominator: int):
                return -(-numerator // denominator)

            number_of_addresses = sum(divide_rounding_up(
                t.bits, _MODBUS_HOLDING_REGISTER_SIZE) for t in types)
            response = read_register_method(
                address, number_of_addresses, **kwargs)
            if response.isError():
                raise Exception(__name__+" "+str(response))
            decoder = BinaryPayloadDecoder.fromRegisters(response.registers, byteorder, wordorder)
            result = [struct.unpack(">e", struct.pack(">H", decoder.decode_16bit_uint())) if t ==
                      ModbusDataType.FLOAT_16 else getattr(decoder, t.decoding_method)() for t in types]
            return result if multi_request else result[0]
        except ConnectionException as e:
            self.close()
            e.args += (NO_CONNECTION.format(self.address, self.port),)
            raise e
        except ModbusIOException as e:
            self.close()
            e.args += (NO_VALUES.format(self.address, self.port),)
            raise e
        except Exception as e:
            self.close()
            raise Exception(__name__+" "+str(type(e))+" " + str(e)) from e

    @overload
    def read_holding_registers(self, address: int, types: Iterable[ModbusDataType], byteorder: Endian = Endian.Big,
                               wordorder: Endian = Endian.Big, **kwargs) -> List[Number]:
        pass

    @overload
    def read_holding_registers(self, address: int, types: ModbusDataType, byteorder: Endian = Endian.Big,
                               wordorder: Endian = Endian.Big, **kwargs) -> Number:
        pass

    def read_holding_registers(self, address: int,
                               types: Union[Iterable[ModbusDataType], ModbusDataType],
                               byteorder: Endian = Endian.Big,
                               wordorder: Endian = Endian.Big,
                               **kwargs):
        return self.__read_registers(
            self._delegate.read_holding_registers, address, types, byteorder, wordorder, **kwargs
        )

    @overload
    def read_input_registers(self, address: int, types: Iterable[ModbusDataType], byteorder: Endian = Endian.Big,
                             wordorder: Endian = Endian.Big,
                             **kwargs) -> List[Number]:
        pass

    @overload
    def read_input_registers(self, address: int, types: ModbusDataType, byteorder: Endian = Endian.Big,
                             wordorder: Endian = Endian.Big, **kwargs) -> Number:
        pass

    def read_input_registers(self, address: int,
                             types: Union[Iterable[ModbusDataType], ModbusDataType],
                             byteorder: Endian = Endian.Big,
                             wordorder: Endian = Endian.Big,
                             **kwargs):
        return self.__read_registers(self._delegate.read_input_registers,
                                     address,
                                     types,
                                     byteorder,
                                     wordorder,
                                     **kwargs)

    @overload
    def read_coils(self, address: int, types: Iterable[ModbusDataType], byteorder: Endian = Endian.Big,
                   wordorder: Endian = Endian.Big,
                   **kwargs) -> List[bool]:
        pass

    @overload
    def read_coils(self, address: int, count: int, **kwargs) -> bool:
        pass

    def read_coils(self, address: int, count: int, **kwargs):
        try:
            response = self._delegate.read_coils(address, count, **kwargs)
            if response.isError():
                raise Exception(__name__+" "+str(response))
            return response.bits[0] if count == 1 else response.bits[:count]
        except ConnectionException as e:
            e.args += (NO_CONNECTION.format(self.address, self.port),)
            raise e
        except ModbusIOException as e:
            e.args += (NO_VALUES.format(self.address, self.port),)
            raise e

    def write_registers(self, address: int, value: Any, **kwargs):
        self._delegate.write_registers(address, value, **kwargs)


class ModbusTcpClient_(ModbusClient):
    def __init__(self,
                 address: str,
                 port: int = 502,
                 sleep_after_connect: Optional[int] = 0,
                 **kwargs):
        parsed_url = parse
