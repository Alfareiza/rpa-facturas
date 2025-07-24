from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, HttpUrl, RootModel
from datetime import datetime
from uuid import UUID


class Mensaje(BaseModel):
    codigo: str
    descripcion: str
    tipo: str
    idArchivo: UUID

    @property
    def simplified_description(self) -> str:
        """
        Returns the description with any full file path simplified to just the filename.

        For example, a description like: "El archivo /path/to/file.zip no contiene PDF."
        becomes:
        "El archivo file.zip no contiene PDF."
        """
        # The original `desc` property was incomplete. This implementation
        # provides a clean, readable version of the description string.
        words = self.descripcion.split(' ')
        new_words = [Path(word).name if '/' in word or '\\' in word else word for word in words]
        return ' '.join(new_words)


class Archivo(BaseModel):
    codigo: str
    estado: str
    extension: str
    fechaCargue: datetime
    id: UUID
    idTipo: UUID
    mensajes: List[Mensaje]
    nombre: str

    @property
    def cargado(self):
        return self.estado == 'CARGADO'

    @property
    def error(self):
        if self.mensajes and (mensaje := self.mensajes[0]):
            return mensaje.tipo == 'ERROR'

    @property
    def motivo_error(self) -> str:
        if self.mensajes:
            return '| '.join([f"{mensaje.codigo}. {mensaje.simplified_description}" for mensaje in self.mensajes])
        return ""

    def exitoso(self):
        if self.mensajes and (mensaje := self.mensajes[0]):
            return mensaje.tipo == ''

    @property
    def sin_errores(self) -> bool:
        """If there is at least one message in self.messages then there is an error on the uploaded invoice."""
        return not bool(self.mensajes)


class FindLoadResponse(BaseModel):
    """Respuesta de petición GET a endpoint /mutual-api-rfds/api/v1/rips-api/findLoad"""
    archivos: List[Archivo]
    cantidad: int
    email: str
    estado: str
    estadoValidaciones: Optional[str]
    fecha: datetime
    id: UUID
    nombres: List[str]
    organizacion: str
    usuario: str
    nombreOrganizacion: Optional[str]

    @property
    def cargue_id(self):
        return str(self.id) if self.id else ""

    @property
    def primer_archivo(self):
        return self.archivos[0]

    @property
    def cargado_exitoso(self) -> bool:
        """Given the messages of the archivos, it determines if the upload was successful."""
        if self.archivos and self.unico_archivo.sin_errores:
            return True
        return False

    @property
    def estado_basado_en_archivos(self):
        """Busca el estado en el primer archivo de los archivos, y si no hay archivos, entonces retorna el estado encontrado en el root de la respuesta."""
        if self.archivos:
            return self.primer_archivo.estado
        return self.estado

    @property
    def done(self):
        if self.archivos:
            return self.primer_archivo.cargado
        return False

    @property
    def unico_archivo(self):
        return self.primer_archivo


class FileLinkResponse(RootModel[dict[str, HttpUrl]]):
    """Respuesta de petición GET a endpoint /mutual-api-rfds/api/v1/rips-api/signedUrl/getUrlUploadFile"""
    pass


class FileLinkRequest(BaseModel):
    """Petición GET a endpoint /mutual-api-rfds/api/v1/rips-api/signedUrl/getUrlUploadFile"""
    fileNames: str


class UploadFilesRequest(BaseModel):
    codigo: str
    mensajes: List[str]  # assuming mensajes is a list of strings (empty in your sample)
    id_archivo: UUID
    id_cargue: UUID
    extension: str
    tamano: float
    id_tipo: UUID
    nombre: str
