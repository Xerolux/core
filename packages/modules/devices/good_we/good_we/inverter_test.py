import unittest
from unittest.mock import MagicMock, patch

from pymodbus.exceptions import ModbusIOException

from modules.common.component_state import InverterState
from modules.common.fault_state import FaultState
from modules.common.modbus import ModbusTcpClient_, ModbusDataType
from modules.common.store import SingleValueStore
from modules.devices.good_we.good_we.inverter import GoodWeInverter
from modules.devices.good_we.good_we.config import GoodWeInverterSetup
from modules.devices.good_we.good_we.version import GoodWeVersion # Assuming this is needed for setup


class TestGoodWeInverter(unittest.TestCase):
    def setUp(self):
        self.mock_tcp_client = MagicMock(spec=ModbusTcpClient_)
        
        # Basic config for GoodWeInverter
        self.config = GoodWeInverterSetup(id=0, configuration=MagicMock())

        # GoodWeInverter takes modbus_id, version, firmware, client in kwargs
        self.inverter = GoodWeInverter(
            component_config=self.config,
            modbus_id=1,
            version=GoodWeVersion.V_L_S, # Example version, adjust if necessary
            firmware=10, # Example firmware
            client=self.mock_tcp_client
        )
        
        self.inverter.store = MagicMock(spec=SingleValueStore)
        self.inverter.fault_state = MagicMock(spec=FaultState)

    def test_update_success_sets_fault_false(self):
        # power = sum of 4 x INT_32 reads, then negated
        # exported = 1 x UINT_32 read, then * 100
        self.mock_tcp_client.read_holding_registers.side_effect = [
            100, 200, 300, 400, # For power calculation (sum = 1000, power = -1000)
            5000               # For exported (exported = 500000)
        ]

        self.inverter.update()

        expected_inverter_state = InverterState(
            power=-1000.0,
            exported=500000.0 
        )

        self.inverter.store.set.assert_called_once()
        args, _ = self.inverter.store.set.call_args
        self.assertEqual(args[0].power, expected_inverter_state.power)
        self.assertEqual(args[0].exported, expected_inverter_state.exported)
        
        self.inverter.fault_state.set_fault.assert_called_once_with(False)
        
        # Check calls to read_holding_registers
        # Call for power registers
        self.mock_tcp_client.read_holding_registers.assert_any_call(35105, ModbusDataType.INT_32, unit=1)
        self.mock_tcp_client.read_holding_registers.assert_any_call(35109, ModbusDataType.INT_32, unit=1)
        self.mock_tcp_client.read_holding_registers.assert_any_call(35113, ModbusDataType.INT_32, unit=1)
        self.mock_tcp_client.read_holding_registers.assert_any_call(35117, ModbusDataType.INT_32, unit=1)
        # Call for exported register
        self.mock_tcp_client.read_holding_registers.assert_any_call(35191, ModbusDataType.UINT_32, unit=1)


    @patch('packages.modules.devices.good_we.good_we.inverter.log')
    def test_update_modbus_exception_sets_fault_true(self, mock_log):
        self.mock_tcp_client.read_holding_registers.side_effect = ModbusIOException("Test Modbus Error")

        self.inverter.update()

        self.inverter.store.set.assert_not_called()
        self.inverter.fault_state.set_fault.assert_called_once_with(True)
        mock_log.error.assert_called_once()

if __name__ == '__main__':
    unittest.main()
