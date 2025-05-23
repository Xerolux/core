import logging
import math
from typing import List

from pymodbus.constants import Endian

from modules.common.modbus import ModbusDataType, ModbusTcpClient_, Number

log = logging.getLogger(__name__)

# Registers that are not applicable to a meter class return the unsupported value. (e.g. Single Phase
# meters will support only summary and phase A values):

UINT16_UNSUPPORTED = 0xFFFF


def scale_registers(registers: List[Number]) -> List[float]:
    log.debug("Raw registers before scaling: %s, Scale factor register: %s", registers[:-1],  registers[-1])
    # The last register in the list is the scale factor.
    # It's an int16, so ensure it's handled correctly if it could be negative.
    # math.pow(10, scale_factor_value)
    scale_factor_value = registers[-1]
    if not isinstance(scale_factor_value, int): # Or check if it's a specific Modbus Number type that can be negative
        # Potentially log a warning if scale factor isn't as expected, though ModbusDataType.INT_16 should ensure it's an int.
        pass

    scale = math.pow(10, scale_factor_value)
    
    scaled_values = []
    for register_val in registers[:-1]:
        if register_val == UINT16_UNSUPPORTED:
            log.debug("Encountered UINT16_UNSUPPORTED value (0x%X), replacing with 0.", UINT16_UNSUPPORTED)
            scaled_values.append(0.0)
        else:
            scaled_values.append(float(register_val) * scale)
    log.debug("Scaled values: %s", scaled_values)
    return scaled_values


def create_scaled_reader(client: ModbusTcpClient_, modbus_id: int, type: ModbusDataType, wordorder: Endian = Endian.Big):
    def scaled_reader(address: int, count: int):
        return scale_registers(
            client.read_holding_registers(address, [type] * count + [ModbusDataType.INT_16], unit=modbus_id, wordorder=wordorder)
        )

    return scaled_reader
