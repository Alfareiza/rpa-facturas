from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from pytz import timezone

from src.config import log
from src.constants import Reasons, Emails, Subjects
from src.decorators import production_only
from src.models.general import Run, Record
from src.models.google import EmailMessage
from src.models.mutualser import FindLoadResponse
from src.resources.datetimes import colombia_now, diff_dates
from src.resources.exceptions import FacturaCargadaSinExito
from src.services.drive import GoogleDrive
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
        self.gs = GSpreadSheets()
        self.mutualser_client = MutualSerAPIClient()

    def get_emails(self):
        """
        A generator that fetches unread emails from the inbox, downloads their attachments,
        and yields EmailMessage objects for further processing.
        """
        messages = self.gmail.read_inbox(200)
        for message in messages:
            log.info(f"{message.id} INICIANDO Leyendo e-mail y descargando adjunto")
            self.gmail.fetch_email_details(message)
            self.run.record[message.nro_factura] = Record(email=message)
            self.gmail.download_attachment(message)
            yield message

    def send_invoice_to_mutual_ser(self, message: EmailMessage):
        """
        Uploads the invoice file attached to an email to the Mutualser API.

        Args:
            message: The EmailMessage object containing the invoice attachment.

        Raises:
            FacturaCargadaSinExito: If the upload to the Mutualser API fails.
        """
        response: FindLoadResponse = self.mutualser_client.upload_file(message.attachment_path)
        self.run.record[message.nro_factura].response_mutualser = response
        if not response.cargado_exitoso:
            raise FacturaCargadaSinExito(response.unico_archivo.motivo_error)

    def read_email_send_invoice(self):
        """
        Main workflow that iterates through emails from the inbox, attempts to upload the invoice for each,
        and handles the outcome. Successful uploads are finalized, and failures are logged.
        """
        for idx, message in enumerate(self.get_emails(), 1):
            try:
                log.info(f"{message.id} {message.nro_factura} {message.fecha_factura} {idx} Enviando a Mutualser")
                self.send_invoice_to_mutual_ser(message)
            except FileNotFoundError:
                self.post_exception(message, Reasons.FILE_NOT_FOUND_MUTUAL_SER)
            except FacturaCargadaSinExito as e:
                self.post_exception(message, str(e))
            except Exception as e:
                self.post_exception(message, str(e))
            else:
                self.finish(message)
            finally:
                message.delete_files()
                log.info(f"{20 * '=='}\n")

    def finish(self, message: EmailMessage):
        """
        Execute some operations as part of the finished process of upload the invoice into customer api.
        1. Mark e-mail as read.
        2. Upload the invoice to Google Drive.
        3. Set the status for report purposes.
        """
        log.info(f"{message.id} {message.nro_factura}_{message.valor_factura}.pdf siendo cargado en Drive")
        self.gmail.mark_as_read(message.id)
        self.run.record[message.nro_factura].status = Reasons.UPLOADED_MUTUAL_SER
        self.drive.upload_file(message.extract_and_rename_pdf(), self.drive.facturas_pdf)
        log.info(f"{message.id} {message.nro_factura} {message.fecha_factura} FINALIZADO")

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
        # bcc = '' if 'inconsistencia en valor total' in subject else None
        self.gmail.send_email(to=Emails.LOGIFARMA_ADMIN,
                              # bcc=bcc,
                              subject=subject,
                              body_vars={'nro_factura': message.nro_factura, 'reason': reason,
                                         'fecha_factura': message.fecha_factura},
                              attachment_file=message.attachment_path)
        log.info(f"{message.nro_factura} E-mail enviado notificando incosistencia: {reason}")

    @production_only
    def register_in_sheets(self):
        """
        Converts the execution data from the run into a pandas DataFrame and inserts it into a Google Sheet.
        This method is decorated to run only in a production environment.
        """
        df = self.run.make_df()
        self.gs.insert_dataframe(df)


def run_process():
    """
    Main execution function that orchestrates the entire process.
    This is the function that will be scheduled by Rocketry.
    """
    moment = colombia_now()
    if moment.hour > 20 and moment.minute >= 0 or moment.hour < 6:
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
        first_record = ordered_records[0]
        last_record = ordered_records[-1]
        log.info(f"SCHEDULER: Primera Factura fue {first_record[0]} del {first_record[1].email.momento_factura}.")
        log.info(f"SCHEDULER: Última Factura fue {last_record[0]} del {last_record[1].email.momento_factura}.")
        log.info(f"SCHEDULER: Procesamiento de facturas finalizado en {diff_dates(moment, colombia_now())}.")


if __name__ == '__main__':
    # for i, (nro, record) in enumerate(p.run.record.items(), 1):
    #     print(f"{i}. {nro}: {record.email.subject}")
    # run_process()
    scheduler = BlockingScheduler()
    scheduler.add_job(run_process, 'interval', minutes=60, id='invoice_processing_job')
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped by user.")
        scheduler.shutdown()
