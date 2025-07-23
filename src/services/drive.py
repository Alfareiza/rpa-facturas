from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_not_exception_type

from src.constants import GOOGLE_TOKEN, GOOGLE_REFRESH_TOKEN, GOOGLE_TOKEN_URI, GOOGLE_CLIENT_ID, \
    GOOGLE_CLIENT_SECRET, GOOGLE_SCOPES, FACTURAS_PDF, FACTURAS_PROCESADAS, FACTURAS_TMP


class GoogleDrive:
    def __init__(self):
        self.creds = Credentials(
            token=GOOGLE_TOKEN,
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=GOOGLE_SCOPES
        )
        self.service = build('drive', 'v3', credentials=self.creds)

        self.facturas_pdf = FACTURAS_PDF
        self.procesadas = FACTURAS_PROCESADAS
        self.temp = FACTURAS_TMP

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), retry=retry_if_not_exception_type(FileNotFoundError),
           reraise=True)
    def upload_file(self, file_path: Path, folder_id: str = None) -> dict:
        """
        Uploads a file to Google Drive.
        """
        file_metadata = {
            'name': file_path.name,
            'parents': [folder_id]
        }
        media = MediaFileUpload(file_path, resumable=True)
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        return file

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def move_file(self, file_id: str, new_folder_id: str) -> dict:
        """
        Moves a file to a different folder in Google Drive.
        """
        file = self.service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents'))
        file = self.service.files().update(
            fileId=file_id,
            addParents=new_folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
        return file

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def delete_file(self, file_id: str) -> None:
        """
        Deletes a file from Google Drive.
        """
        self.service.files().delete(fileId=file_id).execute()


if __name__ == '__main__':
    from src.config import BASE_DIR

    drive_client = GoogleDrive()
    drive_client.upload_file(BASE_DIR / 'LGFM1574927_900073223x.zip', drive_client.temp)
