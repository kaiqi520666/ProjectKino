from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.core.schemas import CamelModel
from app.modules.jobs.schemas import JobOut

MIN_EPISODE_SECONDS = 120
MAX_EPISODE_SECONDS = 600
MAX_INITIAL_TOTAL_SECONDS = 3600
MAX_UPLOAD_TEXT_BYTES = 2 * 1024 * 1024


class ProjectSettingsIn(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    ratio: Literal["16:9", "9:16", "1:1", "4:3", "3:4"] = "16:9"
    language: Literal["zh-CN", "zh-TW", "en"] = "zh-CN"
    visual_style: str = Field(min_length=1, max_length=80)
    visual_style_label: str = Field(default="", max_length=500)
    episode_count: int = Field(ge=1, le=MAX_INITIAL_TOTAL_SECONDS // MIN_EPISODE_SECONDS)
    max_segment_duration: Literal[15, 30] = 15
    seconds_per_episode: int = Field(default=120, ge=MIN_EPISODE_SECONDS, le=MAX_EPISODE_SECONDS)
    background_music: bool = True
    image_model_id: str | None = Field(default=None, max_length=48)
    image_tier: Literal["web", "1k", "2k", "4k"] | None = None
    video_model_id: str | None = Field(default=None, max_length=48)

    @model_validator(mode="after")
    def validate_initial_total_duration(self) -> "ProjectSettingsIn":
        if self.episode_count * self.seconds_per_episode > MAX_INITIAL_TOTAL_SECONDS:
            max_eps = MAX_INITIAL_TOTAL_SECONDS // self.seconds_per_episode
            raise ValueError(
                f"首创全剧总时长不能超过 {MAX_INITIAL_TOTAL_SECONDS // 60} 分钟"
                f"（当前单集 {self.seconds_per_episode} 秒最多可首创 {max_eps} 集，"
                "创建后可在剧本页继续新增分集）"
            )
        return self


class GenerateProjectRequest(CamelModel):
    settings: ProjectSettingsIn
    mode: Literal["story", "upload"] = "story"
    text: str = Field(min_length=1)
    feedback: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_text_size(self) -> "GenerateProjectRequest":
        if len(self.text.encode("utf-8")) > MAX_UPLOAD_TEXT_BYTES:
            raise ValueError("上传的文本内容不能超过 2MB")
        return self


class RegenerateStoryRequest(CamelModel):
    feedback: str = Field(default="", max_length=500)


class RewriteEpisodeRequest(CamelModel):
    feedback: str = Field(default="", max_length=500)


class AppendEpisodeRequest(CamelModel):
    feedback: str = Field(default="", max_length=500)


class RenameProjectRequest(CamelModel):
    name: str = Field(min_length=1, max_length=120)


class UpdateProjectRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    ratio: Literal["16:9", "9:16", "1:1", "4:3", "3:4"] | None = None
    visual_style: str | None = Field(default=None, min_length=1, max_length=80)
    visual_style_label: str | None = Field(default=None, max_length=500)
    max_segment_duration: Literal[15, 30] | None = None
    background_music: bool | None = None
    image_model_id: str | None = Field(default=None, max_length=48)
    image_tier: Literal["web", "1k", "2k", "4k"] | None = None
    video_model_id: str | None = Field(default=None, max_length=48)
    cover_url: str | None = Field(default=None, max_length=2048)
    cover_key: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_fields(self) -> "UpdateProjectRequest":
        if "name" in self.model_fields_set:
            if self.name is None or not self.name.strip():
                raise ValueError("项目名称不能为空")
            self.name = self.name.strip()
        if "visual_style" in self.model_fields_set:
            if self.visual_style is None or not self.visual_style.strip():
                raise ValueError("画风不能为空")
            self.visual_style = self.visual_style.strip()
        if "cover_url" in self.model_fields_set and self.cover_url is not None:
            cleaned = self.cover_url.strip()
            if not cleaned:
                self.cover_url = None
            elif not cleaned.startswith(("http://", "https://")):
                raise ValueError("封面地址必须为有效的 http/https 链接")
            else:
                self.cover_url = cleaned
        if "cover_key" in self.model_fields_set and self.cover_key is not None:
            cleaned_key = self.cover_key.strip()
            self.cover_key = cleaned_key or None
        if "image_model_id" in self.model_fields_set and self.image_model_id is not None:
            self.image_model_id = self.image_model_id.strip() or None
        if "video_model_id" in self.model_fields_set and self.video_model_id is not None:
            self.video_model_id = self.video_model_id.strip() or None
        return self


class ProjectMetaOut(CamelModel):
    id: UUID
    name: str
    settings: dict[str, Any]
    cover_url: str | None = None
    cover_key: str | None = None
    updated_at: datetime


class StructuredEpisodeSaveRequest(CamelModel):
    title: str = Field(min_length=1, max_length=160)
    scenes: list[dict[str, Any]] = Field(min_length=1)


class AssetCreateRequest(CamelModel):
    kind: Literal["character", "scene", "prop"]
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    prompt: str = ""
    voice: str = ""
    image_url: str | None = None
    image_key: str | None = None
    parent_asset_id: UUID | None = None
    variant_label: str = Field(default="", max_length=48)


class AssetUpdateRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    prompt: str | None = None
    voice: str | None = None
    image_url: str | None = None
    image_key: str | None = None
    clear_image: bool = False
    variant_label: str | None = Field(default=None, max_length=48)


class ExtractAssetsRequest(CamelModel):
    mode: Literal["full", "incremental"] = "incremental"


class GenerateStoryboardRequest(CamelModel):
    feedback: str = Field(default="", max_length=500)


class RegenerateClipRequest(CamelModel):
    feedback: str = Field(default="", max_length=500)
    refresh_references: bool = True


class GenerateNewClipRequest(CamelModel):
    duration_seconds: int = Field(default=10, ge=4, le=30)
    feedback: str = Field(default="", max_length=500)
    insert_after_clip_id: UUID | None = None


class ClipCreateRequest(CamelModel):
    duration_seconds: int = Field(default=15, ge=1, le=30)
    prompt: str = ""
    references: list[dict[str, Any]] = Field(default_factory=list)
    insert_after_clip_id: UUID | None = None


class ClipUpdateRequest(CamelModel):
    duration_seconds: int | None = Field(default=None, ge=1, le=30)
    prompt: str | None = None
    references: list[dict[str, Any]] | None = None


class ClipReorderRequest(CamelModel):
    clip_ids: list[UUID] = Field(min_length=1, max_length=200)


class SuggestVariantPromptRequest(CamelModel):
    variant_label: str = Field(min_length=1, max_length=60)
    note: str = Field(default="", max_length=300)


class SuggestVariantPromptOut(CamelModel):
    description: str
    prompt: str


class GenerateAssetImageRequest(CamelModel):
    model_id: str = Field(default="gpt-image-2", min_length=1, max_length=48)
    tier: Literal["web", "1k", "2k", "4k"] = "1k"
    ratio: str | None = Field(default=None, max_length=16)
    reference_urls: list[str] = Field(default_factory=list, max_length=16)


class GenerateClipGridRequest(CamelModel):
    model_id: str = Field(default="gemini-nano-banana-2.1", min_length=1, max_length=48)
    tier: Literal["web", "1k", "2k", "4k"] = "2k"
    ratio: str | None = Field(default=None, max_length=16)


class BatchGenerateAssetImagesRequest(CamelModel):
    asset_ids: list[UUID] = Field(min_length=1, max_length=30)
    model_id: str = Field(default="gpt-image-2", min_length=1, max_length=48)
    tier: Literal["web", "1k", "2k", "4k"] = "1k"
    ratio: str | None = Field(default=None, max_length=16)
    use_parent_reference: bool = True


class BatchSkippedAssetOut(CamelModel):
    asset_id: UUID
    name: str
    reason: str


class BatchAssetImageAcceptedOut(CamelModel):
    project_id: UUID
    batch_id: str
    accepted_count: int
    total_frozen_credits: Decimal
    jobs: list[JobOut]
    skipped: list[BatchSkippedAssetOut]


class GenerateClipVideoRequest(CamelModel):
    model_id: str = Field(default="cc-sd2-fast-720", min_length=1, max_length=48)
    resolution: Literal["480p", "720p", "1080p"] = "720p"
    ratio: str | None = Field(default=None, max_length=16)
    duration_seconds: int | None = Field(default=None, ge=1, le=60)


class BatchGenerateClipVideosRequest(CamelModel):
    clip_ids: list[UUID] = Field(min_length=1, max_length=30)
    model_id: str = Field(default="cc-sd2-fast-720", min_length=1, max_length=48)
    resolution: Literal["480p", "720p", "1080p"] = "720p"
    ratio: str | None = Field(default=None, max_length=16)
    duration_seconds: int | None = Field(default=None, ge=1, le=60)


class BatchSkippedClipOut(CamelModel):
    clip_id: UUID
    clip_index: int | None = None
    reason: str


class BatchClipVideoAcceptedOut(CamelModel):
    project_id: UUID
    episode_number: int
    batch_id: str
    accepted_count: int
    total_duration_seconds: int
    total_frozen_credits: Decimal
    jobs: list[JobOut]
    skipped: list[BatchSkippedClipOut]


class EpisodeOut(CamelModel):
    id: UUID
    number: int
    title: str
    summary: str
    target_seconds: int
    seconds: float
    hook: str
    cliff: str
    hook_beat: list[int]
    scenes: list[dict[str, Any]]
    script: str
    warnings: list[str]
    composed_video_url: str | None = None
    composed_duration: float | None = None


class MediaHistoryItemOut(CamelModel):
    id: str
    url: str
    key: str | None = None
    source: Literal["ai", "upload", "rescue"] = "ai"
    job_id: str | None = None
    model_id: str | None = None
    tier: str | None = None
    resolution: str | None = None
    ratio: str | None = None
    duration: float | None = None
    created_at: str


class SelectMediaHistoryRequest(CamelModel):
    history_id: str = Field(min_length=1, max_length=128)


class ProjectAssetOut(CamelModel):
    id: UUID
    asset_code: str
    kind: str
    name: str
    description: str
    prompt: str
    voice: str
    episode_numbers: list[int]
    parent_asset_id: UUID | None = None
    variant_label: str = ""
    image_url: str | None = None
    image_model_id: str | None = None
    image_tier: str | None = None
    image_status: str
    image_history: list[MediaHistoryItemOut] = Field(default_factory=list)
    last_job_id: UUID | None = None
    last_job_status: str | None = None
    last_job_error: str | None = None


class StoryboardClipOut(CamelModel):
    id: UUID
    episode_id: UUID
    clip_index: int
    duration_seconds: int
    prompt: str
    prompt_customized: bool
    references: list[dict[str, Any]]
    beats: list[int] | None = None
    blocking: str | None = None
    cuts: list[dict[str, Any]] | None = None
    preview_url: str | None = None
    video_url: str | None = None
    video_model_id: str | None = None
    video_status: str
    video_history: list[MediaHistoryItemOut] = Field(default_factory=list)
    last_job_id: UUID | None = None
    last_job_status: str | None = None
    last_job_error: str | None = None


class EpisodeStoryboardOut(CamelModel):
    episode_number: int
    clips: list[StoryboardClipOut]


class ProjectSummaryOut(CamelModel):
    id: UUID
    name: str
    mode: str
    settings: dict[str, Any]
    cover_url: str | None = None
    cover_key: str | None = None
    auto_cover_url: str | None = None
    script_confirmed: bool
    episode_count: int
    planned_episode_count: int = 0
    asset_count: int
    asset_image_ready_count: int = 0
    storyboard_episode_count: int = 0
    clip_count: int = 0
    clip_video_ready_count: int = 0
    composed_episode_count: int = 0
    created_at: datetime
    updated_at: datetime


class ProjectDetailOut(CamelModel):
    id: UUID
    name: str
    mode: str
    source_text: str
    settings: dict[str, Any]
    cover_url: str | None = None
    cover_key: str | None = None
    outline: dict[str, Any] | None = None
    script_confirmed: bool
    episodes: list[EpisodeOut]
    assets: list[ProjectAssetOut]
    storyboards: dict[int, list[StoryboardClipOut]]
    active_jobs: list[JobOut]
    created_at: datetime
    updated_at: datetime


class ProjectJobAcceptedOut(CamelModel):
    project_id: UUID
    job: JobOut
