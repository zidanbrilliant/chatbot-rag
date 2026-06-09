from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


class DocumentOut(BaseModel):
    id: str
    original_filename: str
    file_type: str
    size_bytes: int
    status: str
    access_level: str
    document_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @field_validator("id", mode="before")
    @classmethod
    def coerce_uuid(cls, v: object) -> str:
        if isinstance(v, UUID):
            return str(v)
        return str(v)

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    document_id: str
    job_id: str | None = None
    message: str


class DeleteResponse(BaseModel):
    message: str
