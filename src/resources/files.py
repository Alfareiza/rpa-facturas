import mimetypes

from src.config import log

import tempfile
import zipfile
from pathlib import Path

from src.resources.parser import XMLHealthInvoiceProcessor


class File:
    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)

    def unzip(self, extract_to=None):
        """Unzip the zip_file and return a Path object of the xml."""
        # If no path is provided, use the system's temp directory
        if extract_to is None:
            extract_to = Path(tempfile.gettempdir())
        # Use zipfile as a context manager
        with zipfile.ZipFile(self.file_path, 'r') as archive:
            # Find the first XML file in the list
            filenames = [f for f in archive.namelist() if f.lower().endswith('.xml') or f.lower().endswith('.pdf')]

            if not filenames:
                raise ValueError("No file found in the ZIP archive.")

            target_files = []
            for filename in filenames:
                # Extract only the XML file to the destination
                archive.extract(filename, path=extract_to)

            # Construct the full absolute path
            return {filename[-3:]: extract_to / Path(filename) for filename in filenames}

    def update_invoice(self):
        """Update the xml and zip it again."""
        processor = XMLHealthInvoiceProcessor(self.file_path)
        processor.process_all()
        return processor.save()


def delete_file_if_exists(file_path: Path):
    """
    Deletes a file if it exists, without raising an exception if the file doesn't exist.

    Args:
        file_path: The PosixPath object representing the file to delete.
    """
    try:
        if not file_path:
            return
        file_path.unlink(missing_ok=True)
    except OSError as e:
        # Log the error if needed, but don't re-raise as per requirement
        log.error(f"Error deleting file {file_path}: {e}")
    except Exception as e:
        log.error(f"Error unexpected deleting file {str(e)}")


def extract_nro_factura_from_file(file_path: Path) -> str:
    """
    Extracts the invoice number from a file name by splitting on the underscore character.

    Returns the first segment of the file name as the invoice number, or the full name if no underscore is present.

    Args:
        file_path: The PosixPath object representing the file.

    Returns:
        str: The extracted invoice number or the file name.
    """
    if not file_path:
        return ""

    if splitted_file_name := file_path.name.split('_'):
        return splitted_file_name[0]
    return file_path.name


def get_mime_type(path: Path) -> str | None:
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type

if __name__ == '__main__':
    file = File(Path('/Users/alfonso/Downloads/ArchivoEjemploIncorrecto_ad09000732230162500173a4e.xml'))
    file.update_invoice()
