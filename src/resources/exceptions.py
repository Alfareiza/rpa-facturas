class FacturaCargadaSinExito(Exception):
    """Exception raised when the invoice was uploaded, but we got an error as response."""
    ...

class ServiceUnavailableError(Exception):
    """Exception raised when the response from an external api is under 500 status code."""

class DuplicatedRow(Exception):
    """Exception raised when the response from Supabase"""

class TimeoutMutualSer(Exception):
    """Exception raised when uploading the file to Mutualser, the timeout was fired."""

class CamposRequeridos(Exception):
    """Exception raised when api returns \'El archivo XML no contiene los campos requeridos en el nodo de sector salud exigido por la Resolución 948 de 2026.\'"""

class NoMatchesEmails(Exception):
    """Exception raised when read the e-mail there is no matches."""