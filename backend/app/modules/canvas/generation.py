import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

from app.core.errors import AppError
from app.modules.canvas.schemas import CanvasGenerateReference, CanvasGenerateRequest

_REF_TOKEN_RE = re.compile(r"\{\{ref:([\w-]+)\}\}")

_CANVAS_TEXT_INSTRUCTIONS = (
    "你是 FrameDrama 画布创作助手，擅长影视短剧大纲、角色设定、分镜提示词润色与视觉画面描述。"
    "请严格按用户指令与参考上下文直接输出高质量的中文 Markdown 正文，"
    "不要输出无关寒暄或解释说明。"
)


@dataclass(frozen=True)
class ResolvedCanvasGeneration:
    resolved_prompt: str
    reference_urls: list[str]
    reference_texts: list[dict[str, str]]


def resolve_canvas_generation_inputs(body: CanvasGenerateRequest) -> ResolvedCanvasGeneration:
    refs_by_id: dict[str, CanvasGenerateReference] = {ref.node_id: ref for ref in body.references}
    image_refs: list[CanvasGenerateReference] = []
    image_index_by_node: dict[str, int] = {}
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
        if image_refs:
            raise AppError(
                400,
                "image_reference_not_supported",
                "当前生图模型暂仅支持文生图，请先断开上游图片连线或用文本描述画面",
            )
    elif body.kind == "video":
        for ref in body.references:
            if ref.kind in ("video", "audio"):
                raise AppError(
                    400,
                    "unsupported_video_reference",
                    "当前视频模型暂不支持直接引用视频或音频节点，请连接图片或文本节点",
                )
            if ref.kind == "image" and ref.media_url:
                image_refs.append(ref)
                image_index_by_node[ref.node_id] = len(image_refs)
            elif ref.kind == "text" and (ref.text or "").strip():
                reference_texts.append(
                    {"title": ref.title or "参考文本", "text": (ref.text or "").strip()}
                )
    else:
        for ref in body.references:
            if ref.kind == "text" and (ref.text or "").strip():
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

    if not resolved and not reference_texts:
        raise AppError(400, "prompt_missing", "请输入提示词或连接包含内容的参考节点")

    return ResolvedCanvasGeneration(
        resolved_prompt=resolved,
        reference_urls=[ref.media_url for ref in image_refs if ref.media_url],
        reference_texts=reference_texts,
    )


async def generate_canvas_text(
    model: Model,
    *,
    prompt: str,
    current_text: str | None = None,
    reference_texts: list[dict[str, str]] | None = None,
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

    if current_text and current_text.strip():
        sections.append(f"## 当前节点已有文本\n\n{current_text.strip()}")

    sections.append(f"## 创作指令\n\n{prompt.strip() or '请基于以上参考内容整理并扩写为清晰的结构化正文。'}")
    user_message = "\n\n".join(sections)

    agent = Agent(model, output_type=str, instructions=_CANVAS_TEXT_INSTRUCTIONS)
    result = await agent.run(user_message, usage=usage)
    text = (result.output or "").strip()
    if not text:
        raise AppError(502, "empty_llm_output", "语言模型未返回有效文本，请重试")

    if on_progress:
        await on_progress(2, 2, "文本生成完成，正在写回画布节点...", 90)
    return text
