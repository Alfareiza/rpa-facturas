
import unittest
from unittest.mock import Mock, patch
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import HttpUrl

from src.models.mutualser import Mensaje, Archivo, FindLoadResponse, FileLinkResponse, FileLinkRequest, UploadFilesRequest


class TestMensaje(unittest.TestCase):

    class TestSimplifiedDescription(unittest.TestCase):

        def test_simplifies_unix_path(self):
            mensaje = Mensaje(
                codigo="1",
                descripcion="El archivo /path/to/file.zip no contiene PDF.",
                tipo="ERROR",
                idArchivo=uuid4()
            )
            self.assertEqual(mensaje.simplified_description, "El archivo file.zip no contiene PDF.")

        def test_simplifies_windows_path(self):
            mensaje = Mensaje(
                codigo="1",
                descripcion=r"El archivo C:\Users\Test\file.zip no contiene PDF.",
                tipo="ERROR",
                idArchivo=uuid4()
            )
            self.assertEqual(mensaje.simplified_description, "El archivo file.zip no contiene PDF.")

        def test_no_path_in_description(self):
            descripcion = "Descripción sin ruta de archivo."
            mensaje = Mensaje(
                codigo="2",
                descripcion=descripcion,
                tipo="INFO",
                idArchivo=uuid4()
            )
            self.assertEqual(mensaje.simplified_description, descripcion)


class TestArchivo(unittest.TestCase):

    class TestCargado(unittest.TestCase):

        def test_cargado_true(self):
            archivo = Archivo(estado='CARGADO', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1', mensajes=[])
            self.assertTrue(archivo.cargado)

        def test_cargado_false(self):
            archivo = Archivo(estado='PENDIENTE', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1', mensajes=[])
            self.assertFalse(archivo.cargado)

    class TestError(unittest.TestCase):

        def test_error_true(self):
            mensaje = Mensaje(tipo='ERROR', codigo='1', descripcion='error', idArchivo=uuid4())
            archivo = Archivo(mensajes=[mensaje], estado='ERROR', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1')
            self.assertTrue(archivo.error)

        def test_error_false(self):
            mensaje = Mensaje(tipo='EXITOSO', codigo='0', descripcion='exitoso', idArchivo=uuid4())
            archivo = Archivo(mensajes=[mensaje], estado='CARGADO', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1')
            self.assertFalse(archivo.error)

    class TestMotivoError(unittest.TestCase):

        def test_motivo_error_single(self):
            mensaje = Mensaje(tipo='ERROR', codigo='E1', descripcion='Error 1', idArchivo=uuid4())
            archivo = Archivo(mensajes=[mensaje], estado='ERROR', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1')
            self.assertEqual(archivo.motivo_error, "E1. Error 1")

        def test_motivo_error_multiple(self):
            mensaje1 = Mensaje(tipo='ERROR', codigo='E1', descripcion='Error 1', idArchivo=uuid4())
            mensaje2 = Mensaje(tipo='ERROR', codigo='E2', descripcion='Error 2', idArchivo=uuid4())
            archivo = Archivo(mensajes=[mensaje1, mensaje2], estado='ERROR', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1')
            self.assertEqual(archivo.motivo_error, "E1. Error 1| E2. Error 2")

    class TestExitoso(unittest.TestCase):

        def test_exitoso_true(self):
            mensaje = Mensaje(tipo='', codigo='0', descripcion='exitoso', idArchivo=uuid4())
            archivo = Archivo(mensajes=[mensaje], estado='CARGADO', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1')
            self.assertTrue(archivo.exitoso())

        def test_exitoso_false(self):
            mensaje = Mensaje(tipo='ERROR', codigo='1', descripcion='error', idArchivo=uuid4())
            archivo = Archivo(mensajes=[mensaje], estado='ERROR', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1')
            self.assertFalse(archivo.exitoso())

    class TestMensajesExitosos(unittest.TestCase):

        def test_mensajes_exitosos_true(self):
            mensaje = Mensaje(tipo='EXITOSO', codigo='0', descripcion='exitoso', idArchivo=uuid4())
            archivo = Archivo(mensajes=[mensaje], estado='CARGADO', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1')
            self.assertTrue(archivo.sin_errores())

        def test_mensajes_exitosos_false(self):
            mensaje = Mensaje(tipo='ERROR', codigo='1', descripcion='error', idArchivo=uuid4())
            archivo = Archivo(mensajes=[mensaje], estado='ERROR', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1')
            self.assertFalse(archivo.sin_errores())


class TestFindLoadResponse(unittest.TestCase):

    class TestPrimerArchivo(unittest.TestCase):

        def test_primer_archivo(self):
            archivo = Archivo(estado='CARGADO', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1', mensajes=[])
            response = FindLoadResponse(archivos=[archivo], cantidad=1, email='test@test.com', estado='test', fecha=datetime.now(), id=uuid4(), nombres=['test'], organizacion='test', usuario='test')
            self.assertEqual(response.primer_archivo, archivo)

    class TestCargadoExitoso(unittest.TestCase):

        @patch('src.models.mutualser.Archivo.sin_errores', new_callable=Mock)
        def test_cargado_exitoso_true(self, mock_mensajes_exitosos):
            mock_mensajes_exitosos.return_value = True
            archivo = Archivo(estado='CARGADO', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1', mensajes=[])
            archivo.mensajes_exitosos = True
            response = FindLoadResponse(archivos=[archivo], cantidad=1, email='test@test.com', estado='test', fecha=datetime.now(), id=uuid4(), nombres=['test'], organizacion='test', usuario='test')
            self.assertTrue(response.cargado_exitoso)

    class TestEstadoBasadoEnArchivos(unittest.TestCase):

        def test_estado_from_archivo(self):
            archivo = Archivo(estado='CARGADO', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1', mensajes=[])
            response = FindLoadResponse(archivos=[archivo], cantidad=1, email='test@test.com', estado='PENDIENTE', fecha=datetime.now(), id=uuid4(), nombres=['test'], organizacion='test', usuario='test')
            self.assertEqual(response.estado_basado_en_archivos, 'CARGADO')

        def test_estado_from_root(self):
            response = FindLoadResponse(archivos=[], cantidad=0, email='test@test.com', estado='PENDIENTE', fecha=datetime.now(), id=uuid4(), nombres=['test'], organizacion='test', usuario='test')
            self.assertEqual(response.estado_basado_en_archivos, 'PENDIENTE')

    class TestDone(unittest.TestCase):

        def test_done_true(self):
            archivo = Archivo(estado='CARGADO', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1', mensajes=[])
            response = FindLoadResponse(archivos=[archivo], cantidad=1, email='test@test.com', estado='test', fecha=datetime.now(), id=uuid4(), nombres=['test'], organizacion='test', usuario='test')
            self.assertTrue(response.done)

        def test_done_false(self):
            archivo = Archivo(estado='PENDIENTE', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1', mensajes=[])
            response = FindLoadResponse(archivos=[archivo], cantidad=1, email='test@test.com', estado='test', fecha=datetime.now(), id=uuid4(), nombres=['test'], organizacion='test', usuario='test')
            self.assertFalse(response.done)

    class TestUnicoArchivo(unittest.TestCase):

        def test_unico_archivo(self):
            archivo = Archivo(estado='CARGADO', id=uuid4(), idTipo=uuid4(), fechaCargue=datetime.now(), nombre='test', extension='zip', codigo='1', mensajes=[])
            response = FindLoadResponse(archivos=[archivo], cantidad=1, email='test@test.com', estado='test', fecha=datetime.now(), id=uuid4(), nombres=['test'], organizacion='test', usuario='test')
            self.assertEqual(response.unico_archivo, archivo)


class TestFileLinkResponse(unittest.TestCase):

    def test_instantiation(self):
        url = HttpUrl('https://example.com')
        response = FileLinkResponse.model_validate({'file.zip': url})
        self.assertEqual(response.root['file.zip'], url)


class TestFileLinkRequest(unittest.TestCase):

    def test_instantiation(self):
        request = FileLinkRequest(fileNames='test.zip')
        self.assertEqual(request.fileNames, 'test.zip')


class TestUploadFilesRequest(unittest.TestCase):

    def test_instantiation(self):
        request = UploadFilesRequest(
            codigo='1',
            mensajes=[],
            id_archivo=uuid4(),
            id_cargue=uuid4(),
            extension='zip',
            tamano=123.45,
            id_tipo=uuid4(),
            nombre='test.zip'
        )
        self.assertEqual(request.nombre, 'test.zip')

if __name__ == '__main__':
    unittest.main()
