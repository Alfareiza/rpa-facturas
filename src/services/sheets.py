from typing import List

import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from gspread_dataframe import set_with_dataframe
from gspread_formatting.dataframe import format_with_dataframe
from pandas import DataFrame
from pydantic.v1.validators import max_str_int
from tenacity import retry, stop_after_attempt, wait_fixed

from src.constants import SPREADSHEET_ID, GOOGLE_TOKEN, GOOGLE_REFRESH_TOKEN, GOOGLE_TOKEN_URI, \
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_SCOPES


class GoogleSheets:
    def __init__(self):
        self.creds = Credentials(
            token=GOOGLE_TOKEN,
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=GOOGLE_SCOPES
        )
        self.service = build('sheets', 'v4', credentials=self.creds)
        self.spreadsheet_id = SPREADSHEET_ID

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1))
    def get_values(self, range_name: str) -> List[List[str]]:
        """
        Gets values from a spreadsheet.
        """
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name
        ).execute()
        return result.get('values', [])

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1))
    def append_values(self, range_name: str, values: List[List[str]]) -> dict:
        """
        Appends values to a spreadsheet.
        """
        body = {
            'values': values
        }
        result = self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        return result

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1))
    def update_values(self, range_name: str, values: List[List[str]]) -> dict:
        """
        Updates values in a spreadsheet.
        """
        body = {
            'values': values
        }
        result = self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        return result

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1))
    def clear_values(self, range_name: str) -> dict:
        """
        Clears values from a spreadsheet.
        """
        result = self.service.spreadsheets().values().clear(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            body={}
        ).execute()
        return result


class GSpreadSheets:
    def __init__(self):
        self.creds = Credentials(
            token=GOOGLE_TOKEN,
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=GOOGLE_SCOPES
        )
        self.gc = gspread.authorize(self.creds)
        self.spreadsheet = self.gc.open_by_key(SPREADSHEET_ID)

    @property
    def control_worksheet(self) -> gspread.Worksheet:
        return self.spreadsheet.worksheet('CONTROL')

    def get_all_records(self) -> List[dict]:
        """Returns all records from a worksheet. """
        self.control_worksheet.get_all_records()

    def append_row(self, values: List[str]) -> dict:
        """Appends a row to the worksheet."""
        self.control_worksheet.append_row(values)

    def update_cell(self, row: int, col: int, value: str) -> dict:
        """Updates a cell in the worksheet."""
        self.control_worksheet.update_cell(row, col, value)

    def clear_worksheet(self) -> dict:
        """Clears the worksheet."""
        self.control_worksheet.clear()

    def write_df_to_worksheet(self, df: DataFrame):
        """Writes pandas DataFrame to Google Sheets' worksheet."""
        set_with_dataframe(self.control_worksheet, df)
        format_with_dataframe(self.control_worksheet, df, include_column_header=True)

    def insert_dataframe(self, df: DataFrame):
        """Inserts a DataFrame after the header row, shifting existing data down."""
        if self.control_worksheet.acell('A2').value:
            self.control_worksheet.insert_rows(df.values.tolist(), 2)
        else:
            self.write_df_to_worksheet(df)


if __name__ == '__main__':
    gs = GSpreadSheets()
