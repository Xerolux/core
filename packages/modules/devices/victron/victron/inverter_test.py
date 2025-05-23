import unittest
from unittest.mock import MagicMock, patch

from pymodbus.exceptions import ModbusIOException

from modules.common.component_state import InverterState
from modules.common.fault_state import FaultState
from modules.common.modbus import ModbusTcpClient_, ModbusDataType
from modules.common.simcount import SimCounter
from modules.common.store import SingleValueStore
from modules.devices.victron.victron.inverter import VictronInverter
from modules.devices.victron.victron.config import VictronInverterSetup


class TestVictronInverter(unittest.TestCase):
    def setUp(self):
        self.mock_tcp_client = MagicMock(spec=ModbusTcpClient_)
        
        # Mock the component_config and its nested configuration
        self.mock_component_configuration = MagicMock()
        self.mock_component_configuration.modbus_id = 1
        self.mock_component_configuration.mppt = False # Default to non-MPPT for basic tests

        self.config = VictronInverterSetup(id=0, configuration=self.mock_component_configuration)
        
        self.patch_simcounter = patch('modules.common.simcount.SimCounter', spec=SimCounter)
        self.mock_simcounter_class = self.patch_simcounter.start()
        self.mock_simcounter_instance = self.mock_simcounter_class.return_value
        self.mock_simcounter_instance.sim_count.return_value = (0, 200.0) # Default: imported, exported

        self.inverter = VictronInverter(
            component_config=self.config,
            device_id=1,
            client=self.mock_tcp_client
        )
        
        self.inverter.store = MagicMock(spec=SingleValueStore)
        self.inverter.fault_state = MagicMock(spec=FaultState)

    def tearDown(self):
        self.patch_simcounter.stop()

    def test_update_success_non_mppt_sets_fault_false(self):
        self.mock_component_configuration.mppt = False
        # power_temp1 = read_holding_registers(808, [UINT_16]*6, unit=100)
        # power_temp2 = read_holding_registers(850, UINT_16, unit=100)
        # power = (sum(power_temp1)+power_temp2) * -1
        self.mock_tcp_client.read_holding_registers.side_effect = [
            [10, 20, 30, 40, 50, 60], # sum = 210
            90                         # total = 210 + 90 = 300. power = -300
        ]
        self.mock_simcounter_instance.sim_count.return_value = (0, 300.0) # exported = 300.0

        self.inverter.update()

        expected_inverter_state = InverterState(power=-300.0, exported=300.0)
        self.inverter.store.set.assert_called_once()
        args, _ = self.inverter.store.set.call_args
        self.assertEqual(args[0].power, expected_inverter_state.power)
        self.assertEqual(args[0].exported, expected_inverter_state.exported)
        
        self.inverter.fault_state.set_fault.assert_called_once_with(False)

    def test_update_success_mppt_sets_fault_false(self):
        self.mock_component_configuration.mppt = True
        # power = read_holding_registers(789, UINT_16, unit=modbus_id) / -10
        self.mock_tcp_client.read_holding_registers.return_value = 2000 # power = 2000 / -10 = -200
        self.mock_simcounter_instance.sim_count.return_value = (0, 200.0)

        self.inverter.update()

        expected_inverter_state = InverterState(power=-200.0, exported=200.0)
        self.inverter.store.set.assert_called_once()
        args, _ = self.inverter.store.set.call_args
        self.assertEqual(args[0].power, expected_inverter_state.power)
        self.assertEqual(args[0].exported, expected_inverter_state.exported)

        self.inverter.fault_state.set_fault.assert_called_once_with(False)

    @patch('packages.modules.devices.victron.victron.inverter.log')
    def test_update_modbus_exception_non_mppt_sets_fault_true(self, mock_log):
        self.mock_component_configuration.mppt = False
        self.mock_tcp_client.read_holding_registers.side_effect = ModbusIOException("Test Modbus Error")

        self.inverter.update()

        self.inverter.store.set.assert_not_called() # Or called with default power=0 if error is in sim_count
        self.inverter.fault_state.set_fault.assert_called_once_with(True)
        mock_log.error.assert_called_once()

    @patch('packages.modules.devices.victron.victron.inverter.log')
    def test_update_modbus_exception_mppt_raise_sets_fault_true(self, mock_log):
        self.mock_component_configuration.mppt = True
        # Test when the exception is NOT "GatewayPathUnavailable"
        self.mock_tcp_client.read_holding_registers.side_effect = ModbusIOException("Another Modbus Error")

        self.inverter.update()
        
        self.inverter.store.set.assert_not_called() # Or called with default power=0
        self.inverter.fault_state.set_fault.assert_called_once_with(True)
        mock_log.error.assert_called_once()


    @patch('packages.modules.devices.victron.victron.inverter.log')
    def test_update_gateway_path_unavailable_handled_sets_fault_false(self, mock_log):
        self.mock_component_configuration.mppt = True
        # Configure mock_tcp_client to raise specific exception for GatewayPathUnavailable
        self.mock_tcp_client.read_holding_registers.side_effect = Exception("Modbus Error: GatewayPathUnavailable")
        self.mock_simcounter_instance.sim_count.return_value = (0, 0.0) # Since power will be 0

        self.inverter.update()

        # Power should be 0 due to handled exception
        expected_inverter_state = InverterState(power=0.0, exported=0.0)
        self.inverter.store.set.assert_called_once()
        args, _ = self.inverter.store.set.call_args
        self.assertEqual(args[0].power, expected_inverter_state.power)
        self.assertEqual(args[0].exported, expected_inverter_state.exported)

        self.inverter.fault_state.set_fault.assert_called_once_with(False) # Because this specific error is handled
        mock_log.debug.assert_called() # Check if the debug log for this case was called

if __name__ == '__main__':
    unittest.main()
