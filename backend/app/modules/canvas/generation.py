import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic_ai import Agent, ImageUrl, UserContent
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

from app.core.errors import AppError
from app.modules.canvas.schemas import CanvasGenerateReference, CanvasGenerateRequest

_REF_TOKEN_RE = re.compile(r"\{\{ref:([\w-]+)\}\}")

_CANVAS_TEXT_INSTRUCTIONS = (
    "你是 FrameDrama 画布创作助手，擅长视觉画面分析、影视短剧大纲、角色设定、分镜提示词润色与视觉画面描述。"
    "当输入附带参考图片时，请仔细观察图片中的人物、服饰、场景、光影、构图与风格细节。"
    "请严格按用户指令与参考上下文直接输出高质量的中文 Markdown 正文，"
    "不要输出无关寒暄或解释说明。"
)


@dataclass(frozen=True)
class ResolvedCanvasGeneration:
    resolved_prompt: str
    reference_urls: list[str]
    reference_video_urls: list[str]
    reference_audio_urls: list[str]
    reference_texts: list[dict[str, str]]
    reference_images: list[dict[str, str]]


def resolve_canvas_generation_inputs(body: CanvasGenerateRequest) -> ResolvedCanvasGeneration:
    refs_by_id: dict[str, CanvasGenerateReference] = {ref.node_id: ref for ref in body.references}
    image_refs: list[CanvasGenerateReference] = []
    video_refs: list[CanvasGenerateReference] = []
    audio_refs: list[CanvasGenerateReference] = []
    image_index_by_node: dict[str, int] = {}
    video_index_by_node: dict[str, int] = {}
    audio_index_by_node: dict[str, int] = {}
    reference_texts: list[dict[str, str]] = []

    if body.kind == "image":
        for ref in body.references:
            if ref.kind in ("video", "audio"):
                raise AppError(
                    400,
                    "unsupported_image_reference",
                    "图片生成节点仅支持连接文本或图片节点，请先断开视频/音频连线",
                )
            if ref.kind == "image" and ref.media_url:
                image_refs.append(ref)
                image_index_by_node[ref.node_id] = len(image_refs)
            elif ref.kind == "text" and (ref.text or "").strip():
                reference_texts.append(
                    {"title": ref.title or "参考文本", "text": (ref.text or "").strip()}
                )
    elif body.kind == "video":
        for ref in body.references:
            if ref.kind == "image" and ref.media_url:
                image_refs.append(ref)
                image_index_by_node[ref.node_id] = len(image_refs)
            elif ref.kind == "video" and ref.media_url:
                video_refs.append(ref)
                video_index_by_node[ref.node_id] = len(video_refs)
            elif ref.kind == "audio" and ref.media_url:
                audio_refs.append(ref)
                audio_index_by_node[ref.node_id] = len(audio_refs)
            elif ref.kind == "text" and (ref.text or "").strip():
                reference_texts.append(
                    {"title": ref.title or "参考文本", "text": (ref.text or "").strip()}
                )
    else:
        for ref in body.references:
            if ref.kind == "image" and ref.media_url:
                image_refs.append(ref)
                image_index_by_node[ref.node_id] = len(image_refs)
            elif ref.kind == "text" and (ref.text or "").strip():
                reference_texts.append(
                    {"title": ref.title or "参考文本", "text": (ref.text or "").strip()}
                )

    referenced_text_ids: set[str] = set()

    def _replace_ref(match: re.Match[str]) -> str:
        node_id = match.group(1)
        ref = refs_by_id.get(node_id)
        if ref is None:
            return ""
        if ref.kind == "image" and node_id in image_index_by_node:
            return f"@[图片{image_index_by_node[node_id]}]"
        if ref.kind == "video" and node_id in video_index_by_node:
            return f"@[视频{video_index_by_node[node_id]}]"
        if ref.kind == "audio" and node_id in audio_index_by_node:
            return f"@[音频{audio_index_by_node[node_id]}]"
        if ref.kind == "text" and (ref.text or "").strip():
            referenced_text_ids.add(node_id)
            return (ref.text or "").strip()
        return ref.title or ""

    resolved = _REF_TOKEN_RE.sub(_replace_ref, body.prompt or "").strip()

    # For image/video generation, if user connected upstream text nodes without using @mention,
    # append them cleanly so connected text context is never silently dropped.
    if body.kind in ("image", "video"):
        unreferenced_texts = [
            (ref.text or "").strip()
            for ref in body.references
            if ref.kind == "text" and ref.node_id not in referenced_text_ids and (ref.text or "").strip()
        ]
        if unreferenced_texts:
            prefix = "\n".join(unreferenced_texts)
            resolved = f"{prefix}\n{resolved}".strip() if resolved else prefix

    if body.kind in ("image", "video") and not resolved:
        raise AppError(400, "prompt_missing", "请输入提示词或连接包含文本内容的参考节点")
    if not resolved and not reference_texts and not image_refs:
        raise AppError(400, "prompt_missing", "请输入提示词或连接包含内容的参考节点")

    reference_images = [
        {
            "index": str(idx),
            "title": ref.title or f"图片{idx}",
            "url": ref.media_url,
        }
        for idx, ref in enumerate(image_refs, start=1)
        if ref.media_url
    ]

    return ResolvedCanvasGeneration(
        resolved_prompt=resolved,
        reference_urls=[ref.media_url for ref in image_refs if ref.media_url],
        reference_video_urls=[ref.media_url for ref in video_refs if ref.media_url],
        reference_audio_urls=[ref.media_url for ref in audio_refs if ref.media_url],
        reference_texts=reference_texts,
        reference_images=reference_images,
    )


async def generate_canvas_text(
    model: Model,
    *,
    prompt: str,
    current_text: str | None = None,
    reference_texts: list[dict[str, str]] | None = None,
    reference_urls: list[str] | None = None,
    reference_images: list[dict[str, str]] | None = None,
    usage: RunUsage | None = None,
    on_progress: Callable[[int, int, str, int], Awaitable[None]] | None = None,
) -> str:
    if on_progress:
        await on_progress(1, 2, "正在组装画布上下文并调用语言模型...", 25)

    sections: list[str] = []
    if reference_texts:
        ref_lines = [
            f"### {item.get('title') or '参考文本'}\n{item.get('text') or ''}"
            for item in reference_texts
            if (item.get("text") or "").strip()
        ]
        if ref_lines:
            sections.append("## 上游参考内容\n\n" + "\n\n".join(ref_lines))

    clean_image_urls: list[str] = []
    image_labels: list[str] = []
    if reference_images:
        for idx, item in enumerate(reference_images, start=1):
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            clean_image_urls.append(url)
            title = str(item.get("title") or f"图片{idx}").strip()
            image_labels.append(f"@[图片{idx}]（{title}）")
    elif reference_urls:
        for idx, raw_url in enumerate(reference_urls, start=1):
            url = str(raw_url or "").strip()
            if not url:
                continue
            clean_image_urls.append(url)
            image_labels.append(f"@[图片{idx}]")

    if clean_image_urls:
        sections.append(
            "## 上游参考图片\n\n"
            f"本消息附带了 {len(clean_image_urls)} 张参考图片，按顺序对应：{'、'.join(image_labels)}。"
            "请结合图片视觉内容直接回答或创作。"
        )

    if current_text and current_text.strip():
        sections.append(f"## 当前节点已有文本\n\n{current_text.strip()}")

    default_instruction = (
        "请详细分析并描述以上参考图片的画面内容（人物、服饰、动作、场景、光影与氛围）。"
        if clean_image_urls and not reference_texts
        else "请基于以上参考内容整理并扩写为清晰的结构化正文。"
    )
    sections.append(f"## 创作指令\n\n{prompt.strip() or default_instruction}")
    user_message = "\n\n".join(sections)

    user_input: str | list[UserContent] = (
        [user_message, *(ImageUrl(url=url) for url in clean_image_urls)]
        if clean_image_urls
        else user_message
    )

    agent = Agent(model, output_type=str, instructions=_CANVAS_TEXT_INSTRUCTIONS)
    result = await agent.run(user_input, usage=usage)
    text = (result.output or "").strip()
    if not text:
        raise AppError(502, "empty_llm_output", "语言模型未返回有效文本，请重试")

    if on_progress:
        await on_progress(2, 2, "文本生成完成，正在写回画布节点...", 90)
    return text
