#!/usr/bin/env python3

from modules.common.abstract_device import AbstractBat
from modules.common.component_state import BatState
from modules.common.component_type import ComponentDescriptor
from modules.common.fault_state import ComponentInfo, FaultState
from modules.common.store import get_bat_value_store
from modules.devices.tesla.tesla.http_client import PowerwallHttpClient
from modules.devices.tesla.tesla.config import TeslaBatSetup


class TeslaBat(AbstractBat):
    def __init__(self, component_config: TeslaBatSetup) -> None:
        self.component_config = component_config

    def initialize(self) -> None:
        self.store = get_bat_value_store(self.component_config.id)
        self.fault_state = FaultState(ComponentInfo.from_component_config(self.component_config))

    def update(self, client: PowerwallHttpClient, aggregate) -> None:
        self.store.set(BatState(
            imported=aggregate["battery"]["energy_imported"],
            exported=aggregate["battery"]["energy_exported"],
            power=-aggregate["battery"]["instant_power"],
            soc=client.get_json("/api/system_status/soe")["percentage"]
        ))


component_descriptor = ComponentDescriptor(configuration_factory=TeslaBatSetup)
