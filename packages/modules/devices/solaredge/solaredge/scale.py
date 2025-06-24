import logging
import math
from typing import List

from modules.common.modbus import ModbusDataType, ModbusTcpClient_, Number

log = logging.getLogger(__name__)

# Registers that are not applicable to a meter class return the unsupported value. (e.g. Single Phase
# meters will support only summary and phase A values):

UINT16_UNSUPPORTED = 0xFFFF

# Cache für Scale-Faktoren - diese ändern sich NIE!
_scale_factor_cache = {}


def scale_registers(registers: List[Number]) -> List[float]:
    log.debug("Registers %s, Scale %s", registers[:-1],  registers[-1])
    scale = math.pow(10, registers[-1])
    return [register * scale if register != UINT16_UNSUPPORTED else 0 for register in registers[:-1]]


def create_scaled_reader(client: ModbusTcpClient_, modbus_id: int, type: ModbusDataType):
    def scaled_reader(address: int, count: int):
        # Cache-Key für diesen Scale-Faktor
        scale_address = address + count
        cache_key = (modbus_id, scale_address)
        
        # Prüfe ob Scale-Faktor bereits im Cache
        if cache_key in _scale_factor_cache:
            scale_factor = _scale_factor_cache[cache_key]
            log.debug(f"Using cached scale factor for address {scale_address}: {scale_factor}")
            
            # Nur die Werte lesen (ohne Scale-Faktor)
            values = client.read_holding_registers(address, [type] * count, unit=modbus_id)
            
            # Scale-Faktor manuell anwenden
            scale = math.pow(10, scale_factor)
            return [value * scale if value != UINT16_UNSUPPORTED else 0 for value in values]
        else:
            # Erster Aufruf: Normale Methode mit Scale-Faktor
            result = scale_registers(
                client.read_holding_registers(address, [type] * count + [ModbusDataType.INT_16], unit=modbus_id)
            )
            
            # Scale-Faktor für nächstes Mal cachen
            # Der Scale-Faktor war das letzte Element vor scale_registers
            raw_registers = client.read_holding_registers(
                scale_address, ModbusDataType.INT_16, unit=modbus_id
            )
            _scale_factor_cache[cache_key] = raw_registers
            log.debug(f"Cached scale factor for address {scale_address}: {raw_registers}")
            
            return result

    return scaled_reader
