class FacturaCargadaSinExito(Exception):
    """Exception raised when the invoice was uploaded, but we got an error as response."""
    ...

class ServiceUnavailableError(Exception):
    """Exception raised when the response from an external api is under 500 status code."""

class DuplicatedRow(Exception):
    """Exception raised when the response from Supabase api is duplicated row."""