import logging
from pathlib import Path

from decouple import config

BASE_DIR: Path = Path(__file__).resolve().parent.parent
_IN_PRODUCTION = config('PRODUCTION', default=False, cast=bool)
_TEST_MODE = config('TEST_MODE', default=False, cast=bool)

# format = r"%(asctime)s - %(levelname)-7s [%(filename)s:%(lineno)03d - %(funcName)34s()] - %(message)s"
format = r"%(asctime)s - %(levelname)-7s [%(filename)-25s:%(lineno)03d - %(funcName)30s()] - %(message)s"
logging.basicConfig(level=logging.INFO, format=format)
log = logging.getLogger(__name__)


class Config:
    """Static class container for all variables."""
    _BASE_DIR = Path(__file__).resolve().parent.parent

    class DIRECTORIES:
        """Container for any directories you require for your automation.

        Folders will be created automatically
        """

        TEMP = Path("/tmp")
        TEMP =  Path('/tmp')


CONFIG = Config()

if __name__ == '__main__':
    log.info('This is a sample')
    log.warning('This is a longer sample message to show alignment.')
