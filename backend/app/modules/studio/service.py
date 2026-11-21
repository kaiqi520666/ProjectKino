import re
from uuid import UUID, uuid4

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.jobs.models import Job
from app.modules.jobs.schemas import JobOut
from app.modules.llm_engine.schema import (
    Asset,
    AssetResult,
    EpisodeDraft,
    Outline,
    ProjectSettings,
    Scene,
    ScriptResult,
    StoryboardResult,
)
from app.modules.llm_engine.schema import (
    Episode as LlmEpisode,
)
from app.modules.llm_engine.timing import episode_seconds, render_script
from app.modules.studio.models import Episode, Project, ProjectAsset, StoryboardClip
from app.modules.studio.schemas import (
    AssetCreateRequest,
    AssetUpdateRequest,
    ClipCreateRequest,
    ClipUpdateRequest,
    EpisodeOut,
    ProjectAssetOut,
    ProjectDetailOut,
    ProjectSummaryOut,
    StoryboardClipOut,
)

_SCRIPT_CODE_RE = re.compile(r"^[CSP]\d+$")


async def get_owned_project(session: AsyncSession, *, project_id: UUID, user_id: int) -> Project:
    project = await session.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == user_id,
            Project.status == "active",
        )
    )
    if project is None:
        raise AppError(404, "project_not_found", "短剧项目不存在")
    return project


async def list_user_projects(session: AsyncSession, *, user_id: int) -> list[ProjectSummaryOut]:
    projects = list(
        await session.scalars(
            select(Project)
            .where(Project.user_id == user_id, Project.status == "active")
            .order_by(desc(Project.updated_at), desc(Project.id))
        )
    )
    if not projects:
        return []
    project_ids = [p.id for p in projects]
    ep_counts = dict(
        (
            await session.execute(
                select(Episode.project_id, func.count())
                .where(Episode.project_id.in_(project_ids))
                .group_by(Episode.project_id)
            )
        ).all()
    )
    asset_counts = dict(
        (
            await session.execute(
                select(ProjectAsset.project_id, func.count())
                .where(ProjectAsset.project_id.in_(project_ids))
                .group_by(ProjectAsset.project_id)
            )
        ).all()
    )
    return [
        ProjectSummaryOut(
            id=p.id,
            name=p.name,
            mode=p.mode,
            settings=p.settings,
            script_confirmed=p.script_confirmed,
            episode_count=int(ep_counts.get(p.id, 0)),
            asset_count=int(asset_counts.get(p.id, 0)),
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in projects
    ]


async def get_project_detail(session: AsyncSession, *, project_id: UUID, user_id: int) -> ProjectDetailOut:
    project = await get_owned_project(session, project_id=project_id, user_id=user_id)
    episodes = list(
        await session.scalars(
            select(Episode).where(Episode.project_id == project.id).order_by(Episode.number)
        )
    )
    assets = list(
        await session.scalars(
            select(ProjectAsset)
            .where(ProjectAsset.project_id == project.id)
            .order_by(ProjectAsset.created_at, ProjectAsset.asset_code)
        )
    )
    clips = list(
        await session.scalars(
            select(StoryboardClip)
            .where(StoryboardClip.project_id == project.id)
            .order_by(StoryboardClip.clip_index)
        )
    )
    active_jobs = list(
        await session.scalars(
            select(Job)
            .where(Job.project_id == project.id, Job.status.in_(("queued", "running", "polling")))
            .order_by(desc(Job.created_at))
        )
    )

    ep_num_by_id = {ep.id: ep.number for ep in episodes}
    storyboards: dict[int, list[StoryboardClipOut]] = {}
    for clip in clips:
        ep_num = ep_num_by_id.get(clip.episode_id)
        if ep_num is not None:
            storyboards.setdefault(ep_num, []).append(StoryboardClipOut.model_validate(clip))

    return ProjectDetailOut(
        id=project.id,
        name=project.name,
        mode=project.mode,
        source_text=project.source_text,
        settings=project.settings,
        outline=project.outline,
        script_confirmed=project.script_confirmed,
        episodes=[EpisodeOut.model_validate(ep) for ep in episodes],
        assets=[ProjectAssetOut.model_validate(a) for a in assets],
        storyboards=storyboards,
        active_jobs=[JobOut.model_validate(j) for j in active_jobs],
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def build_script_result_from_db(session: AsyncSession, project: Project) -> ScriptResult:
    if not project.outline:
        raise AppError(400, "script_not_generated", "该项目尚未生成结构化剧本")
    episodes = list(
        await session.scalars(
            select(Episode).where(Episode.project_id == project.id).order_by(Episode.number)
        )
    )
    return ScriptResult(
        settings=ProjectSettings.model_validate(project.settings),
        outline=Outline.model_validate(project.outline),
        episodes=[
            LlmEpisode(
                number=ep.number,
                title=ep.title,
                summary=ep.summary,
                hook=ep.hook or "开场钩子",
                cliff=ep.cliff or "结尾悬念",
                hookBeat=(ep.hook_beat[0], ep.hook_beat[1]) if len(ep.hook_beat) == 2 else (1, 1),
                scenes=[Scene.model_validate(scene) for scene in ep.scenes],
                targetSeconds=ep.target_seconds,
                seconds=ep.seconds,
                script=ep.script,
                warnings=list(ep.warnings or []),
            )
            for ep in episodes
        ],
    )


async def build_asset_result_from_db(session: AsyncSession, project: Project) -> AssetResult:
    assets = list(
        await session.scalars(
            select(ProjectAsset)
            .where(ProjectAsset.project_id == project.id)
            .order_by(ProjectAsset.created_at, ProjectAsset.asset_code)
        )
    )
    return AssetResult(
        settings=ProjectSettings.model_validate(project.settings),
        assets=[
            Asset(
                id=a.asset_code,
                kind=a.kind,  # type: ignore[arg-type]
                name=a.name,
                description=a.description or a.name,
                prompt=a.prompt or a.name,
                episodeNumbers=[n for n in (a.episode_numbers or []) if isinstance(n, int) and n >= 1],
                voice=a.voice or "",
            )
            for a in assets
        ],
    )


async def persist_script_result(
    session: AsyncSession,
    project: Project,
    result: ScriptResult,
    *,
    reset_downstream: bool = False,
) -> None:
    project.name = result.settings.name
    project.settings = result.settings.model_dump()
    project.outline = result.outline.model_dump()
    project.script_confirmed = False

    if reset_downstream:
        await session.execute(delete(StoryboardClip).where(StoryboardClip.project_id == project.id))
        await session.execute(delete(ProjectAsset).where(ProjectAsset.project_id == project.id))
    await session.execute(delete(Episode).where(Episode.project_id == project.id))
    await session.flush()

    for ep in result.episodes:
        session.add(
            Episode(
                project_id=project.id,
                number=ep.number,
                title=ep.title,
                summary=ep.summary,
                target_seconds=ep.targetSeconds,
                seconds=ep.seconds,
                hook=ep.hook,
                cliff=ep.cliff,
                hook_beat=list(ep.hookBeat),
                scenes=[scene.model_dump() for scene in ep.scenes],
                script=ep.script,
                warnings=list(ep.warnings),
            )
        )
    await session.flush()


async def persist_rewritten_episode(
    session: AsyncSession,
    project: Project,
    rewritten: LlmEpisode,
) -> Episode:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == rewritten.number)
    )
    if ep is None:
        ep = Episode(project_id=project.id, number=rewritten.number, title=rewritten.title)
        session.add(ep)
    ep.title = rewritten.title
    ep.summary = rewritten.summary
    ep.target_seconds = rewritten.targetSeconds
    ep.seconds = rewritten.seconds
    ep.hook = rewritten.hook
    ep.cliff = rewritten.cliff
    ep.hook_beat = list(rewritten.hookBeat)
    ep.scenes = [scene.model_dump() for scene in rewritten.scenes]
    ep.script = rewritten.script
    ep.warnings = list(rewritten.warnings)
    ep.composed_video_key = None
    ep.composed_video_url = None
    ep.composed_duration = None
    project.script_confirmed = False
    await session.flush()
    await session.execute(delete(StoryboardClip).where(StoryboardClip.episode_id == ep.id))
    await session.flush()
    return ep


async def persist_appended_episode(
    session: AsyncSession,
    project: Project,
    updated: ScriptResult,
) -> Episode:
    project.settings = updated.settings.model_dump()
    project.outline = updated.outline.model_dump()
    project.script_confirmed = False
    latest = max(updated.episodes, key=lambda item: item.number)
    ep = Episode(
        project_id=project.id,
        number=latest.number,
        title=latest.title,
        summary=latest.summary,
        target_seconds=latest.targetSeconds,
        seconds=latest.seconds,
        hook=latest.hook,
        cliff=latest.cliff,
        hook_beat=list(latest.hookBeat),
        scenes=[scene.model_dump() for scene in latest.scenes],
        script=latest.script,
        warnings=list(latest.warnings),
    )
    session.add(ep)
    await session.flush()
    return ep


async def persist_extracted_assets(
    session: AsyncSession,
    project: Project,
    result: AssetResult,
    *,
    preserve_edits: bool = False,
) -> list[ProjectAsset]:
    existing_rows = list(
        await session.scalars(select(ProjectAsset).where(ProjectAsset.project_id == project.id))
    )
    by_code = {row.asset_code: row for row in existing_rows}
    result_codes = {item.id for item in result.assets}

    # 删除已不在剧本中出现的旧脚本资产（保留用户手动创建的非 C/S/P 自定义资产）。
    for row in existing_rows:
        if row.asset_code not in result_codes and _SCRIPT_CODE_RE.match(row.asset_code):
            await session.delete(row)

    saved: list[ProjectAsset] = []
    for item in result.assets:
        row = by_code.get(item.id)
        if row is None:
            row = ProjectAsset(
                project_id=project.id,
                asset_code=item.id,
                kind=item.kind,
                name=item.name,
                description=item.description,
                prompt=item.prompt,
                voice=item.voice if item.kind == "character" else "",
                episode_numbers=list(item.episodeNumbers),
            )
            session.add(row)
        else:
            row.episode_numbers = list(item.episodeNumbers)
            if not preserve_edits:
                row.kind = item.kind
                row.name = item.name
                row.description = item.description
                row.prompt = item.prompt
                row.voice = item.voice if item.kind == "character" else ""
            # 无论全量还是增量，始终保留已上传/已生成的 image_key / image_url。
        saved.append(row)

    await session.flush()
    return saved


async def persist_storyboard_result(
    session: AsyncSession,
    project: Project,
    result: StoryboardResult,
) -> None:
    episodes = {
        ep.number: ep for ep in await session.scalars(select(Episode).where(Episode.project_id == project.id))
    }
    assets_by_code = {
        a.asset_code: a
        for a in await session.scalars(select(ProjectAsset).where(ProjectAsset.project_id == project.id))
    }
    for board in result.episodes:
        ep = episodes.get(board.number)
        if ep is None:
            continue
        await session.execute(delete(StoryboardClip).where(StoryboardClip.episode_id == ep.id))
        await session.flush()
        for clip in board.clips:
            refs = []
            for ref in clip.references:
                matched = assets_by_code.get(ref.assetId)
                refs.append(
                    {
                        "index": ref.index,
                        "assetId": str(matched.id) if matched else ref.assetId,
                        "assetCode": ref.assetId,
                        "name": matched.name if matched else ref.name,
                        "kind": ref.kind,
                    }
                )
            session.add(
                StoryboardClip(
                    project_id=project.id,
                    episode_id=ep.id,
                    clip_index=clip.id,
                    duration_seconds=max(1, round(clip.durationSeconds)),
                    prompt=clip.prompt,
                    prompt_customized=False,
                    references=refs,
                    beats=list(clip.beats) if clip.beats else None,
                    blocking=clip.blocking or None,
                    cuts=[cut.model_dump() for cut in clip.cuts] if clip.cuts else None,
                )
            )
    await session.flush()


async def save_structured_episode(
    session: AsyncSession,
    *,
    project: Project,
    episode_number: int,
    title: str,
    raw_scenes: list[dict],
) -> Episode:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    if not project.outline:
        raise AppError(400, "outline_missing", "缺少大纲信息，无法保存结构化剧本")

    cleaned_scenes: list[Scene] = []
    for raw in raw_scenes:
        characters = list(raw.get("characters") or [])
        flow = []
        for beat in raw.get("flow") or []:
            if beat.get("action") is not None:
                text_val = str(beat["action"]).strip()
                if text_val:
                    flow.append({"action": text_val})
            else:
                line_val = str(beat.get("line") or "").strip()
                if not line_val:
                    continue
                speaker = str(beat.get("speaker") or "").strip() or "VO"
                delivery = str(beat.get("delivery") or "").strip()
                if speaker != "VO" and speaker not in characters:
                    characters.append(speaker)
                item = {"speaker": speaker, "line": line_val}
                if delivery:
                    item["delivery"] = delivery
                flow.append(item)
        if not flow or not any("action" in b for b in flow):
            raise AppError(400, "invalid_scene_flow", "每场至少需要保留一条动作节拍")
        cleaned_scenes.append(
            Scene.model_validate(
                {
                    "sceneId": raw["sceneId"],
                    "lighting": str(raw.get("lighting") or "").strip(),
                    "characters": characters,
                    "props": list(raw.get("props") or []),
                    "flow": flow,
                }
            )
        )

    outline = Outline.model_validate(project.outline)
    safe_scene = max(1, min(ep.hook_beat[0] if ep.hook_beat else 1, len(cleaned_scenes)))
    safe_beat = max(
        1,
        min(
            ep.hook_beat[1] if len(ep.hook_beat) > 1 else 1,
            len(cleaned_scenes[safe_scene - 1].flow),
        ),
    )
    draft = EpisodeDraft(
        number=ep.number,
        title=title.strip(),
        summary=ep.summary or title.strip(),
        hook=ep.hook or "开场钩子",
        cliff=ep.cliff or "结尾悬念",
        hookBeat=(safe_scene, safe_beat),
        scenes=cleaned_scenes,
    )
    ep.title = draft.title
    ep.scenes = [s.model_dump() for s in cleaned_scenes]
    ep.seconds = episode_seconds(draft)
    ep.script = render_script(draft, outline)
    ep.hook_beat = [safe_scene, safe_beat]
    project.script_confirmed = False
    await session.flush()
    return ep


async def create_project_asset(
    session: AsyncSession, *, project: Project, body: AssetCreateRequest
) -> ProjectAsset:
    asset = ProjectAsset(
        project_id=project.id,
        asset_code=uuid4().hex[:12],
        kind=body.kind,
        name=body.name.strip(),
        description=body.description.strip(),
        prompt=body.prompt.strip(),
        voice=body.voice.strip() if body.kind == "character" else "",
        image_url=body.image_url,
        image_key=body.image_key,
        image_status="ready" if body.image_url else "none",
    )
    session.add(asset)
    await session.flush()
    return asset


async def update_project_asset(
    session: AsyncSession, *, project: Project, asset_id: UUID, body: AssetUpdateRequest
) -> ProjectAsset:
    asset = await session.scalar(
        select(ProjectAsset).where(ProjectAsset.id == asset_id, ProjectAsset.project_id == project.id)
    )
    if asset is None:
        raise AppError(404, "asset_not_found", "资产不存在")
    if body.name is not None:
        asset.name = body.name.strip()
    if body.description is not None:
        asset.description = body.description.strip()
    if body.prompt is not None:
        asset.prompt = body.prompt.strip()
    if body.voice is not None:
        asset.voice = body.voice.strip() if asset.kind == "character" else ""
    if body.clear_image:
        asset.image_url = None
        asset.image_key = None
        asset.image_status = "none"
    elif body.image_url is not None:
        asset.image_url = body.image_url
        asset.image_key = body.image_key
        asset.image_status = "ready"
    await session.flush()
    return asset


async def delete_project_asset(session: AsyncSession, *, project: Project, asset_id: UUID) -> None:
    asset = await session.scalar(
        select(ProjectAsset).where(ProjectAsset.id == asset_id, ProjectAsset.project_id == project.id)
    )
    if asset is None:
        raise AppError(404, "asset_not_found", "资产不存在")
    await session.delete(asset)
    await session.flush()


async def create_clip(
    session: AsyncSession, *, project: Project, episode_number: int, body: ClipCreateRequest
) -> StoryboardClip:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    highest = int(
        await session.scalar(
            select(func.coalesce(func.max(StoryboardClip.clip_index), 0)).where(
                StoryboardClip.episode_id == ep.id
            )
        )
        or 0
    )
    clip = StoryboardClip(
        project_id=project.id,
        episode_id=ep.id,
        clip_index=highest + 1,
        duration_seconds=body.duration_seconds,
        prompt=body.prompt,
        prompt_customized=bool(body.prompt.strip()),
        references=body.references,
    )
    session.add(clip)
    await session.flush()
    return clip


async def update_clip(
    session: AsyncSession, *, project: Project, clip_id: UUID, body: ClipUpdateRequest
) -> StoryboardClip:
    clip = await session.scalar(
        select(StoryboardClip).where(StoryboardClip.id == clip_id, StoryboardClip.project_id == project.id)
    )
    if clip is None:
        raise AppError(404, "clip_not_found", "片段不存在")
    if body.duration_seconds is not None:
        if clip.video_status == "generating":
            raise AppError(409, "clip_video_in_progress", "该片段正在生成视频中，暂不可修改时长")
        clip.duration_seconds = body.duration_seconds
    if body.prompt is not None and body.prompt != clip.prompt:
        clip.prompt = body.prompt
        clip.prompt_customized = True
    if body.references is not None:
        clip.references = body.references
    await session.flush()
    return clip


async def reorder_episode_clips(
    session: AsyncSession,
    *,
    project: Project,
    episode_number: int,
    clip_ids: list[UUID],
) -> list[StoryboardClip]:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    clips = list(
        await session.scalars(
            select(StoryboardClip)
            .where(StoryboardClip.episode_id == ep.id)
            .order_by(StoryboardClip.clip_index)
        )
    )
    by_id = {c.id: c for c in clips}
    if len(clip_ids) != len(clips) or set(clip_ids) != set(by_id.keys()):
        raise AppError(400, "invalid_clip_order", "片段排序列表必须包含本集全部且不重复的片段")

    # 两阶段正偏移重排：满足 clip_index >= 1 约束同时避免唯一索引碰撞。
    offset = max((c.clip_index for c in clips), default=0) + 1000
    for idx, cid in enumerate(clip_ids, 1):
        by_id[cid].clip_index = offset + idx
    await session.flush()

    ordered: list[StoryboardClip] = []
    for idx, cid in enumerate(clip_ids, 1):
        row = by_id[cid]
        row.clip_index = idx
        ordered.append(row)
    await session.flush()
    return ordered


async def delete_clip(session: AsyncSession, *, project: Project, clip_id: UUID) -> None:
    clip = await session.scalar(
        select(StoryboardClip).where(StoryboardClip.id == clip_id, StoryboardClip.project_id == project.id)
    )
    if clip is None:
        raise AppError(404, "clip_not_found", "片段不存在")
    await session.delete(clip)
    await session.flush()
