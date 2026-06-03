from pydantic import BaseModel
from typing import Optional


class QueryRequest(BaseModel):
    session_id: Optional[str] = None
    query: str


class Source(BaseModel):
    file_name: str
    page_number: Optional[int] = None
    row_index: Optional[int] = None


class QueryResponse(BaseModel):
    session_id: str
    reply: str
    sources: list[Source] = []
    fallback_triggered: bool = False
    out_of_context: bool = False


class FallbackRequest(BaseModel):
    session_id: str
    query: str


class ExternalSource(BaseModel):
    title: str
    url: str


class FallbackResponse(BaseModel):
    reply: str
    external_sources: list[ExternalSource] = []
