from pathlib import Path

from src.config import log


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

