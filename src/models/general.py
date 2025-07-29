from collections import defaultdict
from datetime import datetime
from typing import Optional

from pandas import DataFrame
from pydantic import BaseModel, Field, PrivateAttr

from src.models.google import EmailMessage
from src.models.mutualser import FindLoadResponse
from src.resources.datetimes import convert_utc_to_utc_minus_5


class Record(BaseModel):
    started_at: datetime = Field(default_factory=datetime.now)
    email: EmailMessage
    response_mutualser: Optional[FindLoadResponse] = None
    status: str = ""
    errors: list[Exception] = []
    finished_at: datetime = Field(default_factory=datetime.now)

    # Internal attribute to track changes
    _initialized: bool = PrivateAttr(default=False)

    def __init__(self, **data):
        super().__init__(**data)
        object.__setattr__(self, "_initialized", True)

    def __setattr__(self, name, value):
        if getattr(self, "_initialized", False) and name not in {"finished_at", "_initialized"}:
            super().__setattr__("finished_at", datetime.now())
        super().__setattr__(name, value)

    @property
    def finished_at_utc(self):
        return convert_utc_to_utc_minus_5(self.finished_at)

    def to_dataframe(self) -> DataFrame:
        """Converts the record to a pandas DataFrame."""
        return DataFrame({
            'Factura': [self.email.nro_factura],
            'Fecha Factura': [self.email.fecha_factura],
            'ID de cargue': [self.response_mutualser.cargue_id if self.response_mutualser else ""],
            'Total': [self.email.valor_factura],
            'Status': [self.status],
            'Errores': [", ".join(map(str, self.errors))],
            'Día': [self.finished_at_utc.strftime('%d')],
            'Mes': [self.finished_at_utc.strftime('%m')],
            'Año': [self.finished_at_utc.year],
            'Momento': [f"{self.finished_at_utc:%T}"]
        })

    class Config:
        arbitrary_types_allowed = True
        orm_mode = True


class Run(BaseModel):
    date: datetime = Field(default_factory=datetime.now)
    record: dict[str, Record] = Field(default_factory=dict)

    # Optional: convert to defaultdict after model creation
    def model_post_init(self, __context) -> None:
        self.record = defaultdict(Record, self.record)

    def make_df(self) -> DataFrame:
        """Generates a DataFrame from all the records."""
        return DataFrame()._append([record.to_dataframe() for record in self.record.values()][::-1], ignore_index=True)

    def order_by_fecha_factura(self) -> list:
        """Create a list based on record's information."""
        return sorted(self.record.items(), key=lambda item: item[1].email.received_at, reverse=True)
