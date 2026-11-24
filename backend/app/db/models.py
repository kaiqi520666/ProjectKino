"""集中导入所有 ORM 模型，供 Alembic 与初始化检查使用。"""

from app.modules.announcements.models import Announcement
from app.modules.art_styles.models import ArtStyle
from app.modules.auth.models import User
from app.modules.canvas.models import Canvas, UserAsset
from app.modules.catalog.models import (
    AiModel,
    AiModelSyncLog,
    AiProvider,
    ImageModelPrice,
    TextModelPrice,
    VideoModelPrice,
)
from app.modules.credits.models import CreditLedger, CreditReservation, RedeemCode, RedeemCodeUse
from app.modules.jobs.models import Job
from app.modules.settings.models import SystemSetting
from app.modules.studio.models import Episode, Project, ProjectAsset, StoryboardClip

__all__ = [
    "User",
    "Announcement",
    "ArtStyle",
    "SystemSetting",
    "AiProvider",
    "AiModel",
    "AiModelSyncLog",
    "TextModelPrice",
    "ImageModelPrice",
    "VideoModelPrice",
    "CreditReservation",
    "CreditLedger",
    "RedeemCode",
    "RedeemCodeUse",
    "Project",
    "Episode",
    "ProjectAsset",
    "StoryboardClip",
    "Canvas",
    "UserAsset",
    "Job",
]
