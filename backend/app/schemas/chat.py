from pydantic import BaseModel


class QueryRequest(BaseModel):
    session_id: str | None = None
    query: str


class Source(BaseModel):
    file_name: str | None = None
    page_number: int | None = None
    row_index: int | None = None
    source_type: str = "internal"
    url: str | None = None
    title: str | None = None


class QueryResponse(BaseModel):
    session_id: str
    reply: str
    message_id: str = ""
    sources: list[Source] = []
    confidence: str = ""  # high | medium | low | abstain
    fallback_triggered: bool = False
    out_of_context: bool = False
    metadata: dict = {}  # e.g. {"price_table": [...]} for price queries


class FallbackRequest(BaseModel):
    session_id: str
    query: str


class ExternalSource(BaseModel):
    title: str
    url: str


class FallbackResponse(BaseModel):
    reply: str
    external_sources: list[ExternalSource] = []


class FeedbackRequest(BaseModel):
    message_id: str
    feedback: str


class FeedbackResponse(BaseModel):
    message: str
