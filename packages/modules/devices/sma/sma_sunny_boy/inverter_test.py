import unittest
from unittest.mock import MagicMock, patch

from pymodbus.exceptions import ModbusIOException

from modules.common.component_state import InverterState
from modules.common.fault_state import FaultState
from modules.common.modbus import ModbusTcpClient_, ModbusDataType
from modules.common.simcount import SimCounter
from modules.common.store import SingleValueStore
from modules.devices.sma.sma_sunny_boy.inverter import SmaSunnyBoyInverter
from modules.devices.sma.sma_sunny_boy.config import SmaSunnyBoyInverterSetup
from modules.devices.sma.sma_sunny_boy.inv_version import SmaInverterVersion # Required for version logic


class TestSmaSunnyBoyInverter(unittest.TestCase):
    def setUp(self):
        self.mock_tcp_client = MagicMock(spec=ModbusTcpClient_)
        
        self.mock_component_configuration = MagicMock()
        self.mock_component_configuration.modbus_id = 1
        # Default to a version for testing, e.g., SmaInverterVersion.default
        self.mock_component_configuration.version = SmaInverterVersion.default

        self.config = SmaSunnyBoyInverterSetup(id=0, configuration=self.mock_component_configuration)
        
        self.patch_simcounter = patch('modules.common.simcount.SimCounter', spec=SimCounter)
        self.mock_simcounter_class = self.patch_simcounter.start()
        self.mock_simcounter_instance = self.mock_simcounter_class.return_value
        self.mock_simcounter_instance.sim_count.return_value = (10.0, 0) # imported, exported

        self.inverter = SmaSunnyBoyInverter(
            component_config=self.config,
            client=self.mock_tcp_client,
            device_id=1 
        )
        
        self.inverter.store = MagicMock(spec=SingleValueStore)
        self.inverter.fault_state = MagicMock(spec=FaultState)

    def tearDown(self):
        self.patch_simcounter.stop()

    def test_update_calls_read_success_sets_fault_false(self):
        # Using SmaInverterVersion.default path in read()
        # power_total = read(30775, INT_32)
        # energy = read(30529, UINT_32)
        # dc_power = read(30773, INT_32) + read(30961, INT_32)
        self.mock_tcp_client.read_holding_registers.side_effect = [
            2000,  # power_total (becomes -2000 in state)
            50000, # energy
            1000,  # dc_power part 1
            1100   # dc_power part 2 (dc_power = 2100, becomes -2100 in state)
        ]
        self.mock_simcounter_instance.sim_count.return_value = (10.0, 0) # imported, exported based on power_total * -1 = -2000

        self.inverter.update()

        expected_inverter_state = InverterState(
            power=-2000.0,
            dc_power=-2100.0,
            exported=50000,
            imported=10.0
        )

        self.inverter.store.set.assert_called_once()
        args, _ = self.inverter.store.set.call_args
        state_out: InverterState = args[0]
        self.assertEqual(state_out.power, expected_inverter_state.power)
        self.assertEqual(state_out.dc_power, expected_inverter_state.dc_power)
        self.assertEqual(state_out.exported, expected_inverter_state.exported)
        self.assertEqual(state_out.imported, expected_inverter_state.imported)
        
        self.inverter.fault_state.set_fault.assert_called_once_with(False)
        
        # Check calls
        self.mock_tcp_client.read_holding_registers.assert_any_call(30775, ModbusDataType.INT_32, unit=1)
        self.mock_tcp_client.read_holding_registers.assert_any_call(30529, ModbusDataType.UINT_32, unit=1)
        self.mock_tcp_client.read_holding_registers.assert_any_call(30773, ModbusDataType.INT_32, unit=1)
        self.mock_tcp_client.read_holding_registers.assert_any_call(30961, ModbusDataType.INT_32, unit=1)


    @patch('packages.modules.devices.sma.sma_sunny_boy.inverter.log')
    def test_update_calls_read_exception_sets_fault_true(self, mock_log):
        # Simulate an exception during the first Modbus read call within inverter.read()
        self.mock_tcp_client.read_holding_registers.side_effect = ModbusIOException("Test Modbus Error")

        self.inverter.update()

        self.inverter.store.set.assert_not_called()
        self.inverter.fault_state.set_fault.assert_called_once_with(True)
        mock_log.error.assert_called_once()

    @patch('packages.modules.devices.sma.sma_sunny_boy.inverter.log')
    def test_read_value_error_for_nan_energy_sets_fault_true(self, mock_log):
        # Test the ValueError path for NAN energy value
        self.mock_component_configuration.version = SmaInverterVersion.default
        self.mock_tcp_client.read_holding_registers.side_effect = [
            2000,  # power_total
            SmaSunnyBoyInverter.SMA_UINT32_NAN, # energy - this should cause ValueError
            1000,  # dc_power part 1
            1100   # dc_power part 2
        ]
        
        self.inverter.update() # update calls read, which will raise ValueError

        self.inverter.store.set.assert_not_called()
        self.inverter.fault_state.set_fault.assert_called_once_with(True)
        mock_log.error.assert_called_once() # Error logged by update() method's try-except

if __name__ == '__main__':
    unittest.main()
