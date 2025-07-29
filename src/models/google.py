from datetime import datetime
from pathlib import Path
from typing import Optional
import zipfile

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.config import CONFIG
from src.constants import LOGI_NIT
from src.resources.datetimes import convert_utc_to_utc_minus_5
from src.resources.files import delete_file_if_exists


class EmailMessage(BaseModel):
    id: str
    thread_id: str = Field(alias='threadId')
    subject: Optional[str] = None
    seen: bool = False
    received_at: Optional[datetime] = None
    body_html: Optional[str] = None
    recipient: Optional[str] = None
    attachment_path: Optional[Path] = None
    pdf_path: Optional[Path] = None

    class Config:
        arbitrary_types_allowed = True
        orm_mode = True

    @property
    def soup(self) -> Optional[BeautifulSoup]:
        """Returns a BeautifulSoup object of the email's HTML body."""
        if self.body_html:
            return BeautifulSoup(self.body_html, "lxml")
        return None

    @property
    def valor_factura(self) -> int | None:
        """Extracts the value of the invoice from the email's HTML body"""
        if self.soup:
            b_tag = self.soup.find('b', string='Total:')
            td_with_value = b_tag.find_parent('td').find_next_sibling('td').find_next_sibling('td')
            raw_text = td_with_value.get_text(strip=True).replace(',', '')
            return int(float(raw_text))
        return None

    @property
    def nro_factura(self) -> Optional[str]:
        """Extracts the invoice number from the email subject."""
        if self.subject:
            try:
                return self.subject.split(";")[2]
            except IndexError:
                return None
        return None

    @property
    def fecha_factura(self) -> Optional[str]:
        """Convert the date to a UTC-5 date and return it as string"""
        if self.received_at:
            return f"{convert_utc_to_utc_minus_5(self.received_at):%d/%m/%Y}"
        return ""

    @property
    def zip_name(self) -> Optional[str]:
        """Constructs the zip filename from the invoice number and customer NIT."""
        if self.nro_factura:
            return f"{self.nro_factura}_{LOGI_NIT}.zip"
        return None

    def extract_and_rename_pdf(self) -> Optional[Path]:
        """Extracts a PDF file from a ZIP attachment, renames it, and saves the new path."""
        if self.attachment_path and self.attachment_path.exists() and self.nro_factura and self.valor_factura:
            with zipfile.ZipFile(self.attachment_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.filename.lower().endswith('.pdf'):
                        pdf_content = zip_ref.read(file_info.filename)
                        new_filename = f"{self.nro_factura}_{self.valor_factura}.pdf"
                        self.pdf_path = CONFIG.DIRECTORIES.TEMP / new_filename
                        with open(self.pdf_path, 'wb') as pdf_file:
                            pdf_file.write(pdf_content)
                        return self.pdf_path
        return None

    def delete_files(self):
        """Deletes the attachment and PDF files associated from the local env."""
        for file in (self.attachment_path, self.pdf_path):
            delete_file_if_exists(file)
