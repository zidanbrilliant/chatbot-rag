from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DocumentOut(BaseModel):
    id: str
    file_name: str
    file_size: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    document_id: str
    message: str


class DeleteResponse(BaseModel):
    message: str
