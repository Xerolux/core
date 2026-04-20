from typing import Optional


class SeafileBackupCloudConfiguration:
    def __init__(self,
                 ip_address: Optional[str] = None,
                 user: Optional[str] = None,
                 password: Optional[str] = None,
                 path: Optional[str] = None,
                 max_backups: Optional[int] = None):
        self.ip_address = ip_address
        self.user = user
        self.password = password
        self.path = path
        # None oder <= 0 bedeutet: keine automatische Löschung alter Backups
        self.max_backups = max_backups


class SeafileBackupCloud:
    def __init__(self,
                 name: str = "Seafile",
                 type: str = "seafile",
                 official: bool = True,
                 configuration: SeafileBackupCloudConfiguration = None) -> None:
        self.name = name
        self.type = type
        self.official = official
        self.configuration = configuration or SeafileBackupCloudConfiguration()
