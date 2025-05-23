import unittest
from unittest.mock import MagicMock, patch

from pymodbus.constants import Endian
from pymodbus.exceptions import ModbusIOException

from modules.common.component_state import InverterState
from modules.common.fault_state import FaultState
from modules.common.modbus import ModbusDataType, ModbusTcpClient_
from modules.common.simcount import SimCounter
from modules.common.store import SingleValueStore
from modules.devices.solaredge.solaredge.inverter import SolaredgeInverter
from modules.devices.solaredge.solaredge.config import SolaredgeInverterSetup


class TestSolaredgeInverter(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=ModbusTcpClient_)
        self.config = SolaredgeInverterSetup(id=0, configuration=MagicMock(modbus_id=1))

        self.patch_simcounter = patch('modules.common.simcount.SimCounter', spec=SimCounter)
        self.mock_simcounter_class = self.patch_simcounter.start()
        self.mock_simcounter_instance = self.mock_simcounter_class.return_value
        # Default behavior for sim_counter: sim_count returns (0,0)
        self.mock_simcounter_instance.sim_count.return_value = (0, 0) 

        self.inverter = SolaredgeInverter(
            component_config=self.config,
            client=self.mock_client,
            device_id=1 
        )
        self.inverter.store = MagicMock(spec=SingleValueStore)
        self.inverter.fault_state = MagicMock(spec=FaultState)
        # initialize() will be called after create_scaled_reader is patched in each test

    def tearDown(self):
        self.patch_simcounter.stop()

    @patch('modules.devices.solaredge.solaredge.scale.create_scaled_reader')
    def test_inverter_read_state_success(self, mock_create_scaled_reader):
        mock_read_int16_scaled = MagicMock()
        mock_read_uint16_scaled = MagicMock()
        mock_read_uint32_scaled = MagicMock()

        def side_effect_create_scaled_reader(client, modbus_id, type, wordorder=Endian.Big): # Default wordorder for scale.py
            if client != self.mock_client or modbus_id != self.config.configuration.modbus_id:
                raise ValueError("Mismatched client or modbus_id in create_scaled_reader mock")
            if type == ModbusDataType.INT_16:
                return mock_read_int16_scaled
            elif type == ModbusDataType.UINT_16:
                return mock_read_uint16_scaled
            elif type == ModbusDataType.UINT_32:
                self.assertEqual(wordorder, Endian.Little, "Wordorder for UINT_32 should be Little Endian")
                return mock_read_uint32_scaled
            raise ValueError(f"Unexpected ModbusDataType: {type}")

        mock_create_scaled_reader.side_effect = side_effect_create_scaled_reader
        
        # Initialize the component so it uses the patched create_scaled_reader
        self.inverter.initialize()

        # Define the return values for each scaled reader function call
        # Power: self._read_scaled_int16(REG_AC_POWER_VALUE, 1)[0] * -1
        # Let scaled value be 1415.2, then after * -1 it's -1415.2 W (Export)
        mock_read_int16_scaled.side_effect = [
            [1415.2],  # For AC Power
            [1436.8]   # For DC Power
        ]
        # Exported: self._read_scaled_uint32(REG_AC_LIFETIME_ENERGY, 1)[0]
        mock_read_uint32_scaled.return_value = [8980404.0] # Lifetime Energy
        # Currents: self._read_scaled_uint16(REG_AC_CURRENT_A, 3)
        mock_read_uint16_scaled.return_value = [6.16, 0.0, 0.0] # Currents

        # Simulate SimCounter behavior for this specific power
        # If power is 1415.2, then inverter.read_state() has power = -1415.2
        # SimCounter will be called with -1415.2
        self.mock_simcounter_instance.sim_count.return_value = (100.0, 0) # imported = 100.0, exported = 0

        self.inverter.update()

        self.inverter.store.set.assert_called_once()
        args, _ = self.inverter.store.set.call_args
        state: InverterState = args[0]

        self.assertAlmostEqual(state.power, -1415.2)
        self.assertAlmostEqual(state.exported, 8980404.0)
        self.assertEqual(len(state.currents), 3)
        self.assertAlmostEqual(state.currents[0], 6.16)
        self.assertAlmostEqual(state.currents[1], 0.0)
        self.assertAlmostEqual(state.currents[2], 0.0)
        self.assertAlmostEqual(state.dc_power, -1436.8) # dc_power = val * -1
        self.assertAlmostEqual(state.imported, 100.0) # From SimCounter mock

        self.inverter.fault_state.set_fault.assert_called_with(False)
        
        # Verify create_scaled_reader calls
        # INT16 is called for AC Power and DC Power
        # UINT32 is called for Lifetime Energy
        # UINT16 is called for Currents
        mock_create_scaled_reader.assert_any_call(self.mock_client, self.config.configuration.modbus_id, ModbusDataType.INT_16)
        mock_create_scaled_reader.assert_any_call(self.mock_client, self.config.configuration.modbus_id, ModbusDataType.UINT_16)
        mock_create_scaled_reader.assert_any_call(self.mock_client, self.config.configuration.modbus_id, ModbusDataType.UINT_32, wordorder=Endian.Little)


    @patch('modules.devices.solaredge.solaredge.scale.create_scaled_reader')
    def test_inverter_read_state_modbus_error(self, mock_create_scaled_reader):
        # Let's say the first call to _read_scaled_int16 (for AC Power) fails
        mock_read_int16_scaled = MagicMock(side_effect=ModbusIOException("test modbus error"))
        
        def side_effect_create_scaled_reader(client, modbus_id, type, wordorder=Endian.Big):
            if type == ModbusDataType.INT_16:
                return mock_read_int16_scaled
            # Other types can return a generic mock if they aren't reached
            return MagicMock()

        mock_create_scaled_reader.side_effect = side_effect_create_scaled_reader
        self.inverter.initialize()

        self.inverter.update()

        self.inverter.store.set.assert_not_called()
        self.inverter.fault_state.set_fault.assert_called_with(True)

if __name__ == '__main__':
    unittest.main()
