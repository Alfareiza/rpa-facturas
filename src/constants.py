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

class Emails:
    LOGIFARMA_ADMIN = config('LOGIFARMA_ADMIN')
    LOGIFARMA_DEV = config('LOGIFARMA_DEV')