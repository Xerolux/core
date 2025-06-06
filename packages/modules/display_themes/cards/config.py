from typing import Optional
from helpermodules.auto_str import auto_str

from modules.common.abstract_device import DeviceDescriptor


@auto_str
class CardsDisplayThemeConfiguration:
    def __init__(self,
                 lock_changes: bool = False,
                 lock_changes_code: Optional[str] = None,
                 default_view: str = "dashboard",
                 default_view_timeout: int = 0,
                 enable_dashboard_view: bool = True,
                 enable_dashboard_card_grid: bool = True,
                 enable_dashboard_card_home_consumption: bool = True,
                 enable_dashboard_card_battery_sum: bool = True,
                 enable_dashboard_card_inverter_sum: bool = True,
                 enable_dashboard_card_charge_point_sum: bool = True,
                 enable_dashboard_card_vehicles: bool = True,
                 enable_energy_flow_view: bool = True,
                 enable_charge_points_view: bool = True,
                 simple_charge_point_view: bool = False,
                 enable_status_view: bool = True) -> None:
        # display lock settings
        self.lock_changes = lock_changes
        self.lock_changes_code = lock_changes_code
        # dashboard settings
        self.default_view = default_view
        self.default_view_timeout = default_view_timeout
        self.enable_dashboard_view = enable_dashboard_view
        self.enable_dashboard_card_grid = enable_dashboard_card_grid
        self.enable_dashboard_card_home_consumption = enable_dashboard_card_home_consumption
        self.enable_dashboard_card_battery_sum = enable_dashboard_card_battery_sum
        self.enable_dashboard_card_inverter_sum = enable_dashboard_card_inverter_sum
        self.enable_dashboard_card_charge_point_sum = enable_dashboard_card_charge_point_sum
        self.enable_dashboard_card_vehicles = enable_dashboard_card_vehicles
        # energy flow settings
        self.enable_energy_flow_view = enable_energy_flow_view
        # charge point settings
        self.enable_charge_points_view = enable_charge_points_view
        self.simple_charge_point_view = simple_charge_point_view
        # state settings
        self.enable_status_view = enable_status_view


@auto_str
class CardsDisplayTheme:
    def __init__(self,
                 name: str = "Cards",
                 type: str = "cards",
                 official: bool = True,
                 configuration: CardsDisplayThemeConfiguration = None) -> None:
        self.name = name
        self.type = type
        self.official = official
        self.configuration = configuration or CardsDisplayThemeConfiguration()


theme_descriptor = DeviceDescriptor(configuration_factory=CardsDisplayTheme)
