from typing import Optional


class GoogleDriveBackupCloudConfiguration:
    def __init__(self, backuppath: str = "openWB/Backup/",
                 persistent_tokencache: Optional[str] = None, # Used to store the refresh token
                 authurl: Optional[str] = None,
                 authcode: Optional[str] = None,
                 device_code: Optional[str] = None,
                 scope: Optional[list] = ["https://www.googleapis.com/auth/drive.file"],
                 clientID: Optional[str] = "399436338578-ik6k9c5erih1d4o6b8v4vdf0mkskss0a.apps.googleusercontent.com",
                 clientSecret: Optional[str] = None,
                 ) -> None:
        self.backuppath = backuppath
        self.persistent_tokencache = persistent_tokencache
        self.authurl = authurl
        self.authcode = authcode
        self.device_code = device_code
        self.scope = scope
        self.clientID = clientID
        self.clientSecret = clientSecret


class GoogleDriveBackupCloud:
    def __init__(self,
                 name: str = "GoogleDrive",
                 type: str = "google_drive",
                 official: bool = False,
                 configuration: GoogleDriveBackupCloudConfiguration = None) -> None:
        self.name = name
        self.type = type
        self.official = official
        self.configuration = configuration or GoogleDriveBackupCloudConfiguration()
