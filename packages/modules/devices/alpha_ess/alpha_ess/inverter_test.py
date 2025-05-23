import unittest
from unittest.mock import MagicMock, patch

from pymodbus.exceptions import ModbusIOException

from modules.common.component_state import InverterState
from modules.common.fault_state import FaultState
from modules.common.modbus import ModbusTcpClient_, ModbusDataType
from modules.common.simcount import SimCounter
from modules.common.store import SingleValueStore
from modules.devices.alpha_ess.alpha_ess.inverter import AlphaEssInverter
from modules.devices.alpha_ess.alpha_ess.config import AlphaEssInverterSetup, AlphaEssConfiguration


class TestAlphaEssInverter(unittest.TestCase):
    def setUp(self):
        self.mock_tcp_client = MagicMock(spec=ModbusTcpClient_)
        
        # Mock the device_config that is expected in kwargs
        self.mock_device_config = MagicMock(spec=AlphaEssConfiguration)
        self.mock_device_config.source = 0 # Example values
        self.mock_device_config.version = 0

        self.config = AlphaEssInverterSetup(id=0, configuration=MagicMock())
        
        # Patch SimCounter
        self.patch_simcounter = patch('modules.common.simcount.SimCounter', spec=SimCounter)
        self.mock_simcounter_class = self.patch_simcounter.start()
        self.mock_simcounter_instance = self.mock_simcounter_class.return_value
        self.mock_simcounter_instance.sim_count.return_value = (0, 123.0) # Default sim_count: imported, exported

        self.inverter = AlphaEssInverter(
            component_config=self.config,
            device_id=1,
            tcp_client=self.mock_tcp_client,
            device_config=self.mock_device_config, # Pass the mocked device_config
            modbus_id=1
        )
        
        # Manually set store and fault_state as they are usually set by AbstractDevice or higher classes
        self.inverter.store = MagicMock(spec=SingleValueStore)
        # Replace the actual FaultState instance with a mock
        self.inverter.fault_state = MagicMock(spec=FaultState)
        
        # Call initialize to set up internal properties
        # No, initialize is called by the ConfigurableDevice, let's assume it's called
        # self.inverter.initialize() -> This is not typically called directly in unit tests of components
        # if they are instantiated directly. However, if it sets up critical things that update() depends on,
        # it might be needed, or those things mocked. Here, it sets up fault_state which we are mocking.
        # Let's ensure __tcp_client, __modbus_id etc. are set if initialize() does that.
        # Based on inverter.py, initialize() sets these from kwargs, which we provide.
        # So, direct call to initialize() for the purpose of this test setup might not be strictly needed
        # as long as the kwargs are correctly passed and self.fault_state is mocked.


    def tearDown(self):
        self.patch_simcounter.stop()

    def test_update_success_sets_fault_false(self):
        # Configure mock_tcp_client to return valid data for power registers
        # The __get_power method reads 4 INT_32 registers
        self.mock_tcp_client.read_holding_registers.side_effect = [
            1000, # reg_p (0x0012)
            200,  # 0x041F
            300,  # 0x0423
            400   # 0x0427
        ] # These are raw values before abs() or sum() * -1

        self.inverter.update()

        # Expected power: abs(1000) + 200 + 300 + 400 = 1900 -> sum * -1 = -1900
        # Expected state
        expected_inverter_state = InverterState(
            power=-1900.0,
            exported=123.0  # from SimCounter mock
        )

        self.inverter.store.set.assert_called_once()
        args, _ = self.inverter.store.set.call_args
        # Deep compare relevant fields if InverterState instances are complex
        self.assertEqual(args[0].power, expected_inverter_state.power)
        self.assertEqual(args[0].exported, expected_inverter_state.exported)
        
        self.inverter.fault_state.set_fault.assert_called_once_with(False)

    @patch('modules.devices.alpha_ess.alpha_ess.inverter.log') # Patching log for error log assertion
    def test_update_modbus_exception_sets_fault_true(self, mock_log):
        # Configure mock_tcp_client to raise ModbusIOException
        self.mock_tcp_client.read_holding_registers.side_effect = ModbusIOException("Test Modbus Error")

        self.inverter.update()

        self.inverter.store.set.assert_not_called()
        self.inverter.fault_state.set_fault.assert_called_once_with(True)
        mock_log.error.assert_called_once()


if __name__ == '__main__':
    unittest.main()
