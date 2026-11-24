from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.schemas import CamelModel


class JobOut(CamelModel):
    id: UUID
    project_id: UUID | None = None
    canvas_id: UUID | None = None
    job_type: str
    target_id: str | None = None
    status: str
    step_index: int
    step_total: int
    step_label: str
    progress: int
    result_payload: dict[str, Any] | None = None
    job_meta: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    usage_summary: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobListOut(CamelModel):
    items: list[JobOut]
