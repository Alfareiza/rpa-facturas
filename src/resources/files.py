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
