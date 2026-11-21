from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.schemas import ApiResponse, CamelModel
from app.db.session import get_session
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.storage.oss import load_storage

router = APIRouter(prefix="/uploads", tags=["uploads"])

_MAX_BYTES = {
    "image": 20 * 1024 * 1024,
    "video": 500 * 1024 * 1024,
    "audio": 50 * 1024 * 1024,
}


class OssUploadPolicyRequest(CamelModel):
    kind: Literal["image", "video", "audio"] = "image"
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=3, max_length=120)
    size: int = Field(gt=0, le=500 * 1024 * 1024)


class OssUploadPolicyOut(CamelModel):
    host: str
    key: str
    url: str
    fields: dict[str, str]
    expires_at: str


@router.post("/oss-policy", response_model=ApiResponse[OssUploadPolicyOut])
async def create_oss_upload_policy(
    body: OssUploadPolicyRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[OssUploadPolicyOut]:
    expected_prefix = f"{body.kind}/"
    if not body.mime_type.lower().startswith(expected_prefix):
        raise AppError(400, "invalid_mime_type", f"文件类型 {body.mime_type} 与上传类别 {body.kind} 不匹配")
    limit = _MAX_BYTES[body.kind]
    if body.size > limit:
        raise AppError(400, "file_too_large", f"文件体积超过限制（最大 {limit // (1024 * 1024)} MB）")

    storage = await load_storage(session)
    policy = storage.upload_policy(
        user_id=user.id,
        kind=body.kind,
        file_name=body.file_name,
        mime_type=body.mime_type,
        size=body.size,
    )
    return ApiResponse(data=OssUploadPolicyOut.model_validate(policy))
