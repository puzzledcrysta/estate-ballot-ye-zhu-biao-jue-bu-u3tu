from typing import Annotated, Literal
from pydantic import BaseModel, Field
from app.inputs import CsvText, EncodedCsv
from app.settings import FIELDS


class CorrectionForm(BaseModel):
    key: Annotated[str, Field(min_length=1, max_length=80)]
    kind: Literal['一般', '特别']
    estate: Annotated[str, Field(min_length=1, max_length=4000)]
    ballot: Annotated[str, Field(min_length=1, max_length=4000)]
    note: Annotated[str, Field(default='', max_length=200)] = ''

    def as_fields(self):
        return {FIELDS[0]: self.kind, FIELDS[1]: self.estate, FIELDS[2]: self.ballot}


class CorrectionPack(BaseModel):
    key: Annotated[str, Field(min_length=1, max_length=80)]
    original: CorrectionForm
    correction_a: CorrectionForm
    correction_b: CorrectionForm
    book: CsvText | None = None
    book_base64: EncodedCsv | None = None


class CorrectionReview(BaseModel):
    version: int = Field(ge=0)
    decision: Literal['确认', '留待核实']
    note: str = Field(default='', max_length=500)
