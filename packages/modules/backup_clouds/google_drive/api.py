import logging
import json
import paho.mqtt.publish as publish
import base64
import requests
from helpermodules.messaging import MessageType
from modules.backup_clouds.google_drive.config import GoogleDriveBackupCloud, GoogleDriveBackupCloudConfiguration

log = logging.getLogger(__name__)

def save_tokencache(config: GoogleDriveBackupCloudConfiguration, cache: str) -> None:
    # We will use persistent_tokencache to store the refresh token
    log.debug("saving updated google tokencache to config")
    config.persistent_tokencache = cache

    # construct full configuartion object for cloud backup
    backupcloud = GoogleDriveBackupCloud()
    backupcloud.configuration = config
    backupcloud_to_mqtt = json.dumps(backupcloud.__dict__, default=lambda o: o.__dict__)
    log.debug("Config to MQTT:" + str(backupcloud_to_mqtt))

    publish.single("openWB/set/system/backup_cloud/config", backupcloud_to_mqtt, retain=True, hostname="localhost")


def get_tokens(config: GoogleDriveBackupCloudConfiguration) -> dict:
    if not config.persistent_tokencache:
        raise Exception("No tokencache found, please re-configure and re-authorize access Cloud backup settings.")

    refresh_token = config.persistent_tokencache

    data = {
        'client_id': config.clientID,
        'client_secret': config.clientSecret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }

    response = requests.post("https://oauth2.googleapis.com/token", data=data)

    if response.status_code == 200:
        result = response.json()
        log.debug("Google access token retrieved")
        return result
    else:
        raise Exception("Error retrieving access token: %s" % response.text)


def generateGoogleAuthCode(cloudbackup: GoogleDriveBackupCloud) -> dict:
    """ startet den Authentifizierungsprozess für Google Drive Backup
    und speichert den AuthCode in der Konfiguration"""
    result = dict(
        message="",
        MessageType=MessageType.SUCCESS
    )

    if cloudbackup is None:
        result["message"] = """Es ist keine Backup-Cloud konfiguriert.
                            Bitte Konfiguration speichern und erneut versuchen.<br />"""
        result["MessageType"] = MessageType.WARNING
        return result

    data = {
        'client_id': cloudbackup.configuration.clientID,
        'scope': ' '.join(cloudbackup.configuration.scope)
    }

    try:
        response = requests.post('https://oauth2.googleapis.com/device/code', data=data)
        response.raise_for_status()
        flow = response.json()
    except Exception as e:
        raise Exception("Fail to create device flow. Err: %s" % str(e))

    cloudbackup.configuration.device_code = flow["device_code"]
    cloudbackup.configuration.authcode = flow["user_code"]
    cloudbackup.configuration.authurl = flow["verification_url"]

    cloudbackupconfig_to_mqtt = json.dumps(cloudbackup.__dict__, default=lambda o: o.__dict__)

    publish.single(
        "openWB/set/system/backup_cloud/config", cloudbackupconfig_to_mqtt, retain=True, hostname="localhost"
    )

    result["message"] = """Autorisierung gestartet, bitte den Link öffnen, Code eingeben,
        und Zugang autorisieren. Anschließend Zugangsberechtigung abrufen."""
    result["MessageType"] = MessageType.SUCCESS

    return result


def retrieveGoogleTokens(cloudbackup: GoogleDriveBackupCloud) -> dict:
    result = dict(
        message="",
        MessageType=MessageType.SUCCESS
    )
    if cloudbackup is None:
        result["message"] = """Es ist keine Backup-Cloud konfiguriert.
                            Bitte Konfiguration speichern und erneut versuchen.<br />"""
        result["MessageType"] = MessageType.WARNING
        return result

    device_code = cloudbackup.configuration.device_code
    if device_code is None:
        result["message"] = """Es ist wurde kein Auth-Code erstellt.
                            Bitte zunächst Auth-Code erstellen und den Autorisierungsprozess beenden.<br />"""
        result["MessageType"] = MessageType.WARNING
        return result

    data = {
        'client_id': cloudbackup.configuration.clientID,
        'client_secret': cloudbackup.configuration.clientSecret,
        'device_code': device_code,
        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
    }

    response = requests.post('https://oauth2.googleapis.com/token', data=data)
    tokens = response.json()

    if "access_token" in tokens and "refresh_token" in tokens:
        log.debug("retrieved Google tokens")

        # Tokens retrieved, remove auth codes as they are single use only.
        cloudbackup.configuration.device_code = None
        cloudbackup.configuration.authcode = None
        cloudbackup.configuration.authurl = None

        # save refresh token
        save_tokencache(config=cloudbackup.configuration, cache=tokens["refresh_token"])

        result["message"] = """Zugangsberechtigung erfolgreich abgerufen."""
        result["MessageType"] = MessageType.SUCCESS
        return result
    elif "error" in tokens:
        result["message"] = """"Es konnten keine Tokens abgerufen werden:
                            %s <br> %s""" % (tokens.get("error"), tokens.get("error_description", ""))
        result["MessageType"] = MessageType.WARNING
        return result
    else:
        result["message"] = """"Unbekannter Fehler beim Abrufen der Tokens."""
        result["MessageType"] = MessageType.WARNING
        return result
