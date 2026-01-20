from datetime import datetime
from http.client import HTTPException
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from pytz import timezone

from src.config import log
from src.constants import Reasons, Emails, Subjects, EMAILS_PER_EXECUTION
from src.decorators import production_only
from src.models.general import Run, Record
from src.models.google import EmailMessage
from src.models.mutualser import FindLoadResponse
from src.resources.datetimes import colombia_now, diff_dates
from src.resources.exceptions import FacturaCargadaSinExito
from src.resources.files import File
from src.services.drive import GoogleDrive, GoogleDriveLogistica
from src.services.gmail import GmailAPIReader
from src.services.mutualser import MutualSerAPIClient
from src.services.sheets import GSpreadSheets


class Process:
    """
    Orchestrates the entire process of reading invoices from Gmail, uploading them to the Mutualser API,
    and logging the results.
    """

    def __init__(self):
        """
        Initializes the services required for the process and a Run object to track the execution.
        """
        self.run = Run()
        self.gmail = GmailAPIReader()
        self.drive = GoogleDrive()
        self.drive_logistica = GoogleDriveLogistica()
        self.gs = GSpreadSheets()
        self.mutualser_client = MutualSerAPIClient()

    def read_lines_to_list(self, file_path: str | Path) -> list[str]:
        """Read a text file and return a list where each line is an item.

        Strips trailing newline characters and ignores empty lines.
        """
        path = Path(file_path)

        with path.open(encoding="utf-8") as file:
            return [line.strip() for line in file if line.strip()]

    def append_line_to_file(self, file_path: str | Path, value: str) -> None:
        """Append a single line to the end of a text file.

        Automatically adds a newline before the value if needed.
        """
        path = Path(file_path)

        with path.open("a", encoding="utf-8") as file:
            file.write(f"{value}\n")

    def get_emails(self):
        """
        A generator that fetches unread emails from the inbox, downloads their attachments,
        and yields EmailMessage objects for further processing.
        """
        messages = self.gmail.read_inbox(EMAILS_PER_EXECUTION)
        # read_lines_to_list = set(self.read_lines_to_list("/Users/alfonso/Projects/rpa-facturas/processed.txt"))
        for idx, message in enumerate(messages, 1):
            log.info(f"{idx}. {message.id} INICIANDO Leyendo e-mail y descargando adjunto")
            self.gmail.fetch_email_details(message)
            # if message.nro_factura in read_lines_to_list:
            #     log.info(f"{idx}. {message.id} Factura {message.nro_factura} procesada anteriormente, omitiendola")
            #     continue
            self.run.record[message.nro_factura] = Record(email=message)
            self.gmail.download_attachment(message)
            yield message

    def send_invoice_to_mutual_ser(self, zip_file: Path, nro_factura: str):
        """
        Uploads the invoice file attached to an email to the Mutualser API.

        Args:
            zip_file: File path to be updated to mutual ser portal.
            nro_factura: Invoice number.

        Raises:
            FacturaCargadaSinExito: If the upload to the Mutualser API fails.
        """
        response: FindLoadResponse = self.mutualser_client.upload_file(zip_file)
        self.run.record[nro_factura].response_mutualser = response
        if not response.cargado_exitoso:
            raise FacturaCargadaSinExito(response.unico_archivo.motivo_error)

    def process_xmls_and_pdf(self, message: EmailMessage):
        """Perform the next actions:
        1. Upload .zip to temp folder on Google Drive.
        2. Unzip files resulting a .pdf and a .xml files.
        3. Rename .xml and .pdf files to respective names.
        4. Update .xml file based on business logic.
        5. Create folder on Google Drive if it doesn't exist.
        6. Upload .pdf on "Procesados" folder.
        7. Upload .xml on folder of the month based on invoice date.
        """
        try:
            zip_temp = self.upload_file_to_drive(message.attachment_path, folder='TMP')
            xml_file, pdf_file = self.unzip_files(message.attachment_path)
            xml_file = xml_file.rename(xml_file.parent / f"{message.nro_factura}_{xml_file.stem}.xml")
            pdf_file = pdf_file.rename(pdf_file.parent / f"{message.nro_factura}_{message.valor_factura}.pdf")
            xml_file = File(xml_file).update_invoice()
            folder_name = self.drive.get_facturas_mes_name(message.received_at.date().month,
                                                           message.received_at.date().year)
            self.upload_file_to_drive(pdf_file, folder='PROCESADOS')
            self.upload_file_to_drive(xml_file, folder=folder_name)
        except Exception as e:
            import traceback;
            traceback.print_exc()
            log.error(str(e))
        finally:
            self.drive.delete_file(zip_temp)


    def read_email_send_invoice(self):
        """
        Main workflow that iterates through emails from the inbox, attempts to upload the invoice for each,
        and handles the outcome. Successful uploads are finalized, and failures are logged.
        """
        for idx, message in enumerate(self.get_emails(), 1):
            try:
                log.info(f"{idx}. {message.id} {message.nro_factura} {message.fecha_factura} Enviando a Mutualser")
                # self.send_invoice_to_mutual_ser(message.attachment_path, message.nro_factura)
            except FileNotFoundError:
                self.post_exception(message, Reasons.FILE_NOT_FOUND_MUTUAL_SER)
            except FacturaCargadaSinExito as e:
                self.post_exception(message, str(e))
            except Exception as e:
                self.post_exception(message, f"{str(type(e))}: {str(e)}")
            else:
                self.finish(idx, message)
            finally:
                message.delete_files()
                log.info(f"{20 * '=='}\n")

    def finish(self, idx: int, message: EmailMessage):
        """
        Execute some operations as part of the finished process of upload the invoice into customer api.
        1. Mark e-mail as read.
        2. Upload the invoice to Google Drive.
        3. Set the status for report purposes.
        """
        log.info(f"{idx}. {message.id} {message.nro_factura}_{message.valor_factura}.pdf siendo cargado en Drive")
        # self.gmail.mark_as_read(message.id)
        self.run.record[message.nro_factura].status = Reasons.UPLOADED_MUTUAL_SER
        # self.drive.upload_file(message.extract_and_rename_pdf(), self.drive.facturas_pdf)
        self.process_xmls_and_pdf(message)
        self.append_line_to_file("/Users/alfonso/Projects/rpa-facturas/processed.txt", message.nro_factura)
        log.info(f"{idx}. {message.id} {message.nro_factura} {message.fecha_factura} FINALIZADO")

    def post_exception(self, message: EmailMessage, reason: str):
        """Operations to be executed when an exception is raised.

        :param message: EmailMessage object containing the invoice information.
        :param reason: Specific reason of failure.
        """
        self.run.record[message.nro_factura].status = Reasons.INVOCE_UPLOADED_WITH_ERROR
        self.run.record[message.nro_factura].errors.append(reason)
        self.send_mail(message, reason)

    def send_mail(self, message: EmailMessage, reason: str):
        """Send the email notifying the issue with the invoice."""
        subject = Subjects.define_subject(message.nro_factura, reason, message.fecha_factura)
        bcc = '' if 'inconsistencia en el valor total' in subject else None
        try:
            self.gmail.send_email(to=Emails.LOGIFARMA_ADMIN,
                              bcc=bcc,
                              subject=subject,
                              body_vars={'nro_factura': message.nro_factura, 'reason': reason,
                                         'fecha_factura': message.fecha_factura},
                              attachment_file=message.attachment_path)
        except HttpError as e:
            log.warning(f"{message.nro_factura} No fue posible enviar correo {subject!r} por error: {str(e)}")
        else:
            log.info(f"{message.nro_factura} E-mail enviado notificando incosistencia: {reason}")

    @production_only
    def register_in_sheets(self):
        """
        Converts the execution data from the run into a pandas DataFrame and inserts it into a Google Sheet.
        This method is decorated to run only in a production environment.
        """
        df = self.run.make_df()
        self.gs.insert_dataframe(df)


    def unzip_files(self, zip_file: Path) -> tuple[Path, Path]:
        """Return the paths of the unzipped file which is on temporary folder."""
        files = File(zip_file).unzip()
        return files['xml'], files['pdf']

    def upload_file_to_drive(self, file: Path, folder: str):
        """Upload zip file to Google Drive"""
        match folder:
            case 'TMP':
                file_id = self.drive.upload_file(file, self.drive.temp)
            case 'PROCESADOS':
                file_id = self.drive.upload_file(file, self.drive.facturas_pdf)
            case _:
                folder_id = self.drive_logistica.create_or_get_folder_id(folder)
                file_id = self.drive.upload_file(file, folder_id)
        return file_id.get('id')



def run_process():
    """
    Main execution function that orchestrates the entire process.
    This is the function that will be scheduled by Rocketry.
    """
    moment = colombia_now()
    # Executed from Monday to Saturday, from 6:00:00 up to 20:59:59
    if moment.isoweekday() == 7 or moment.hour > 20 and moment.minute >= 0 or moment.hour < 6:
        log.info(f"SCHEDULER: Procesamiento de facturas deshabilitado en este horario ({moment:%D %r})")
    else:
        log.info("SCHEDULER: Iniciando nuevo procesamiento de facturas.")
        p = Process()
        try:
            p.read_email_send_invoice()
        except Exception as e:
            import traceback

            traceback.print_exc()

        try:
            p.register_in_sheets()
        except Exception as e:
            import traceback

            traceback.print_exc()
        ordered_records = p.run.order_by_fecha_factura()
        if ordered_records:
            last_record = ordered_records[0]
            first_record = ordered_records[-1]
            log.info(f"REPORT: Primera Factura fue {first_record[0]} del {first_record[1].email.momento_factura}.")
            log.info(f"REPORT: Última Factura fue {last_record[0]} del {last_record[1].email.momento_factura}.")
        log.info(f"REPORT: Comenzó a las {moment:%T} y le tomó {diff_dates(moment, colombia_now())} procesar"
                 f" {len(ordered_records)} correos.")


if __name__ == '__main__':
    # for i, (nro, record) in enumerate(p.run.record.items(), 1):
    #     print(f"{i}. {nro}: {record.email.subject}")
    run_process()
    # scheduler = BlockingScheduler()
    # scheduler.add_job(run_process, 'interval', minutes=60, id='invoice_processing_job')
    # try:
    #     scheduler.start()
    # except (KeyboardInterrupt, SystemExit):
    #     log.info("Scheduler stopped by user.")
    #     scheduler.shutdown()
