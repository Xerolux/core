#!/usr/bin/env python3
import logging
import os
import requests

from modules.backup_clouds.google_drive.api import get_tokens
from modules.backup_clouds.google_drive.config import GoogleDriveBackupCloud, GoogleDriveBackupCloudConfiguration
from modules.common.abstract_device import DeviceDescriptor


log = logging.getLogger(__name__)

def _get_or_create_folder(access_token: str, folder_name: str, parent_id: str = None) -> str:
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    url = "https://www.googleapis.com/drive/v3/files"
    params = {
        "q": query,
        "spaces": "drive",
        "fields": "files(id, name)"
    }

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    files = response.json().get('files', [])

    if files:
        return files[0]['id']
    else:
        # Create folder
        log.debug(f"Creating folder {folder_name} in Google Drive")
        metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            metadata['parents'] = [parent_id]

        response = requests.post(
            "https://www.googleapis.com/drive/v3/files",
            headers=headers,
            json=metadata
        )
        response.raise_for_status()
        return response.json()['id']


def _get_folder_id_by_path(access_token: str, path: str) -> str:
    parts = [p for p in path.split('/') if p]
    parent_id = None
    for part in parts:
        parent_id = _get_or_create_folder(access_token, part, parent_id)
    return parent_id


def upload_backup(config: GoogleDriveBackupCloudConfiguration, backup_filename: str, backup_file: bytes) -> None:
    tokens = get_tokens(config)
    access_token = tokens["access_token"]

    log.debug("Uploading file %s to Google Drive", backup_filename)

    folder_id = None
    if config.backuppath:
        folder_id = _get_folder_id_by_path(access_token, config.backuppath)

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    metadata = {
        "name": backup_filename.split('/')[-1]
    }

    if folder_id:
        metadata["parents"] = [folder_id]

    # Start resumable upload session
    response = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
        headers=headers,
        json=metadata
    )
    response.raise_for_status()

    upload_url = response.headers['Location']

    # Upload the file
    upload_response = requests.put(
        upload_url,
        data=backup_file
    )
    upload_response.raise_for_status()
    log.debug("Successfully uploaded file to Google Drive.")


def create_backup_cloud(config: GoogleDriveBackupCloud):
    def updater(backup_filename: str, backup_file: bytes):
        upload_backup(config.configuration, backup_filename, backup_file)
    return updater


device_descriptor = DeviceDescriptor(configuration_factory=GoogleDriveBackupCloud)
