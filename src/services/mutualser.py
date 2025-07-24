"""
Main module for interacting with the MutualSer API.

This script provides a self-sufficient client class for authenticating and
making requests to the MutualSer API endpoints. It automatically handles
token acquisition and renewal.
"""
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from functools import wraps

import requests
from requests import JSONDecodeError
from requests.exceptions import RequestException

from src.config import BASE_DIR, log
from src.decorators import production_only
from src.models.mutualser import FileLinkRequest, FileLinkResponse, UploadFilesRequest, FindLoadResponse

from src.constants import LOGI_NIT, MUTUALSER_USERNAME, MUTUALSER_PASSWORD, BASE_URL_AUTH, BASE_URL_API, PORTAL_URL, \
    USER_ID
from src.resources.files import extract_nro_factura_from_file


def _token_required(func):
    """
    Decorator to ensure that a valid access token is present before making an API call.
    If the token is missing or a 401 Unauthorized error occurs, it triggers a login
    and retries the original request.
    """

    @wraps(func)
    def wrapper(client_instance: 'MutualSerAPIClient', *args, **kwargs):
        # If we have never logged in, do it first.
        if not client_instance.access_token:
            log.info("No token found. Performing initial login.")
            client_instance.login()

        try:
            # Attempt the decorated API call
            return func(client_instance, *args, **kwargs)
        except RequestException as e:
            # If the request failed with a 401, our token likely expired.
            if e.response is not None and e.response.status_code == 401:
                log.warning("Token expired or invalid (401). Re-authenticating.")
                client_instance.login()  # Re-login to get a new token
                log.info("Re-authentication successful. Retrying the original request.")
                # Retry the decorated API call one more time
                return func(client_instance, *args, **kwargs)
            else:
                # For any other request exception, re-raise it.
                raise

    return wrapper


class MutualSerAPIClient:
    """
    A self-sufficient client for the MutualSer API.

    This class encapsulates all configuration, authentication, and request logic.
    It automatically handles token acquisition and renewal.
    """
    _BASE_URL_AUTH = BASE_URL_AUTH
    _BASE_URL_API = BASE_URL_API
    LOGIN_ENDPOINT = "/login/users/login"
    CONFIG_INFO_ENDPOINT = "/mutual-api-rfds/api/v1/rips-api/application"
    UPLOAD_RIPS_ENDPOINT = "/mutual-api-rfds/api/v1/rips-api/upload"
    UPLOAD_FILES = "/mutual-api-rfds/api/v1/rips-api/upload-files"
    GET_URL_UPLOAD_FILE = "/mutual-api-rfds/api/v1/rips-api/signedUrl/getUrlUploadFile"
    UPLOAD_GOOGLE_FILE = "/rdfs_firebase_prod/{codigo}.zip"
    FIND_LOAD_ENDPOINT = "/mutual-api-rfds/api/v1/rips-api/findLoad"

    _ORGANIZACION_ID = LOGI_NIT
    _ORGANIZACION_NAME = "LOGIFARMA S.A.S."
    _USER_ID = USER_ID

    def __init__(self):
        """
        Initializes the API client.
        Loads credentials from environment variables and sets up a session.
        """
        self._load_credentials()
        self.session = requests.Session()
        self.access_token: Optional[str] = None
        self.user_details: Dict[str, Any] = {'usuario': MUTUALSER_USERNAME, 'email': MUTUALSER_USERNAME}
        self.codigo = ''

    @property
    def transaction_id(self) -> str:
        """Retrieves the transaction-id from session headers."""
        trans_id = self.session.headers.get('transaction-id')
        if not trans_id:
            raise AttributeError(
                "Attribute 'transaction-id' not found in session headers. "
                "Ensure `get_config_info` has been called successfully."
            )
        return trans_id

    def _load_credentials(self):
        """Loads username and password from environment variables."""
        self.username = MUTUALSER_USERNAME
        self.password = MUTUALSER_PASSWORD

        if not all([self.username, self.password]):
            raise ValueError("FATAL: MUTUALSER_USERNAME and MUTUALSER_PASSWORD environment variables must be set.")

    def _get_base_headers(self) -> Dict[str, str]:
        """Generates a set of base headers with a dynamic User-Agent."""
        try:
            from fake_useragent import UserAgent
            user_agent = UserAgent().random
        except ImportError:
            log.warning("`fake-useragent` not installed. Using a static User-Agent.")
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'

        return {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': PORTAL_URL,
            'pragma': 'no-cache',
            'referer': PORTAL_URL,
            'user-agent': user_agent,
        }

    def _make_request(self, method: str, endpoint: str, base_url: Optional[str] = None, **kwargs: Any) -> dict[
                                                                                                              Any, Any] | None | Any:
        """A generic helper method to execute API requests."""
        final_base_url = base_url or self._BASE_URL_AUTH
        url = f"{final_base_url}{endpoint}"
        try:
            if endpoint == self.UPLOAD_RIPS_ENDPOINT:
                self.codigo = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-2]
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return {} if response.status_code == 204 else response.json()
        except JSONDecodeError:
            if endpoint == self.UPLOAD_RIPS_ENDPOINT:
                return {}
        except RequestException as e:
            log.error(f"API request to {url} failed: {e}")
            raise

    def login(self) -> None:
        """
        Authenticates using instance credentials, creates a dynamic User-Agent,
        and sets the base headers for the session.
        This method is called automatically by the @_token_required decorator.
        """
        # log.info(f"Attempting to log in as {self.username}...")
        payload = {'username': self.username, 'password': self.password}

        # Login uses its own headers, creating a dynamic user-agent for this session.
        login_headers = self._get_base_headers()

        login_response = self._make_request(
            method='POST',
            endpoint=self.LOGIN_ENDPOINT,
            json=payload,
            headers=login_headers
        )

        self.access_token = login_response.get('access_token')
        token_type = login_response.get('token_type', 'Bearer')

        if not self.access_token:
            raise ValueError("Login failed: 'access_token' not found in response.")

        # Store user details from the response for later use in other requests
        # self.user_details = {
        #     'email': login_response.get('email'),
        #     'username': login_response.get('preferred_username'),
        # }

        # Set the base headers and auth token for all subsequent requests in this session.
        auth_header = f"{token_type.capitalize()} {self.access_token}"
        self.session.headers.clear()
        self.session.headers.update(login_headers)
        self.session.headers.update({'Authorization': auth_header})
        log.info("Authorization token and base headers have been successfully set for the session.")

    def _update_api_headers(self, api_headers: Dict[str, str]) -> None:
        """
        Updates the session headers with additional contextual information.

        This is intended to be called after the first successful API call that
        provides context (like organization, user ID, etc.), enriching the
        headers for all subsequent requests in the session.

        Args:
            api_headers (Dict[str, str]): A dictionary of headers to add to the session.
        """
        self.session.headers.update(api_headers)

    # --- Public API Methods ---

    @_token_required
    def get_config_info(self) -> str:
        """
        Fetches application configuration and returns the ID of a specific type.

        This method requires extra user and organization context in the headers.
        It also enriches the session headers for subsequent API calls.

        Args:
            codigo_aplicacion (str): The application code to query (e.g., 'REG-FACT').
            tipo_codigo (str): The code of the specific type to find (e.g., 'ZIP_REG-FACT').

        Returns:
            str: The ID of the matching type.

        Raises:
            ValueError: If the specified type code is not found in the response.
        """
        # These headers are specific to this request. They will be merged with
        # session headers for this call and then stored for subsequent requests.
        request_headers = {
            'email': self.user_details.get('email', ''),
            'usuario': self.user_details.get('usuario', ''),
            'organizacion': self._ORGANIZACION_ID,
            'organizacionname': self._ORGANIZACION_NAME,
            'user-id': self._USER_ID,
            'roles': '15574sad',
            'transaction-id': str(uuid.uuid4()),
        }

        params = {'codigo_aplicacion': 'REG-FACT'}

        # Make the request to the different API base URL
        config_data = self._make_request(
            method='GET',
            endpoint=self.CONFIG_INFO_ENDPOINT,
            base_url=self._BASE_URL_API,
            params=params,
            headers=request_headers
        )

        # After the first successful call, update the session headers with this context.
        self._update_api_headers(request_headers)

        # Process the response to find the required ID
        tipo_codigo = 'ZIP_REG-FACT'
        for tipo in config_data.get('tipos', []):
            if tipo.get('codigo') == tipo_codigo:
                tipo_id = tipo.get('id')
                # log.info(f"Found matching type '{tipo_codigo}' with ID: {tipo_id}")
                if not tipo_id:
                    raise ValueError(f"Type '{tipo_codigo}' found, but it has no 'id'.")
                return tipo_id

        raise ValueError(f"Could not find a type with codigo '{tipo_codigo}' in the response.")

    @_token_required
    def upload_rips_file(self, tipo_id: str, file_name: Path) -> None:
        """
        Uploads a RIPS file record to the API.

        Args:
            tipo_id (str): The ID of the file type, obtained from `get_config_info`.
            file_name (Path): The name of the file being uploaded (e.g., 'LGFM1574927_900073223.zip').
        """
        # log.info(f"Submitting upload record for file: {file_name}")

        payload = {
            'id_cargue': self.transaction_id,
            'id_tipo': tipo_id,
            'organizacion': self._ORGANIZACION_ID,
            'cantidad': 1,
            'nombres': [str(file_name)],
        }

        self._make_request(
            method='POST',
            endpoint=self.UPLOAD_RIPS_ENDPOINT,
            base_url=self._BASE_URL_API,
            json=payload
        )

        # log.info("Successfully submitted the upload record.")

    @_token_required
    def get_url_upload_file(self):
        """Get the URL necessary to upload the file to Google."""
        # log.info(f"Getting Google URL for file.")

        file_link_req = FileLinkRequest(fileNames=f"{self.codigo}.zip")

        resp = self._make_request(
            method='GET',
            endpoint=self.GET_URL_UPLOAD_FILE,
            base_url=self._BASE_URL_API,
            params=file_link_req.model_dump(mode='json')
        )

        # log.info(f'{resp=!r}')
        return FileLinkResponse(resp)

    @_token_required
    def upload_to_google(self, file_path: Path, gurl: str):
        """Upload file to google based on URL to be requested."""
        log.info(f"{extract_nro_factura_from_file(file_path)} Cargando archivo {file_path.name} en Mutual Ser")
        # self._update_api_headers({"Content-Type": "application/x-www-form-urlencoded"})
        with open(file_path, 'rb') as file:
            file_content = file.read()
            file_size = len(file_content)
            content_lengt = str(file_size)

        self._update_api_headers({"Content-Type": "application/zip", 'Content-Length': content_lengt})
        self.session.request('PUT', gurl, data=file_content)
        self._update_api_headers({"Content-Type": 'application/json'})
        del self.session.headers['Content-Length']

    @_token_required
    def upload_files(self, tipo_id: str, file_name: Path):
        """Uploads a file to the API."""
        file_request = UploadFilesRequest(
            codigo=f"{self.codigo}.zip",
            mensajes=[],
            id_archivo=str(uuid.uuid4()),
            id_cargue=self.transaction_id,
            extension='zip',
            tamano=round(file_name.stat().st_size / (1024 ** 2), 2),
            id_tipo=tipo_id,
            nombre=str(file_name),
        )
        response = self._make_request(
            method='POST',
            endpoint=self.UPLOAD_FILES,
            base_url=self._BASE_URL_API,
            json=[file_request.model_dump(mode='json')]
        )
        return response

    @_token_required
    def find_load_status(self, max_retries: int = 10, delay_seconds: int = 6) -> FindLoadResponse:
        """
        Polls the findLoad endpoint to check the status of the file upload.

        It checks the 'estado' field and retries if it is 'EN_PROCESO'.

        Args:
            max_retries (int): The maximum number of times to poll the endpoint.
            delay_seconds (int): The number of seconds to wait between retries.

        Returns:
            Dict[str, Any]: The final response from the findLoad endpoint.

        Raises:
            ValueError: If the upload is still in process after all retries.
        """
        # log.info(f"Checking upload status for transaction ID: {self.transaction_id}")

        today = datetime.now()
        payload = {
            'id': self.transaction_id,
            'fecha_inicial': today.strftime('%d/%m/%Y 00:00:00'),
            'fecha_final': today.strftime('%d/%m/%Y 23:59:59'),
            'organizacion': self._ORGANIZACION_ID,
        }

        for attempt in range(max_retries):
            # log.info(f"Polling attempt {attempt + 1}/{max_retries}...")
            response = self._make_request(
                method='POST',
                endpoint=self.FIND_LOAD_ENDPOINT,
                base_url=self._BASE_URL_API,
                json=payload
            )

            resp_obj = FindLoadResponse(**response)
            # log.info(f"Current upload status is: {resp_obj.estado_basado_en_archivos}")

            if resp_obj.done:
                # log.info("Upload processing finished.")
                return resp_obj

            if attempt < max_retries - 1:
                # log.info(f"Status is still 'EN_PROCESO'. Waiting for {delay_seconds} seconds before retrying.")
                time.sleep(delay_seconds)

        raise ValueError(f"Después de {max_retries} intentos, no se cargó la factura. "
                         f"Último estado de API fue {resp_obj.estado_basado_en_archivos!r}. "
                         f"El ID de Cargue es {self.transaction_id}.")

    @production_only
    def upload_file(self, filepath: Path) -> FindLoadResponse | None:
        """Main function to upload the file into Mutual Ser."""
        try:
            # 1. Directly call a protected method. The decorator handles login automatically.
            tipo_id = self.get_config_info()
            # 2. Upload the RIPS file information
            self.upload_rips_file(tipo_id=tipo_id, file_name=filepath)
            # 3. Get the URL necessary to upload the file to Google
            url_google_file = self.get_url_upload_file()
            # 4. Upload file to google based on URL to be requested
            self.upload_to_google(filepath, url_google_file.root[f"{self.codigo}.zip"])
            # 5. Uploads the file to the API
            self.upload_files(tipo_id=tipo_id, file_name=filepath)
            # 6. Poll for the final status of the upload
            final_response = self.find_load_status()
            # 7. Poll for the final status of the upload
            log.info(f"{extract_nro_factura_from_file(filepath)} Archivo cargado "
                     f"con ID de cargue: {final_response.id}: {final_response.model_dump_json()}")
        except (RequestException, ValueError, AttributeError) as e:
            log.error(f"Could not complete the process: {e}")
            raise
        except Exception as e:
            log.error(f"An unexpected error occurred: {e}", exc_info=True)
            raise
        else:
            return final_response


if __name__ == "__main__":
    api_client = MutualSerAPIClient()
    api_client.upload_file(BASE_DIR / 'LGFM1590904_900073223.zip')
