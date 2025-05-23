import unittest
from unittest.mock import MagicMock, patch

from pymodbus.exceptions import ModbusIOException

from modules.common.component_state import InverterState
from modules.common.fault_state import FaultState
from modules.common.modbus import ModbusDataType # Only for type hinting the reader mock
from modules.common.store import SingleValueStore
from modules.devices.kostal.kostal_plenticore.inverter import KostalPlenticoreInverter
from modules.devices.kostal.kostal_plenticore.config import KostalPlenticoreInverterSetup


class TestKostalPlenticoreInverter(unittest.TestCase):
    def setUp(self):
        self.config = KostalPlenticoreInverterSetup(id=0, configuration=MagicMock())
        
        # KostalPlenticoreInverter does not take many kwargs directly for its own init
        # The 'reader' callable is passed to its read_state method.
        self.inverter = KostalPlenticoreInverter(component_config=self.config)
        
        self.inverter.store = MagicMock(spec=SingleValueStore)
        self.inverter.fault_state = MagicMock(spec=FaultState)
        
        # Mock for the 'reader' callable
        self.mock_reader = MagicMock()

    def test_read_state_success_sets_fault_false(self):
        # Configure mock_reader to return valid data
        # power = reader(575, ModbusDataType.INT_16) * -1
        # exported = reader(320, ModbusDataType.FLOAT_32)
        self.mock_reader.side_effect = [
            -1500, # for power (becomes 1500)
            12345.67 # for exported
        ]

        # Call read_state directly as it contains the logic and fault handling
        result_state = self.inverter.read_state(self.mock_reader)
        
        # Then call update with the result, as done in device.py
        self.inverter.update(result_state)


        self.assertIsNotNone(result_state)
        self.assertEqual(result_state.power, 1500.0)
        self.assertAlmostEqual(result_state.exported, 12345.67)
        
        self.inverter.store.set.assert_called_once_with(result_state)
        self.inverter.fault_state.set_fault.assert_called_once_with(False)

        # Check calls to the reader
        self.mock_reader.assert_any_call(575, ModbusDataType.INT_16)
        self.mock_reader.assert_any_call(320, ModbusDataType.FLOAT_32)

    @patch('packages.modules.devices.kostal.kostal_plenticore.inverter.log')
    def test_read_state_reader_exception_sets_fault_true(self, mock_log):
        # Configure mock_reader to raise ModbusIOException
        self.mock_reader.side_effect = ModbusIOException("Test Modbus Error from reader")

        result_state = self.inverter.read_state(self.mock_reader)
        self.inverter.update(result_state) # Update with None

        self.assertIsNone(result_state)
        self.inverter.store.set.assert_not_called() # Since state is None
        self.inverter.fault_state.set_fault.assert_called_once_with(True)
        mock_log.error.assert_called_once()

    @patch('packages.modules.devices.kostal.kostal_plenticore.inverter.log')
    def test_dc_in_string_1_2_success(self, mock_log):
        # Test auxiliary method dc_in_string_1_2 for completeness
        # val = reader(260, ModbusDataType.FLOAT_32) + reader(270, ModbusDataType.FLOAT_32)
        self.mock_reader.side_effect = [
            100.5,
            200.3
        ]
        result = self.inverter.dc_in_string_1_2(self.mock_reader)
        self.assertAlmostEqual(result, 300.8)
        mock_log.error.assert_not_called() # No error should be logged

    @patch('packages.modules.devices/kostal/kostal_plenticore/inverter.log')
    def test_dc_in_string_1_2_exception(self, mock_log):
        self.mock_reader.side_effect = ModbusIOException("DC Read Error")
        result = self.inverter.dc_in_string_1_2(self.mock_reader)
        self.assertIsNone(result)
        mock_log.error.assert_called_once() # Should log the error from reader

if __name__ == '__main__':
    unittest.main()
