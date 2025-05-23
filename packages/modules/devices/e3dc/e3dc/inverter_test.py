import unittest
from unittest.mock import MagicMock, patch

from pymodbus.exceptions import ModbusIOException # To simulate Modbus errors

from modules.common.component_state import InverterState
from modules.common.fault_state import FaultState
from modules.common.store import SingleValueStore
from modules.devices.e3dc.e3dc.inverter import E3dcInverter, read_inverter # Import the helper
from modules.devices.e3dc.e3dc.config import E3dcInverterSetup


class TestE3dcInverter(unittest.TestCase):
    def setUp(self):
        self.mock_tcp_client = MagicMock() # Not directly used if helper is patched, but good for consistency
        
        self.config = E3dcInverterSetup(id=0, configuration=MagicMock())

        # E3dcInverter takes device_id, modbus_id, client in kwargs
        self.inverter = E3dcInverter(
            component_config=self.config,
            device_id=1,
            modbus_id=1, # Passed to read_inverter helper
            client=self.mock_tcp_client # Passed to read_inverter helper
        )
        
        self.inverter.store = MagicMock(spec=SingleValueStore)
        self.inverter.fault_state = MagicMock(spec=FaultState)
        
        # SimCounter is used in update after the read
        self.patch_simcounter = patch('modules.common.simcount.SimCounter')
        self.mock_simcounter_class = self.patch_simcounter.start()
        self.mock_simcounter_instance = self.mock_simcounter_class.return_value
        self.mock_simcounter_instance.sim_count.return_value = (0, 500.0) # imported, exported

    def tearDown(self):
        self.patch_simcounter.stop()

    @patch('modules.devices.e3dc.e3dc.inverter.read_inverter') # Patch the helper function
    def test_update_success_sets_fault_false(self, mock_read_inverter_helper):
        # Configure the mock helper to return a valid power value
        mock_read_inverter_helper.return_value = 1500 # Example PV power

        self.inverter.update()

        expected_inverter_state = InverterState(
            power=1500,
            exported=500.0 # from SimCounter mock
        )

        self.inverter.store.set.assert_called_once()
        args, _ = self.inverter.store.set.call_args
        self.assertEqual(args[0].power, expected_inverter_state.power)
        self.assertEqual(args[0].exported, expected_inverter_state.exported)
        
        self.inverter.fault_state.set_fault.assert_called_once_with(False)
        mock_read_inverter_helper.assert_called_once_with(self.inverter.client, self.inverter._E3dcInverter__modbus_id)


    @patch('modules.devices.e3dc.e3dc.inverter.read_inverter') # Patch the helper
    @patch('modules.devices.e3dc.e3dc.inverter.log') # Patch log for error assertion
    def test_update_read_inverter_exception_sets_fault_true(self, mock_log, mock_read_inverter_helper):
        # Configure the mock helper to raise an exception
        mock_read_inverter_helper.side_effect = ModbusIOException("Test Modbus Error from helper")

        self.inverter.update()

        self.inverter.store.set.assert_not_called()
        self.inverter.fault_state.set_fault.assert_called_once_with(True)
        mock_log.error.assert_called_once()

if __name__ == '__main__':
    unittest.main()
