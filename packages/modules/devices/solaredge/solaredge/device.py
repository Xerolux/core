#!/usr/bin/env python3
import logging
from typing import Iterable, Union

from modules.common import modbus
from modules.common.abstract_device import DeviceDescriptor
from modules.common.configurable_device import ComponentFactoryByType, ConfigurableDevice, MultiComponentUpdater
from modules.devices.solaredge.solaredge.bat import SolaredgeBat
from modules.devices.solaredge.solaredge.counter import SolaredgeCounter
from modules.devices.solaredge.solaredge.external_inverter import SolaredgeExternalInverter
from modules.devices.solaredge.solaredge.inverter import SolaredgeInverter
from modules.devices.solaredge.solaredge.config import (Solaredge, SolaredgeBatSetup, SolaredgeCounterSetup,
                                                        SolaredgeExternalInverterSetup, SolaredgeInverterSetup)

log = logging.getLogger(__name__)


reconnect_delay = 1.2


def create_device(device_config: Solaredge):
    client = None

    def create_bat_component(component_config: SolaredgeBatSetup):
        nonlocal client
        return SolaredgeBat(component_config, device_id=device_config.id, client=client)

    def create_counter_component(component_config: SolaredgeCounterSetup):
        nonlocal client, device
        return SolaredgeCounter(component_config, client=client, components=device.components)

    def create_inverter_component(component_config: SolaredgeInverterSetup):
        nonlocal client
        return SolaredgeInverter(component_config, client=client, device_id=device_config.id)

    def create_external_inverter_component(component_config: SolaredgeExternalInverterSetup):
        nonlocal client, device
        return SolaredgeExternalInverter(component_config, client=client, components=device.components)

    def update_components(components: Iterable[Union[SolaredgeBat, SolaredgeCounter, SolaredgeInverter]]):
        nonlocal client
        with client:
            for component in components:
                component.update()

    def initializer():
        nonlocal client
        client = modbus.ModbusTcpClient_(device_config.configuration.ip_address,
                                         device_config.configuration.port,
                                         reconnect_delay=reconnect_delay)
        # Attempt to connect to verify and log. The client handles actual connection management internally.
        # This is primarily to give an early feedback/log message.
        try:
            if client.connect():
                log.info("Successfully connected to SolarEdge device %s at %s:%s for initial check.",
                         device_config.name, device_config.configuration.ip_address, device_config.configuration.port)
                # The client will be opened again by `with client:` in `update_components` or when first used.
                # We close it here if we opened it just for this check.
                client.close()
            else:
                log.warning("Initial connection check failed for SolarEdge device %s at %s:%s. Will retry on updates.",
                            device_config.name, device_config.configuration.ip_address, device_config.configuration.port)
        except Exception as e:
            log.error("Exception during initial connection check for SolarEdge device %s at %s:%s: %s",
                      device_config.name, device_config.configuration.ip_address, device_config.configuration.port, e, exc_info=True)


    device = ConfigurableDevice(
        device_config=device_config,
        initializer=initializer,
        component_factory=ComponentFactoryByType(
            bat=create_bat_component,
            counter=create_counter_component,
            external_inverter=create_external_inverter_component,
            inverter=create_inverter_component,
        ),
        component_updater=MultiComponentUpdater(update_components)
    )
    return device


device_descriptor = DeviceDescriptor(configuration_factory=Solaredge)
