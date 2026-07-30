from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import sys

from src.config import log
from src.constants import EMAILS_PER_EXECUTION, Reasons
from src.models.general import Record
from src.models.google import EmailMessage
from src.resources.exceptions import DuplicatedRow, FacturaCargadaSinExito, TimeoutMutualSer
from src.resources.log_buffer import InvoiceLogManager
from src.services.drive import GoogleDrive, GoogleDriveLogistica
from src.services.gmail import GmailAPIReader
from src.services.mutualser import MutualSerAPIClient


@dataclass(frozen=True)
class WorkItem:
    idx: int
    message: EmailMessage


@dataclass(frozen=True)
class CompletedItem:
    idx: int
    message: EmailMessage
    success: bool
    error_reason: Optional[str] = None


class InvoicePipeline:
    """
    Bounded, thread-based pipeline:
      - Fetch stage: Gmail details + attachment download (parallel)
      - Process stage: Drive/unzip/update/upload (parallel)
      - Mutualser stage: upload (single worker)

    Logs are buffered per idx and flushed strictly in idx order with no interleaving.
    """

    def __init__(
        self,
        process: "ProcessLike",
        *,
        emails_limit: int = EMAILS_PER_EXECUTION,
        fetch_workers: int = 10,
        process_workers: int = 10,
        mutual_workers: int = 3,
        fetch_queue_size: int = 50,
        process_queue_size: int = 50,
        mutual_queue_size: int = 50,
    ) -> None:
        """
        Create a new pipeline instance.

        Args:
            process: Orchestrator object (the `Process` instance) that provides the concrete
                business operations (`process_xmls_and_pdf`, `send_invoice_to_mutual_ser`, etc.).
            emails_limit: Max unread emails to load from Gmail for this run.
            fetch_workers: Number of parallel workers for Gmail detail + attachment download.
            process_workers: Number of parallel workers for Drive/unzip/update/upload work.
            mutual_workers: Number of parallel workers for Mutualser uploads (funnel stage).
            fetch_queue_size: Backpressure limit between list stage and fetch stage.
            process_queue_size: Backpressure limit between fetch stage and drive stage.
            mutual_queue_size: Backpressure limit between drive stage and mutualser funnel stage.
        """
        self._process = process
        self._emails_limit = emails_limit
        self._fetch_workers = fetch_workers
        self._process_workers = process_workers
        self._mutual_workers = mutual_workers
        self._fetch_q: queue.Queue[Optional[WorkItem]] = queue.Queue(maxsize=fetch_queue_size)
        self._process_q: queue.Queue[Optional[WorkItem]] = queue.Queue(maxsize=process_queue_size)
        self._mutual_q: queue.Queue[Optional[WorkItem]] = queue.Queue(maxsize=mutual_queue_size)
        self._completed: dict[int, CompletedItem] = {}
        self._completed_lock = threading.Lock()

        fmt = logging.Formatter(
            "%(asctime)s - %(levelname)-7s [%(filename)-13s:%(lineno)03d - %(funcName)30s()] - %(message)s"
        )
        self._log_mgr = InvoiceLogManager(formatter=fmt)
        self._progress = logging.getLogger("pipeline_progress")
        self._progress.propagate = False
        self._progress.setLevel(logging.INFO)
        if not self._progress.handlers:
            ph = logging.StreamHandler(sys.stdout)
            ph.setFormatter(fmt)
            self._progress.addHandler(ph)

    def run(self) -> None:
        """
        Execute the pipeline end-to-end.

        Installs the per-invoice log buffering handler and guarantees that buffered logs
        are flushed contiguously and in deterministic `idx` order (no interleaving).
        """
        self._log_mgr.install()
        try:
            self._run_inner()
        finally:
            self._log_mgr.uninstall()

    def _run_inner(self) -> None:
        """
        Internal runner: list messages, start workers, feed queues, and wait for completion.

        This method enforces the stage boundaries:
        - fetch workers terminate before process workers are stopped
        - mutual worker is stopped last
        - log flush thread drains buffers strictly from idx=1..N
        """
        lister = GmailAPIReader()
        messages = lister.read_inbox(self._emails_limit)
        total = len(messages)
        self._progress.info(f"PIPELINE: {total} correos encontrados para procesar.")
        if total == 0:
            return

        # Start flusher thread first; it will block waiting for readiness.
        flush_thread = threading.Thread(
            target=self._log_mgr.flusher.flush_ready_in_order, args=(total,), daemon=True
        )
        flush_thread.start()

        fetch_threads = [
            threading.Thread(target=self._fetch_worker, args=(total,), daemon=True)
            for _ in range(self._fetch_workers)
        ]
        process_threads = [
            threading.Thread(target=self._process_worker, args=(total,), daemon=True)
            for _ in range(self._process_workers)
        ]
        mutual_threads = [
            threading.Thread(target=self._mutual_worker, args=(total,), daemon=True)
            for _ in range(self._mutual_workers)
        ]

        for t in fetch_threads + process_threads + mutual_threads:
            t.start()

        # Enqueue work in deterministic order (idx = inbox order)
        for idx, msg in enumerate(messages, 1):
            self._fetch_q.put(WorkItem(idx=idx, message=msg))

        # Stop fetch workers
        for _ in fetch_threads:
            self._fetch_q.put(None)
        for t in fetch_threads:
            t.join()

        # Stop process workers
        for _ in process_threads:
            self._process_q.put(None)
        for t in process_threads:
            t.join()

        # Stop mutual worker
        for _ in mutual_threads:
            self._mutual_q.put(None)
        for t in mutual_threads:
            t.join()

        # By now all items should be marked ready; wait for flush completion.
        flush_thread.join()

    def _mark_completed(self, item: CompletedItem) -> None:
        """
        Mark an invoice as completed and release it for ordered log flushing.

        Args:
            item: Completion metadata (idx/message/success/reason).
        """
        with self._completed_lock:
            self._completed[item.idx] = item
        self._log_mgr.flusher.mark_ready(item.idx)

    def _fetch_worker(self, total: int) -> None:
        """
        Fetch worker loop.

        Each worker owns its own `GmailAPIReader` instance and consumes `WorkItem`s from
        the fetch queue, producing ready items onto the process queue.
        """
        gmail = GmailAPIReader()
        while True:
            item = self._fetch_q.get()
            if item is None:
                self._fetch_q.task_done()
                break
            with self._log_mgr.bind(item.idx):
                self._handle_fetch(gmail, item)
            self._fetch_q.task_done()

    def _handle_fetch(self, gmail: GmailAPIReader, item: WorkItem) -> None:
        """
        Fetch and validate per-email prerequisites.

        Steps:
        - dedupe guard (Record creation)
        - fetch Gmail metadata (subject/date/body)
        - download ZIP attachment to local temp path
        - register the Record in the shared `Run` object

        On success, pushes the item to the process queue. On failure, records the error,
        triggers exception handling, and marks the item completed for log flushing.
        """
        message = item.message
        try:
            try:
                record = Record(email=message)
            except DuplicatedRow:
                log.info(f"{item.idx}. {message.id} Procesado anteriormente")
                self._mark_completed(
                    CompletedItem(idx=item.idx, message=message, success=False, error_reason="Procesado anteriormente")
                )
                return

            gmail.fetch_email_details(message)
            if not message.nro_factura:
                raise ValueError("No se pudo extraer nro_factura del subject.")

            log.info(f"{10 * '⬇️'} INICIO FACTURA {message.nro_factura} {10 * '⬇️'}")
            with self._process.run_lock:
                self._process.run.record[message.nro_factura] = record

            gmail.download_attachment(message)
            if not message.attachment_path:
                raise FileNotFoundError("No se encontró adjunto ZIP en el correo.")

            self._process_q.put(item)
        except Exception as e:
            # Route to completion with exception semantics
            reason = f"{str(type(e))}: {str(e)}"
            self._process.post_exception(message, reason, gmail=gmail)
            self._mark_completed(CompletedItem(idx=item.idx, message=message, success=False, error_reason=reason))
            message.delete_files()

    def _process_worker(self, total: int) -> None:
        """
        Drive/process worker loop.

        Each worker owns its own Drive clients and performs the Drive/unzip/update/upload
        step before handing work off to the Mutualser funnel stage.
        """
        drive = GoogleDrive()
        drive_logistica = GoogleDriveLogistica()
        while True:
            item = self._process_q.get()
            if item is None:
                self._process_q.task_done()
                break
            with self._log_mgr.bind(item.idx):
                self._handle_process_drive(item, drive, drive_logistica)
            self._process_q.task_done()

    def _handle_process_drive(self, item: WorkItem, drive: GoogleDrive, drive_logistica: GoogleDriveLogistica) -> None:
        """
        Run Drive-related processing for a single invoice.

        On success, pushes the item to the Mutualser queue.
        On failure, triggers exception handling and completes the item.
        """
        message = item.message
        try:
            log.info(
                f"{item.idx}. {message.nro_factura} recibida el {message.fecha_correo_recibido}"
                f" XML y PDF siendo cargados al drive"
            )
            self._process.process_xmls_and_pdf(message, drive=drive, drive_logistica=drive_logistica)
            self._mutual_q.put(item)
        except Exception as e:
            reason = f"{str(type(e))}: {str(e)}"
            self._process.post_exception(message, reason)
            self._mark_completed(CompletedItem(idx=item.idx, message=message, success=False, error_reason=reason))
            message.delete_files()

    def _mutual_worker(self, total: int) -> None:
        """
        Mutualser funnel worker loop.

        Mutualser is kept as a *small* concurrency pool (default 2) to improve throughput
        while keeping a controlled funnel. Each worker uses its own `MutualSerAPIClient`
        session and `GmailAPIReader` to avoid cross-thread sharing of stateful clients.
        """
        mutual = MutualSerAPIClient()
        gmail = GmailAPIReader()
        while True:
            item = self._mutual_q.get()
            if item is None:
                self._mutual_q.task_done()
                break
            with self._log_mgr.bind(item.idx):
                self._handle_mutualser(item, mutual, gmail)
            self._mutual_q.task_done()

    def _handle_mutualser(self, item: WorkItem, mutual: MutualSerAPIClient, gmail: GmailAPIReader) -> None:
        """
        Upload a single invoice ZIP to Mutualser and finalize the email.

        Semantics:
        - On success: mark as read + set status, then mark completed
        - On failure: call `post_exception(...)` and mark completed
        - Always: emit final invoice boundary log and delete local temp files
        """
        message = item.message
        try:
            self._process.send_invoice_to_mutual_ser(message.attachment_path, message.nro_factura, client=mutual)
        except FileNotFoundError:
            self._process.post_exception(message, Reasons.FILE_NOT_FOUND_MUTUAL_SER, gmail=gmail)
            self._mark_completed(
                CompletedItem(idx=item.idx, message=message, success=False, error_reason=Reasons.FILE_NOT_FOUND_MUTUAL_SER)
            )
        except TimeoutMutualSer:
            self._process.post_exception(message, Reasons.INVOCE_UPLOADED_WITH_ERROR, gmail=gmail)
            self._mark_completed(
                CompletedItem(idx=item.idx, message=message, success=False, error_reason=Reasons.FILE_NOT_FOUND_MUTUAL_SER)
            )
        except FacturaCargadaSinExito as e:
            self._process.post_exception(message, str(e), gmail=gmail)
            self._mark_completed(CompletedItem(idx=item.idx, message=message, success=False, error_reason=str(e)))
        except Exception as e:
            reason = f"{str(type(e))}: {str(e)}"
            self._process.post_exception(message, reason, gmail=gmail)
            self._mark_completed(CompletedItem(idx=item.idx, message=message, success=False, error_reason=reason))
        else:
            self._process.finish(item.idx, message, gmail=gmail)
            self._mark_completed(CompletedItem(idx=item.idx, message=message, success=True))
        finally:
            log.info(f"{7 * '⬆️'}  FIN FACTURA {message.nro_factura} del {message.dt_factura_str} {7 * '⬆️'}\n")
            message.delete_files()


class ProcessLike:
    """
    Structural type used by the pipeline to avoid circular imports at runtime.
    The real `Process` in `src/main.py` matches this API.
    """

    run: object
    run_lock: threading.Lock

    def process_xmls_and_pdf(self, message: EmailMessage, *, drive: GoogleDrive, drive_logistica: GoogleDriveLogistica) -> None:
        """Process ZIP → XML/PDF and upload artifacts to Drive."""
        ...

    def send_invoice_to_mutual_ser(self, zip_file: Path, nro_factura: str, *, client: MutualSerAPIClient) -> None:
        """Upload the invoice ZIP to Mutualser using the provided client."""
        ...

    def finish(self, idx: int, message: EmailMessage, *, gmail: GmailAPIReader) -> None:
        """Finalize a successful invoice (e.g., mark email as read, update run status)."""
        ...

    def post_exception(self, message: EmailMessage, reason: str, *, gmail: Optional[GmailAPIReader] = None) -> None:
        """Finalize a failed invoice (e.g., update run status, send notification email)."""
        ...

