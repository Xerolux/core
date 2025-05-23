import unittest
from unittest.mock import MagicMock, patch

from pymodbus.constants import Endian
from pymodbus.exceptions import ModbusIOException

from modules.common.component_state import CounterState
from modules.common.fault_state import FaultState
from modules.common.modbus import ModbusDataType, ModbusTcpClient_
from modules.common.store import SingleValueStore
from modules.devices.solaredge.solaredge.counter import SolaredgeCounter
from modules.devices.solaredge.solaredge.config import SolaredgeCounterSetup, SolaredgeCounterConfiguration
from modules.devices.solaredge.solaredge.meter import SolaredgeMeterRegisters


class TestSolaredgeCounter(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=ModbusTcpClient_)
        self.config = SolaredgeCounterSetup(
            id=0, 
            configuration=SolaredgeCounterConfiguration(modbus_id=1, meter_id=1)
        )

        # Mocking dependencies that are normally set up by the device or higher-level components
        self.patch_set_component_registers = patch('modules.devices.solaredge.solaredge.counter.set_component_registers')
        self.mock_set_component_registers = self.patch_set_component_registers.start()

        # Mock the SolaredgeMeterRegisters instance
        self.mock_meter_registers = MagicMock(spec=SolaredgeMeterRegisters)
        self.mock_meter_registers.powers = 40206
        self.mock_meter_registers.currents = 40191
        self.mock_meter_registers.voltages = 40196
        self.mock_meter_registers.frequency = 40204
        self.mock_meter_registers.power_factors = 40222
        self.mock_meter_registers.imp_exp = 40226

        self.patch_meter_registers_init = patch('modules.devices.solaredge.solaredge.counter.SolaredgeMeterRegisters', return_value=self.mock_meter_registers)
        self.mock_meter_registers_class = self.patch_meter_registers_init.start()


        self.counter = SolaredgeCounter(
            component_config=self.config, 
            client=self.mock_client, 
            components={} # Assuming components dict might be used by set_component_registers
        )
        
        # Manually set store and fault_state as they are typically handled by AbstractDevice/ConfigurableDevice
        self.counter.store = MagicMock(spec=SingleValueStore)
        self.counter.fault_state = MagicMock(spec=FaultState)
        
        # Call initialize after patching is complete
        self.counter.initialize()

    def tearDown(self):
        self.patch_set_component_registers.stop()
        self.patch_meter_registers_init.stop()

    @patch('modules.devices.solaredge.solaredge.scale.create_scaled_reader')
    def test_counter_read_state_success(self, mock_create_scaled_reader):
        # Mock the return values of the scaled reader functions
        mock_read_int16_scaled = MagicMock()
        mock_read_uint32_scaled = MagicMock()

        def side_effect_create_scaled_reader(client, modbus_id, type, wordorder=None):
            if type == ModbusDataType.INT_16:
                return mock_read_int16_scaled
            elif type == ModbusDataType.UINT_32:
                # Ensure wordorder is passed correctly for UINT_32
                self.assertEqual(wordorder, Endian.Little)
                return mock_read_uint32_scaled
            raise ValueError("Unexpected ModbusDataType")

        mock_create_scaled_reader.side_effect = side_effect_create_scaled_reader
        
        # Re-initialize to make sure the patched create_scaled_reader is used
        self.counter.initialize()


        # Expected scaled values (after scale_registers would have run)
        # For _read_scaled_int16(self.registers.powers, 4) -> [Total, PhA, PhB, PhC]
        # Let Total Power = 1000.0 W (Import), PhA=300W, PhB=300W, PhC=400W
        # The counter code negates these: `powers = [-power for power in scaled_results]`
        # So, to get positive power for import in CounterState, provide negative values here.
        # This seems counter-intuitive based on typical conventions (import positive).
        # Let's assume the test values from inverter_test: power = val * -1.
        # If scaled reader returns 1000.0, then powers_list becomes -1000.0.
        # So CounterState.power = -1000.0 (Exporting).
        # If scaled reader returns -1000.0, then powers_list becomes 1000.0
        # So CounterState.power = 1000.0 (Importing). This matches typical convention.

        # Data from scaled readers:
        mock_read_int16_scaled.side_effect = [
            [-1000.0, -300.0, -300.0, -400.0],  # Powers (Total, A, B, C)
            [5.0, 5.1, 5.2],                    # Currents
            [230.0, 230.1, 230.2],              # Voltages (reads 7, takes 3)
            [50.0],                             # Frequency
            [99, 98, 97]                        # Power Factors (scaled to 0.xx later)
        ]
        # For _read_scaled_uint32(self.registers.imp_exp, 8)
        # [ExpTotal, ExpA, ExpB, ExpC, ImpTotal, ImpA, ImpB, ImpC]
        mock_read_uint32_scaled.return_value = [
            12345678.0, 0, 0, 0,  # Exported total & phases
            87654321.0, 0, 0, 0   # Imported total & phases
        ]

        self.counter.update()

        self.counter.store.set.assert_called_once()
        args, _ = self.counter.store.set.call_args
        state: CounterState = args[0]

        self.assertAlmostEqual(state.power, 1000.0) # -(-1000.0)
        self.assertEqual(len(state.powers), 3)
        self.assertAlmostEqual(state.powers[0], 300.0) # -(-300.0)
        self.assertAlmostEqual(state.currents[0], 5.0)
        self.assertAlmostEqual(state.voltages[0], 230.0)
        self.assertAlmostEqual(state.frequency, 50.0)
        self.assertAlmostEqual(state.power_factors[0], 0.99)
        self.assertAlmostEqual(state.exported, 12345678.0)
        self.assertAlmostEqual(state.imported, 87654321.0)
        
        self.counter.fault_state.set_fault.assert_called_with(False)

    @patch('modules.devices.solaredge.solaredge.scale.create_scaled_reader')
    def test_counter_read_state_modbus_error(self, mock_create_scaled_reader):
        mock_read_int16_scaled = MagicMock(side_effect=ModbusIOException("test error"))
        mock_read_uint32_scaled = MagicMock() # Not called if first one fails

        def side_effect_create_scaled_reader(client, modbus_id, type, wordorder=None):
            if type == ModbusDataType.INT_16:
                return mock_read_int16_scaled
            elif type == ModbusDataType.UINT_32:
                return mock_read_uint32_scaled
            raise ValueError("Unexpected ModbusDataType")

        mock_create_scaled_reader.side_effect = side_effect_create_scaled_reader
        self.counter.initialize() # Re-initialize with new mocks

        self.counter.update()

        self.counter.store.set.assert_not_called()
        self.counter.fault_state.set_fault.assert_called_with(True)

if __name__ == '__main__':
    unittest.main()
