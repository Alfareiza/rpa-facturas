from decouple import config, Csv

# Business
LOGI_NIT = config('LOGI_NIT')
USER_ID = config('USER_ID')
USERNAME = config('LOGI_NIT')
MUTUALSER_USERNAME = config('MUTUALSER_USERNAME')
MUTUALSER_PASSWORD = config('MUTUALSER_PASSWORD')

# Web
BASE_URL_AUTH = config('BASE_URL_AUTH')
BASE_URL_API = config('BASE_URL_API')
PORTAL_URL = config('PORTAL_URL')

# External Services
GOOGLE_TOKEN = config('GOOGLE_TOKEN')
GOOGLE_REFRESH_TOKEN = config('GOOGLE_REFRESH_TOKEN')
GOOGLE_TOKEN_URI = config('GOOGLE_TOKEN_URI')
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET')
GOOGLE_SCOPES = config('GOOGLE_SCOPES', cast=Csv())

# Spreadsheets
SPREADSHEET_ID = config('SPREADSHEET_ID')

# Drive
FACTURAS_PDF = config('FACTURAS_PDF')
FACTURAS_PROCESADAS = config('FACTURAS_PROCESADAS')
FACTURAS_TMP = config('FACTURAS_TMP')


class Reasons:
    FILE_NOT_FOUND_MUTUAL_SER = 'Archivo no encontrado al intentar ser enviado a Mutualser'
    UPLOADED_MUTUAL_SER = 'Cargado en Mutual Ser'
    INVOCE_UPLOADED_WITH_ERROR = 'Factura NO CARGADA en Mutual Ser'


class Subjects:
    BASIC = "{nro_factura} - Error cargando factura en Mutual Ser"
    INCONSISTENCY_TOTAL_INVOICE = "{nro_factura} - Inconsistencia en valor total de la factura"
    RETRY_FAILED = "{nro_factura} - No se pudo cargar la factura después de varios intentos"

    @classmethod
    def define_subject(cls, nro_factura: str, reason: str):
        """Determines the appropriate subject line for a notification email based on the invoice number and reason.

        Returns a formatted subject string that reflects the context of the invoice error or inconsistency.

        Args:
            nro_factura (str): The invoice number.
            reason (str): The reason for the notification.

        Returns:
            str: The formatted subject line for the email.
        """
        if 'corresponde al valor total del servicio' in reason.lower():
            return cls.INCONSISTENCY_TOTAL_INVOICE.format(nro_factura=nro_factura)
        if 'intentos, no se cargó la factura' in reason.lower():
            return cls.RETRY_FAILED.format(nro_factura=nro_factura)
        return cls.BASIC.format(nro_factura=nro_factura)


class Emails:
    LOGIFARMA_ADMIN = config('LOGIFARMA_ADMIN')
    LOGIFARMA_DEV = config('LOGIFARMA_DEV')
