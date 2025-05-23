import unittest
from unittest.mock import MagicMock, patch

from pymodbus.constants import Endian
from pymodbus.exceptions import ModbusIOException

from modules.common.component_state import BatState
from modules.common.fault_state import FaultState
from modules.common.modbus import ModbusDataType, ModbusTcpClient_
from modules.common.simcount import SimCounter
from modules.common.store import SingleValueStore
from modules.devices.solaredge.solaredge.bat import SolaredgeBat, REG_BAT_POWER, REG_BAT_SOC, FLOAT32_UNSUPPORTED
from modules.devices.solaredge.solaredge.config import SolaredgeBatSetup


class TestSolaredgeBat(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=ModbusTcpClient_)
        self.config = SolaredgeBatSetup(id=0, configuration=MagicMock(modbus_id=1))
        # Patch SimCounter to avoid external dependencies in these unit tests
        self.patch_simcounter = patch('modules.common.simcount.SimCounter', spec=SimCounter)
        self.mock_simcounter_class = self.patch_simcounter.start()
        self.mock_simcounter_instance = self.mock_simcounter_class.return_value
        self.mock_simcounter_instance.sim_count.return_value = (0, 0) # Default sim_count

        self.bat = SolaredgeBat(component_config=self.config, device_id=1, client=self.mock_client)
        # Initialize components normally done by the device setup
        self.bat.store = MagicMock(spec=SingleValueStore)
        self.bat.fault_state = MagicMock(spec=FaultState)
        # Call initialize to setup internal properties if SolaredgeBat.initialize() does that
        self.bat.initialize() # This sets up sim_counter based on the patched class

    def tearDown(self):
        self.patch_simcounter.stop()

    def test_bat_read_state_success_positive_power(self):
        # SoC 95.5% -> registers (LE): [0x0000, 0x42BE]
        # Power 1500.0W -> registers (LE): [0xc000, 0x44bb]
        # Note: read_holding_registers for FLOAT32 returns a single float value after decoding.
        # The mock should return the decoded float value directly as per ModbusClient behavior for single type read.
        self.mock_client.read_holding_registers.side_effect = [
            95.5,  # SoC
            1500.0  # Power
        ]
        self.mock_simcounter_instance.sim_count.return_value = (0, 1500.0 * (1/3600)) # exported for 1 sec

        self.bat.update()

        self.mock_client.read_holding_registers.assert_any_call(
            REG_BAT_SOC, ModbusDataType.FLOAT_32, wordorder=Endian.Little, unit=1
        )
        self.mock_client.read_holding_registers.assert_any_call(
            REG_BAT_POWER, ModbusDataType.FLOAT_32, wordorder=Endian.Little, unit=1
        )

        self.bat.store.set.assert_called_once()
        args, _ = self.bat.store.set.call_args
        state: BatState = args[0]

        self.assertAlmostEqual(state.soc, 95.5)
        self.assertAlmostEqual(state.power, 1500.0)
        self.assertAlmostEqual(state.exported, 1500.0 * (1/3600))
        self.assertAlmostEqual(state.imported, 0)
        self.bat.fault_state.set_fault.assert_called_once_with(False)

    def test_bat_read_state_success_negative_power(self):
        # SoC 50.25% -> struct.pack('>f', 50.25) -> b'BHO\x00'. LE regs: [0x4f48, 0x4248] -> No, this is wrong.
        # SoC 50.25% -> use direct float
        # Power -500.0W (charging) -> use direct float
        self.mock_client.read_holding_registers.side_effect = [
            50.25, # SoC
            -500.0 # Power
        ]
        self.mock_simcounter_instance.sim_count.return_value = (abs(-500.0) * (1/3600), 0) # imported for 1 sec

        self.bat.update()
        
        self.bat.store.set.assert_called_once()
        args, _ = self.bat.store.set.call_args
        state: BatState = args[0]

        self.assertAlmostEqual(state.soc, 50.25)
        self.assertAlmostEqual(state.power, -500.0)
        self.assertAlmostEqual(state.imported, abs(-500.0) * (1/3600))
        self.assertAlmostEqual(state.exported, 0)
        self.bat.fault_state.set_fault.assert_called_once_with(False)

    def test_bat_read_state_unsupported_values(self):
        self.mock_client.read_holding_registers.side_effect = [
            FLOAT32_UNSUPPORTED,  # SoC
            FLOAT32_UNSUPPORTED   # Power
        ]
        self.mock_simcounter_instance.sim_count.return_value = (0,0)

        self.bat.update()

        self.bat.store.set.assert_called_once()
        args, _ = self.bat.store.set.call_args
        state: BatState = args[0]
        
        self.assertAlmostEqual(state.soc, 0.0)
        self.assertAlmostEqual(state.power, 0.0)
        self.bat.fault_state.set_fault.assert_called_once_with(False)


    def test_bat_read_state_modbus_error(self):
        self.mock_client.read_holding_registers.side_effect = ModbusIOException("test error")

        self.bat.update()

        self.bat.store.set.assert_not_called()
        self.bat.fault_state.set_fault.assert_called_once_with(True)


if __name__ == '__main__':
    unittest.main()
