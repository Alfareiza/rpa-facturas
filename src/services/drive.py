from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_not_exception_type
from src.config import log

from src.constants import GOOGLE_TOKEN, GOOGLE_REFRESH_TOKEN, GOOGLE_TOKEN_URI, GOOGLE_CLIENT_ID, \
    GOOGLE_CLIENT_SECRET, GOOGLE_SCOPES, FACTURAS_PDF, FACTURAS_PROCESADAS, FACTURAS_TMP, LOGISTICA_GOOGLE_TOKEN, \
    LOGISTICA_GOOGLE_REFRESH_TOKEN, LOGISTICA_GOOGLE_CLIENT_ID, LOGISTICA_GOOGLE_CLIENT_SECRET, LOGISTICA_GOOGLE_SCOPES, \
    XMLS_MUTUALSER
from src.resources.files import get_mime_type


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

    def get_facturas_mes_name(self, mes: int, ano: int):
        """"""
        return f"FacturasMutualser_{ano}{mes:02d}"

    # @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def file_exists_in_folder(self, file_path: Path, folder_id: str, file_type = 'application/pdf') -> dict | None:
        """
        Validates if a file exists in a folder given a file name with PDF extension and a folder id.
        
        Args:
            file_path: The file
            folder_id: The ID of the folder to search in
            file_type: 'application/pdf' by default.
            
        Returns:
            dict: File dictionary with 'id' field if file exists, None otherwise
        """
        file_type = get_mime_type(file_path) or file_type
        query = f"'{folder_id}' in parents and name='{file_path.name}' and mimeType='{file_type}' and trashed=false"
        response = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id)'
        ).execute()
        
        files = response.get('files', [])
        if files:
            return {'id': files[0].get('id')}
        return None

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), retry=retry_if_not_exception_type(FileNotFoundError),
           reraise=True)
    def upload_file(self, file_path: Path, folder_id: str = None) -> dict:
        """Uploads a file to Google Drive."""
        # Check if file already exists in the folder
        if existing_file := self.file_exists_in_folder(file_path, folder_id):
            log.info(f"Archivo {file_path.name} existe en Drive")
            # self.delete_file(existing_file.get('id'))
            return existing_file
        
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
        log.info(f"{file_path.name} cargado en Drive")
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

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def exclude_duplicated_files(self) -> list:
        """
        Goes through self.facturas_pdf folder and excludes duplicated files based on the name.
        Deletes duplicate files from Google Drive, keeping only the first occurrence of each file name.
        
        Returns:
            list: List of file dictionaries with 'id' and 'name' fields for the remaining unique files.
        """
        query = f"'{self.facturas_pdf}' in parents and trashed=false and mimeType='application/pdf'"
        all_files = []
        next_page_token = None
        
        # Fetch all files from the folder (handling pagination)

        while True:
            response = self.service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name)',
                orderBy='modifiedTime desc',
                pageSize=1000,
                pageToken=next_page_token
            ).execute()
            
            files = response.get('files', [])
            all_files.extend(files)
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        
        # Track seen file names and delete duplicates
        seen_names = set()
        unique_files = []
        
        for file in all_files:
            file_name = file.get('name')
            if file_name not in seen_names:
                seen_names.add(file_name)
                unique_files.append(file)
            else:
                # Delete duplicate file from Google Drive
                self.delete_file(file.get('id'))
                print(f'Removing duplicated file {file.get('name')!r}')
        
        return unique_files


class GoogleDriveLogistica:
    def __init__(self):
        self.creds = Credentials(
            token=LOGISTICA_GOOGLE_TOKEN,
            refresh_token=LOGISTICA_GOOGLE_REFRESH_TOKEN,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=LOGISTICA_GOOGLE_CLIENT_ID,
            client_secret=LOGISTICA_GOOGLE_CLIENT_SECRET,
            scopes=LOGISTICA_GOOGLE_SCOPES
        )
        self.service = build('drive', 'v3', credentials=self.creds)

        self.xmls = XMLS_MUTUALSER

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def create_or_get_folder_id(self, folder_name: str) -> str:
        """
        Gets a folder by name or creates it if it doesn't exist.
        """
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        response = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        if files := response.get('files', []):
            return files[0].get('id')

        file_metadata = {
            'name': folder_name,
            'parents': [self.xmls],
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = self.service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')


if __name__ == '__main__':
    from src.config import BASE_DIR, log

    drive_client = GoogleDrive()
    unique = drive_client.exclude_duplicated_files()
    # drive_client.upload_file(BASE_DIR / 'LGFM1574927_900073223x.zip', drive_client.temp)
