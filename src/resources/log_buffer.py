from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Condition, Lock
from typing import Dict, Iterable, Iterator, List, Optional


_invoice_idx_var: ContextVar[Optional[int]] = ContextVar("invoice_idx", default=None)

_PASSTHROUGH_LOGGERS = {"invoice_flush", "pipeline_progress"}


class _DropBoundInvoiceLogsFilter(logging.Filter):
    """
    Filter attached to existing handlers to prevent duplicated output.

    If an invoice idx is bound (meaning we're inside a parallel invoice task), then the
    normal handlers should NOT emit that record. Instead, the record is buffered and later
    flushed contiguously by `OrderedLogFlusher`.

    We allow a small set of loggers to passthrough (progress + flusher).
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (name matches logging API)
        idx = _invoice_idx_var.get()
        if idx is None:
            return True
        return record.name in _PASSTHROUGH_LOGGERS


class PerInvoiceBufferHandler(logging.Handler):
    """
    Logging handler that buffers LogRecords per invoice idx.

    Records are grouped by the value in `_invoice_idx_var`.
    If no invoice idx is bound, the record is ignored by this handler.
    """

    def __init__(self, buffers: Dict[int, List[logging.LogRecord]], lock: Lock):
        super().__init__()
        self._buffers = buffers
        self._lock = lock

    def emit(self, record: logging.LogRecord) -> None:
        idx = _invoice_idx_var.get()
        if idx is None:
            return
        # Don't buffer flush/progress loggers.
        if record.name in _PASSTHROUGH_LOGGERS:
            return
        with self._lock:
            self._buffers.setdefault(idx, []).append(record)


@dataclass
class OrderedLogFlusher:
    """
    Flushes buffered invoice logs contiguously, strictly ordered by idx.
    """

    formatter: logging.Formatter
    stream: object = sys.stdout
    _buffers: Dict[int, List[logging.LogRecord]] = field(default_factory=dict)
    _ready: Dict[int, bool] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)
    _cv: Condition = field(init=False)
    _next_idx: int = 1
    _flush_logger: logging.Logger = field(init=False)

    def __post_init__(self) -> None:
        self._cv = Condition(self._lock)
        self._flush_logger = logging.getLogger("invoice_flush")
        self._flush_logger.propagate = False
        self._flush_logger.setLevel(logging.INFO)
        if not self._flush_logger.handlers:
            h = logging.StreamHandler(self.stream)
            h.setFormatter(self.formatter)
            self._flush_logger.addHandler(h)

    @property
    def buffers(self) -> Dict[int, List[logging.LogRecord]]:
        return self._buffers

    @property
    def lock(self) -> Lock:
        return self._lock

    def mark_ready(self, idx: int) -> None:
        with self._cv:
            self._ready[idx] = True
            self._cv.notify_all()

    def flush_ready_in_order(self, total: int) -> None:
        """
        Blocks until it can flush invoices in idx order up to `total`.
        """
        with self._cv:
            while self._next_idx <= total:
                while not self._ready.get(self._next_idx, False):
                    self._cv.wait()
                idx = self._next_idx
                records = self._buffers.pop(idx, [])
                self._ready.pop(idx, None)
                self._next_idx += 1

                # Flush outside the lock to avoid blocking producers.
                self._cv.release()
                try:
                    for record in records:
                        # Ensure formatting is consistent with your global format.
                        self._flush_logger.handle(record)
                finally:
                    self._cv.acquire()


class InvoiceLogManager:
    """
    Manages buffering handler installation and invoice binding context.
    """

    def __init__(self, formatter: logging.Formatter):
        self.flusher = OrderedLogFlusher(formatter=formatter)
        self._handler = PerInvoiceBufferHandler(self.flusher.buffers, self.flusher.lock)
        self._drop_filter = _DropBoundInvoiceLogsFilter()
        self._installed_on_handlers: list[logging.Handler] = []

    def install(self) -> None:
        root = logging.getLogger()
        # Prevent duplicate emission: keep only the buffered/flush path for bound invoices.
        for h in root.handlers:
            h.addFilter(self._drop_filter)
            self._installed_on_handlers.append(h)
        root.addHandler(self._handler)

    def uninstall(self) -> None:
        root = logging.getLogger()
        for h in self._installed_on_handlers:
            try:
                h.removeFilter(self._drop_filter)
            except ValueError:
                pass
        self._installed_on_handlers.clear()
        try:
            root.removeHandler(self._handler)
        except ValueError:
            pass

    @contextmanager
    def bind(self, idx: int) -> Iterator[None]:
        token = _invoice_idx_var.set(idx)
        try:
            yield
        finally:
            _invoice_idx_var.reset(token)

