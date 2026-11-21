from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ApiResponse
from app.db.session import get_session
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.jobs.schemas import JobListOut, JobOut
from app.modules.jobs.service import get_user_job, list_project_jobs, stream_job_events

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=ApiResponse[JobOut])
async def get_job(
    job_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[JobOut]:
    job = await get_user_job(session, job_id=job_id, user_id=user.id)
    return ApiResponse(data=JobOut.model_validate(job))


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    # 先校验权限与存在性，避免在 StreamingResponse 内部报错。
    await get_user_job(session, job_id=job_id, user_id=user.id)
    generator = stream_job_events(
        sessions=request.app.state.sessions,
        redis=request.app.state.redis,
        settings=request.app.state.settings,
        job_id=job_id,
        user_id=user.id,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/projects/{project_id}/jobs", response_model=ApiResponse[JobListOut])
async def get_project_jobs(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[JobListOut]:
    rows = await list_project_jobs(session, project_id=project_id, user_id=user.id)
    return ApiResponse(data=JobListOut(items=[JobOut.model_validate(row) for row in rows]))
