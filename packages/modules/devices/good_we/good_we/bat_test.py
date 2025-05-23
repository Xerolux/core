import unittest
from unittest.mock import MagicMock, patch

from pymodbus.exceptions import ModbusIOException

from modules.common.component_state import BatState
from modules.common.fault_state import FaultState
from modules.common.modbus import ModbusTcpClient_, ModbusDataType
from modules.common.store import SingleValueStore
from modules.devices.good_we.good_we.bat import GoodWeBat
from modules.devices.good_we.good_we.config import GoodWeBatSetup
from modules.devices.good_we.good_we.version import GoodWeVersion # Required for version logic


class TestGoodWeBat(unittest.TestCase):
    def setUp(self):
        self.mock_tcp_client = MagicMock(spec=ModbusTcpClient_)
        
        self.config = GoodWeBatSetup(id=0, configuration=MagicMock())

        # GoodWeBat takes modbus_id, version, firmware, client in kwargs
        self.bat = GoodWeBat(
            component_config=self.config,
            modbus_id=1,
            version=GoodWeVersion.V_L_S, # Example version, for INT_32 power read
            firmware=10, 
            client=self.mock_tcp_client
        )
        
        self.bat.store = MagicMock(spec=SingleValueStore)
        self.bat.fault_state = MagicMock(spec=FaultState)

    def test_update_success_sets_fault_false(self):
        # Based on version=GoodWeVersion.V_L_S:
        # power = INT_32 read (reg 35182), negated
        # soc = UINT_16 read (reg 37007)
        # imported = UINT_32 read (reg 35206), * 100
        # exported = UINT_32 read (reg 35209), * 100
        self.mock_tcp_client.read_holding_registers.side_effect = [
            1000,  # Power (becomes -1000)
            80,    # SoC
            50,    # Imported (becomes 5000)
            20     # Exported (becomes 2000)
        ]

        self.bat.update()

        expected_bat_state = BatState(
            power=-1000.0,
            soc=80,
            imported=5000.0,
            exported=2000.0
        )

        self.bat.store.set.assert_called_once()
        args, _ = self.bat.store.set.call_args
        state_out: BatState = args[0]
        self.assertEqual(state_out.power, expected_bat_state.power)
        self.assertEqual(state_out.soc, expected_bat_state.soc)
        self.assertEqual(state_out.imported, expected_bat_state.imported)
        self.assertEqual(state_out.exported, expected_bat_state.exported)
        
        self.bat.fault_state.set_fault.assert_called_once_with(False)
        
        # Check mock calls
        self.mock_tcp_client.read_holding_registers.assert_any_call(35182, ModbusDataType.INT_32, unit=1)
        self.mock_tcp_client.read_holding_registers.assert_any_call(37007, ModbusDataType.UINT_16, unit=1)
        self.mock_tcp_client.read_holding_registers.assert_any_call(35206, ModbusDataType.UINT_32, unit=1)
        self.mock_tcp_client.read_holding_registers.assert_any_call(35209, ModbusDataType.UINT_32, unit=1)


    @patch('packages.modules.devices.good_we.good_we.bat.log')
    def test_update_modbus_exception_sets_fault_true(self, mock_log):
        self.mock_tcp_client.read_holding_registers.side_effect = ModbusIOException("Test Modbus Error")

        self.bat.update()

        self.bat.store.set.assert_not_called()
        self.bat.fault_state.set_fault.assert_called_once_with(True)
        mock_log.error.assert_called_once()

    def test_update_success_v1_7_version(self):
        # Test for GoodWeVersion.V_1_7 where power is INT_16
        self.bat.version = GoodWeVersion.V_1_7 
        
        self.mock_tcp_client.read_holding_registers.side_effect = [
            -500,  # Power (INT_16, becomes 500 then negated by simcount? No, power is used as is after initial negation)
                   # The code is: power = self.__tcp_client.read_holding_registers(...) * -1
                   # So if register returns -500, power becomes 500.
            75,    # SoC
            40,    # Imported (becomes 4000)
            10     # Exported (becomes 1000)
        ]

        self.bat.update()
        
        expected_bat_state = BatState(
            power=500.0, # -(-500)
            soc=75,
            imported=4000.0,
            exported=1000.0
        )
        self.bat.store.set.assert_called_once()
        args, _ = self.bat.store.set.call_args
        state_out: BatState = args[0]

        self.assertEqual(state_out.power, expected_bat_state.power)
        
        self.bat.fault_state.set_fault.assert_called_once_with(False)
        self.mock_tcp_client.read_holding_registers.assert_any_call(35183, ModbusDataType.INT_16, unit=1)


if __name__ == '__main__':
    unittest.main()
