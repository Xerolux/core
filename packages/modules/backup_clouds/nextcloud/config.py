#!/usr/bin/env python3
import logging
import re
import os
from datetime import datetime, timedelta
from typing import Optional

from modules.backup_clouds.nextcloud.config import NextcloudBackupCloud, NextcloudBackupCloudConfiguration
from modules.common import req
from modules.common.abstract_device import DeviceDescriptor

log = logging.getLogger(__name__)


class NextcloudBackupCloudConfiguration:
    def __init__(self, ip_address: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None,
                 retention_days: Optional[int] = None):
        """
        Konfiguration für Nextcloud-Backups.
        :param ip_address: URL oder IP-Adresse der Nextcloud-Instanz.
        :param user: Benutzername für die Authentifizierung.
        :param password: Passwort für die Authentifizierung.
        :param retention_days: Anzahl der Tage, für die Backups aufbewahrt werden sollen.
        """
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
        """
        Nextcloud-Backup-Cloud-Objekt.
        :param name: Name der Cloud.
        :param type: Typ der Cloud (z. B. "nextcloud").
        :param configuration: Die Konfiguration für die Cloud.
        """
        self.name = name
        self.type = type
        self.configuration = configuration or NextcloudBackupCloudConfiguration()


def upload_backup(config: NextcloudBackupCloudConfiguration, backup_filename: str, backup_file: bytes) -> None:
    """
    Lädt ein Backup zu Nextcloud hoch.
    :param config: Die Nextcloud-Konfiguration.
    :param backup_filename: Name der Backup-Datei.
    :param backup_file: Inhalt der Backup-Datei.
    """
    if config.user is None:
        url_match = re.fullmatch(r'(http[s]?):\/\/([\S^/]+)\/(?:index.php\/)?s\/(.+)', config.ip_address)
        if not url_match:
            raise ValueError(f"URL '{config.ip_address}' hat nicht die erwartete Form "
                             "'https://server/index.php/s/user_token' oder 'https://server/s/user_token'")
        upload_url = f"{url_match[1]}://{url_match[2]}"
        user = url_match.group(url_match.lastindex)
    else:
        upload_url = config.ip_address
        user = config.user

    req.get_http_session().put(
        f'{upload_url}/public.php/webdav/{backup_filename}',
        headers={'X-Requested-With': 'XMLHttpRequest'},
        data=backup_file,
        auth=(user, '' if config.password is None else config.password),
        timeout=30
    )


def create_backup_cloud(config: NextcloudBackupCloud):
    """
    Erstellt eine Backup-Cloud-Instanz.
    :param config: Die Konfiguration für die Cloud.
    :return: Eine Funktion, um ein Backup hochzuladen.
    """
    def updater(backup_filename: str, backup_file: bytes):
        upload_backup(config.configuration, backup_filename, backup_file)
    return updater


class BackupRetention:
    def __init__(self, backup_folder: str, retention_days: Optional[int] = None):
        """
        Initialisiert die Retention-Logik.
        :param backup_folder: Der Pfad zum Verzeichnis, in dem die Backups gespeichert werden.
        :param retention_days: Die Anzahl der Tage, die Backups aufbewahrt werden sollen.
        """
        self.backup_folder = backup_folder
        self.retention_days = retention_days

    def list_backups(self) -> list:
        """
        Listet alle Backups im Backup-Verzeichnis auf.
        :return: Eine Liste von Dateinamen im Backup-Verzeichnis.
        """
        return [
            f for f in os.listdir(self.backup_folder)
            if os.path.isfile(os.path.join(self.backup_folder, f))
        ]

    def delete_old_backups(self):
        """
        Löscht Backups, die älter sind als die konfigurierte Anzahl von Tagen.
        """
        if not self.retention_days:
            return  # Keine Retention konfiguriert

        now = datetime.now()
        cutoff_date = now - timedelta(days=self.retention_days)

        backups = self.list_backups()

        for backup in backups:
            full_path = os.path.join(self.backup_folder, backup)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(full_path))

            if file_mtime < cutoff_date:
                os.remove(full_path)
                log.info(f"Gelöscht: {full_path}")

    def add_backup(self, backup_file: str):
        """
        Fügt ein neues Backup hinzu und überprüft die Retention.
        :param backup_file: Der Pfad der neuen Backup-Datei.
        """
        backup_path = os.path.join(self.backup_folder, backup_file)
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Die Datei {backup_file} existiert nicht im Verzeichnis {self.backup_folder}")

        self.delete_old_backups()
        log.info(f"Backup hinzugefügt: {backup_file}")


device_descriptor = DeviceDescriptor(configuration_factory=NextcloudBackupCloud)


# Beispiel-Nutzung
if __name__ == "__main__":
    # Beispielkonfiguration
    config = NextcloudBackupCloudConfiguration(
        ip_address="https://example.com",
        user="admin",
        password="1234",
        retention_days=7  # Aufbewahrungszeit in Tagen
    )

    # Verzeichnis für Backups
    backup_folder = "/path/to/backup/folder"
    retention = BackupRetention(backup_folder=backup_folder, retention_days=config.retention_days)

    # Füge ein neues Backup hinzu
    new_backup = "backup_2025-01-05.tar.gz"
    retention.add_backup(new_backup)
