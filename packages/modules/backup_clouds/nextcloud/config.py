from typing import Optional
import os
import re
from datetime import datetime, timedelta


class NextcloudBackupCloudConfiguration:
    def __init__(self, ip_address: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None,
                 retention_days: Optional[int] = None):
        # Validierung der IP-Adresse/URL
        if ip_address and not re.match(r'(http[s]?://)?[\w.-]+(?:\.[\w\.-]+)+', ip_address):
            raise ValueError(f"Ungültige IP-Adresse oder URL: {ip_address}")
        self.ip_address = ip_address
        self.user = user
        self.password = password
        self.retention_days = retention_days  # Neue Retention-Option


class NextcloudBackupCloud:
    def __init__(self,
                 name: str = "NextCloud",
                 type: str = "nextcloud",
                 configuration: Optional[NextcloudBackupCloudConfiguration] = None) -> None:
        self.name = name
        self.type = type
        self.configuration = configuration or NextcloudBackupCloudConfiguration()
