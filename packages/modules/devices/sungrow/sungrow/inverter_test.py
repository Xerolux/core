import unittest
from unittest.mock import MagicMock, patch

from pymodbus.exceptions import ModbusIOException

from modules.common.component_state import InverterState
from modules.common.fault_state import FaultState
from modules.common.modbus import ModbusTcpClient_, ModbusDataType, Endian
from modules.common.simcount import SimCounter
from modules.common.store import SingleValueStore
from modules.devices.sungrow.sungrow.inverter import SungrowInverter
from modules.devices.sungrow.sungrow.config import SungrowInverterSetup, Sungrow # For device_config
from modules.devices.sungrow.sungrow.version import Version # For version logic


class TestSungrowInverter(unittest.TestCase):
    def setUp(self):
        self.mock_tcp_client = MagicMock(spec=ModbusTcpClient_)
        
        # Mock the device_config (instance of Sungrow) expected in kwargs
        self.mock_device_config_instance = MagicMock(spec=Sungrow)
        self.mock_device_config_instance.id = 1 # Simulating device_config.id for SimCounter
        self.mock_device_config_instance.configuration = MagicMock()
        self.mock_device_config_instance.configuration.modbus_id = 1
        # Default to a non-SH version for simpler test path initially
        self.mock_device_config_instance.configuration.version = Version.SG_CX 

        self.component_config = SungrowInverterSetup(id=0, configuration=MagicMock())
        
        self.patch_simcounter = patch('modules.common.simcount.SimCounter', spec=SimCounter)
        self.mock_simcounter_class = self.patch_simcounter.start()
        self.mock_simcounter_instance = self.mock_simcounter_class.return_value
        self.mock_simcounter_instance.sim_count.return_value = (0, 1234.0) # imported, exported

        self.inverter = SungrowInverter(
            component_config=self.component_config,
            client=self.mock_tcp_client,
            device_config=self.mock_device_config_instance 
        )
        
        self.inverter.store = MagicMock(spec=SingleValueStore)
        self.inverter.fault_state = MagicMock(spec=FaultState)

    def tearDown(self):
        self.patch_simcounter.stop()

    def test_update_success_non_sh_version_sets_fault_false(self):
        # For non-SH version:
        # power = read_input_registers(5030, INT_32, LE) * -1
        # dc_power = read_input_registers(5016, UINT_32, LE) * -1
        self.mock_tcp_client.read_input_registers.side_effect = [
            2000, # power (becomes -2000)
            2100  # dc_power (becomes -2100)
        ]
        self.mock_simcounter_instance.sim_count.return_value = (0, 2000.0) # exported based on power

        returned_power = self.inverter.update()

        self.assertEqual(returned_power, -2000.0)
        expected_inverter_state = InverterState(
            power=-2000.0,
            dc_power=-2100.0,
            exported=2000.0 
        )

        self.inverter.store.set.assert_called_once()
        args, _ = self.inverter.store.set.call_args
        self.assertEqual(args[0].power, expected_inverter_state.power)
        self.assertEqual(args[0].dc_power, expected_inverter_state.dc_power)
        self.assertEqual(args[0].exported, expected_inverter_state.exported)
        
        self.inverter.fault_state.set_fault.assert_called_once_with(False)
        
        # Check calls to read_input_registers
        self.mock_tcp_client.read_input_registers.assert_any_call(5030, ModbusDataType.INT_32, wordorder=Endian.Little, unit=1)
        self.mock_tcp_client.read_input_registers.assert_any_call(5016, ModbusDataType.UINT_32, wordorder=Endian.Little, unit=1)

    def test_update_success_sh_version_sets_fault_false(self):
        # Change version to SH for this test
        self.inverter.device_config.configuration.version = Version.SH

        # For SH version:
        # power = read_input_registers(13033, INT_32, LE) * -1
        # dc_power = read_input_registers(5016, UINT_32, LE) * -1
        self.mock_tcp_client.read_input_registers.side_effect = [
            1500, # power (becomes -1500)
            1600  # dc_power (becomes -1600)
        ]
        self.mock_simcounter_instance.sim_count.return_value = (0, 1500.0)

        returned_power = self.inverter.update()

        self.assertEqual(returned_power, -1500.0)
        expected_inverter_state = InverterState(
            power=-1500.0,
            dc_power=-1600.0,
            exported=1500.0
        )
        self.inverter.store.set.assert_called_once_with(expected_inverter_state)
        self.inverter.fault_state.set_fault.assert_called_once_with(False)
        self.mock_tcp_client.read_input_registers.assert_any_call(13033, ModbusDataType.INT_32, wordorder=Endian.Little, unit=1)
        self.mock_tcp_client.read_input_registers.assert_any_call(5016, ModbusDataType.UINT_32, wordorder=Endian.Little, unit=1)


    @patch('packages.modules.devices.sungrow.sungrow.inverter.log')
    def test_update_modbus_exception_sets_fault_true(self, mock_log):
        self.mock_tcp_client.read_input_registers.side_effect = ModbusIOException("Test Modbus Error")

        returned_power = self.inverter.update()
        
        self.assertEqual(returned_power, 0.0) # Default power defined in update try-block
        self.inverter.store.set.assert_not_called()
        self.inverter.fault_state.set_fault.assert_called_once_with(True)
        mock_log.error.assert_called_once()

if __name__ == '__main__':
    unittest.main()
