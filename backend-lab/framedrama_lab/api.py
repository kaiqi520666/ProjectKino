import os
import time
from functools import lru_cache
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models import Model

from .analyze_assets import analyze_assets
from .deepseek import model_from_env
from .gates import log_progress
from .generate import Source, append_episode, generate_script, regenerate_episode
from .schema import Asset, AssetResult, Episode, ProjectSettings, ScriptResult, StoryboardResult
from .storyboard import storyboard, storyboard_problems

DEV_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


class StoryRequest(BaseModel):
    settings: ProjectSettings
    mode: Literal["story", "upload"] = "story"
    text: str
    feedback: str = ""


class EpisodeRegenerateRequest(BaseModel):
    script: ScriptResult
    episode: int
    mode: Literal["story", "upload"] = "story"
    text: str = ""
    feedback: str = ""


class EpisodeAppendRequest(BaseModel):
    script: ScriptResult
    mode: Literal["story", "upload"] = "story"
    text: str = ""
    feedback: str = ""


class AssetsRequest(BaseModel):
    script: ScriptResult
    existingAssets: list[Asset] = []


class StoryboardRequest(BaseModel):
    script: ScriptResult
    assets: AssetResult
    episode: int | None = None


@lru_cache(maxsize=1)
def _default_model() -> Model:
    return model_from_env()


def get_model() -> Model:
    """Request dependency so tests can swap in a FunctionModel."""
    return _default_model()


app = FastAPI(title="FrameDrama Lab API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _detail(exc: AgentRunError) -> str:
    status = getattr(exc, "status_code", None)
    detail = f"HTTP {status}" if status else type(exc).__name__
    cause = exc.__cause__
    if cause is not None:
        detail += f"：{str(cause)[:1200]}"
    return detail


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "model": os.getenv("DEEPSEEK_MODEL", "deepseek-flash")}


@app.post("/api/story", response_model=ScriptResult)
async def create_story(body: StoryRequest, model: Model = Depends(get_model)) -> ScriptResult:
    try:
        source = Source.from_text(body.mode, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    started = time.perf_counter()
    log_progress("api", f"收到 /api/story：《{body.settings.name}》· {body.settings.episodeCount} 集 · {body.mode}")
    try:
        result = await generate_script(model, body.settings, source, feedback=body.feedback)
    except AgentRunError as exc:
        log_progress("api", f"/api/story 失败（{time.perf_counter() - started:.1f}s）：{_detail(exc)}")
        raise HTTPException(status_code=502, detail=_detail(exc)) from exc
    log_progress("api", f"/api/story 完成：《{result.settings.name}》共 {len(result.episodes)} 集（{time.perf_counter() - started:.1f}s）")
    return result


@app.post("/api/story/episode", response_model=Episode)
async def rewrite_episode(body: EpisodeRegenerateRequest, model: Model = Depends(get_model)) -> Episode:
    started = time.perf_counter()
    log_progress("api", f"收到 /api/story/episode：《{body.script.settings.name}》· 重写第 {body.episode} 集")
    try:
        source = Source.from_text(body.mode, body.text) if body.text.strip() else None
        result = await regenerate_episode(model, body.script, body.episode, source=source, feedback=body.feedback)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AgentRunError as exc:
        log_progress("api", f"/api/story/episode 失败（{time.perf_counter() - started:.1f}s）：{_detail(exc)}")
        raise HTTPException(status_code=502, detail=_detail(exc)) from exc
    log_progress("api", f"/api/story/episode 完成：第 {result.number} 集（{time.perf_counter() - started:.1f}s）")
    return result


@app.post("/api/story/episode/append", response_model=ScriptResult)
async def create_next_episode(body: EpisodeAppendRequest, model: Model = Depends(get_model)) -> ScriptResult:
    started = time.perf_counter()
    log_progress("api", f"收到 /api/story/episode/append：《{body.script.settings.name}》· 当前 {len(body.script.episodes)} 集")
    try:
        source = Source.from_text(body.mode, body.text) if body.text.strip() else None
        result = await append_episode(model, body.script, source=source, feedback=body.feedback)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AgentRunError as exc:
        log_progress("api", f"/api/story/episode/append 失败（{time.perf_counter() - started:.1f}s）：{_detail(exc)}")
        raise HTTPException(status_code=502, detail=_detail(exc)) from exc
    log_progress("api", f"/api/story/episode/append 完成：现共 {len(result.episodes)} 集（{time.perf_counter() - started:.1f}s）")
    return result


@app.post("/api/assets", response_model=AssetResult)
async def create_assets(body: AssetsRequest, model: Model = Depends(get_model)) -> AssetResult:
    started = time.perf_counter()
    mode_note = f"增量（已有 {len(body.existingAssets)} 项）" if body.existingAssets else "全量"
    log_progress("api", f"收到 /api/assets：《{body.script.settings.name}》· {len(body.script.episodes)} 集 · {mode_note}")
    try:
        result = await analyze_assets(model, body.script, existing=body.existingAssets)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AgentRunError as exc:
        log_progress("api", f"/api/assets 失败（{time.perf_counter() - started:.1f}s）：{_detail(exc)}")
        raise HTTPException(status_code=502, detail=_detail(exc)) from exc
    log_progress("api", f"/api/assets 完成：共 {len(result.assets)} 项资产（{time.perf_counter() - started:.1f}s）")
    return result


@app.post("/api/storyboard", response_model=StoryboardResult)
async def create_storyboard(body: StoryboardRequest, model: Model = Depends(get_model)) -> StoryboardResult:
    started = time.perf_counter()
    scope = f"第 {body.episode} 集" if body.episode is not None else f"全部 {len(body.script.episodes)} 集"
    log_progress("api", f"收到 /api/storyboard：《{body.script.settings.name}》· {scope}")
    try:
        result = await storyboard(model, body.script, body.assets, body.episode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AgentRunError as exc:
        log_progress("api", f"/api/storyboard 失败（{time.perf_counter() - started:.1f}s）：{_detail(exc)}")
        raise HTTPException(status_code=502, detail=_detail(exc)) from exc
    problems = storyboard_problems(result, body.script)
    if problems:
        log_progress("api", f"/api/storyboard 校验失败（{time.perf_counter() - started:.1f}s）：{'；'.join(problems)}")
        raise HTTPException(status_code=500, detail="分镜未通过检查：" + "；".join(problems))
    log_progress("api", f"/api/storyboard 完成：{len(result.episodes)} 集（{time.perf_counter() - started:.1f}s）")
    return result


def main() -> int:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Run the FrameDrama Lab API.")
    parser.add_argument("--reload", action="store_true", help="代码变更时自动重启")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = parser.parse_args()
    uvicorn.run("framedrama_lab.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
