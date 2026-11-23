import pytest
from pydantic import ValidationError

from app.modules.canvas.schemas import (
    CanvasGraphPayload,
    CanvasMediaPayload,
    CanvasUpdateRequest,
    UserAssetCreateRequest,
)


def test_canvas_media_rejects_blob_and_data_urls():
    with pytest.raises(ValidationError):
        CanvasMediaPayload.model_validate({"url": "blob:http://localhost:5173/abc", "name": "a.png"})

    with pytest.raises(ValidationError):
        CanvasMediaPayload.model_validate({"url": "data:image/png;base64,AAAA", "name": "a.png"})

    ok = CanvasMediaPayload.model_validate(
        {
            "url": "https://image.nodepass.net/framedrama/1/images/test.png",
            "key": "framedrama/1/images/test.png",
            "name": "test.png",
            "modelId": "gpt-image-2",
        }
    )
    dumped = ok.model_dump(by_alias=True, exclude_none=True)
    assert dumped["url"].startswith("https://")
    assert dumped["modelId"] == "gpt-image-2"


def test_canvas_update_request_validates_camel_case_graph_and_version():
    req = CanvasUpdateRequest.model_validate(
        {
            "expectedVersion": 3,
            "name": "都市悬疑画布",
            "viewport": {"x": 12.5, "y": -8, "zoom": 1.25},
            "graphData": {
                "nodes": [
                    {
                        "id": "node-1",
                        "type": "image-generation",
                        "position": {"x": 100, "y": 200},
                        "data": {
                            "title": "主场景",
                            "prompt": "雨夜档案室 {{ref:node-0}}",
                            "settings": {"modelId": "gpt-image-2", "tier": "2k", "ratio": "16:9"},
                            "referenceOrder": ["node-0"],
                        },
                    }
                ],
                "edges": [{"id": "e1", "source": "node-0", "target": "node-1"}],
            },
        }
    )
    assert req.expected_version == 3
    assert req.graph_data is not None
    assert len(req.graph_data.nodes) == 1
    assert req.graph_data.nodes[0].data.settings is not None
    assert req.graph_data.nodes[0].data.settings.tier == "2k"


def test_canvas_graph_enforces_history_cap_and_user_asset_url_validation():
    too_many = [{"url": f"https://example.com/{i}.png", "name": f"{i}.png"} for i in range(21)]
    with pytest.raises(ValidationError):
        CanvasGraphPayload.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "image-generation",
                        "position": {"x": 0, "y": 0},
                        "data": {"history": too_many},
                    }
                ],
                "edges": [],
            }
        )

    with pytest.raises(ValidationError):
        UserAssetCreateRequest.model_validate(
            {"kind": "image", "title": "bad", "mediaUrl": "blob:http://localhost/1"}
        )

    valid_asset = UserAssetCreateRequest.model_validate(
        {
            "kind": "image",
            "title": "雨夜角色图",
            "mediaUrl": "https://image.nodepass.net/framedrama/1/images/a.png",
            "mediaName": "a.png",
            "sourceType": "canvas",
        }
    )
    assert valid_asset.media_url is not None


def test_resolve_canvas_generation_inputs_handles_refs_and_rejects_unsupported_media():
    from app.core.errors import AppError
    from app.modules.canvas.generation import resolve_canvas_generation_inputs
    from app.modules.canvas.schemas import CanvasGenerateRequest

    video_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "video",
            "prompt": "镜头推进 {{ref:img-1}}，结合 {{ref:txt-1}}",
            "references": [
                {
                    "nodeId": "img-1",
                    "kind": "image",
                    "title": "主角图",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/images/hero.png",
                },
                {
                    "nodeId": "txt-1",
                    "kind": "text",
                    "title": "氛围",
                    "text": "冷调雨夜",
                },
                {
                    "nodeId": "txt-2",
                    "kind": "text",
                    "title": "补充",
                    "text": "电影质感",
                },
            ],
        }
    )
    resolved = resolve_canvas_generation_inputs(video_req)
    assert resolved.reference_urls == ["https://image.nodepass.net/framedrama/1/images/hero.png"]
    assert "@[图片1]" in resolved.resolved_prompt
    assert "冷调雨夜" in resolved.resolved_prompt
    assert "电影质感" in resolved.resolved_prompt

    multimodal_video_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "video",
            "prompt": "参考 {{ref:vid-1}} 的运镜和 {{ref:aud-1}} 的节奏",
            "references": [
                {
                    "nodeId": "vid-1",
                    "kind": "video",
                    "title": "运镜参考",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/videos/old.mp4",
                },
                {
                    "nodeId": "aud-1",
                    "kind": "audio",
                    "title": "配乐",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/audios/bgm.mp3",
                },
            ],
        }
    )
    resolved_mm = resolve_canvas_generation_inputs(multimodal_video_req)
    assert resolved_mm.reference_video_urls == [
        "https://image.nodepass.net/framedrama/1/videos/old.mp4"
    ]
    assert resolved_mm.reference_audio_urls == [
        "https://image.nodepass.net/framedrama/1/audios/bgm.mp3"
    ]
    assert "@[视频1]" in resolved_mm.resolved_prompt
    assert "@[音频1]" in resolved_mm.resolved_prompt

    bad_img_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "image",
            "prompt": "参考视频生图",
            "references": [
                {
                    "nodeId": "vid-1",
                    "kind": "video",
                    "title": "旧视频",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/videos/old.mp4",
                }
            ],
        }
    )
    with pytest.raises(AppError) as err:
        resolve_canvas_generation_inputs(bad_img_req)
    assert err.value.code == "unsupported_image_reference"

    img_edit_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "image",
            "prompt": "把 {{ref:img-1}} 的服装换成深蓝色晚礼服，结合 {{ref:txt-1}}",
            "references": [
                {
                    "nodeId": "img-1",
                    "kind": "image",
                    "title": "主角参考图",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/images/ref.png",
                },
                {
                    "nodeId": "txt-1",
                    "kind": "text",
                    "title": "光影",
                    "text": "暖调夜景",
                },
            ],
        }
    )
    img_resolved = resolve_canvas_generation_inputs(img_edit_req)
    assert img_resolved.reference_urls == ["https://image.nodepass.net/framedrama/1/images/ref.png"]
    assert "@[图片1]" in img_resolved.resolved_prompt
    assert "暖调夜景" in img_resolved.resolved_prompt

    empty_img_prompt_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "image",
            "prompt": "   ",
            "references": [
                {
                    "nodeId": "img-1",
                    "kind": "image",
                    "title": "参考",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/images/ref.png",
                }
            ],
        }
    )
    with pytest.raises(AppError) as empty_err:
        resolve_canvas_generation_inputs(empty_img_prompt_req)
    assert empty_err.value.code == "prompt_missing"

    text_vision_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "text",
            "prompt": "描述 {{ref:img-1}} 里的人物穿搭",
            "references": [
                {
                    "nodeId": "img-1",
                    "kind": "image",
                    "title": "主角定妆照",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/images/hero.jpg",
                }
            ],
        }
    )
    text_resolved = resolve_canvas_generation_inputs(text_vision_req)
    assert text_resolved.reference_urls == ["https://image.nodepass.net/framedrama/1/images/hero.jpg"]
    assert text_resolved.reference_images == [
        {
            "index": "1",
            "title": "主角定妆照",
            "url": "https://image.nodepass.net/framedrama/1/images/hero.jpg",
        }
    ]
    assert "@[图片1]" in text_resolved.resolved_prompt


def test_resolve_canvas_generation_inputs_unified_at_slot_syntax():
    from app.modules.canvas.generation import resolve_canvas_generation_inputs
    from app.modules.canvas.schemas import CanvasGenerateRequest

    video_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "video",
            "prompt": "镜头推进 @[图片1]，参考 @[视频1] 运镜，配 @[音频1] 节奏，氛围为 @[文本1]",
            "references": [
                {
                    "nodeId": "img-1",
                    "kind": "image",
                    "title": "主角图",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/images/hero.png",
                },
                {
                    "nodeId": "vid-1",
                    "kind": "video",
                    "title": "运镜参考",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/videos/cam.mp4",
                },
                {
                    "nodeId": "aud-1",
                    "kind": "audio",
                    "title": "配乐",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/audios/bgm.mp3",
                },
                {
                    "nodeId": "txt-1",
                    "kind": "text",
                    "title": "氛围",
                    "text": "冷调雨夜",
                },
                {
                    "nodeId": "txt-2",
                    "kind": "text",
                    "title": "补充",
                    "text": "胶片颗粒感",
                },
            ],
        }
    )
    resolved = resolve_canvas_generation_inputs(video_req)
    assert resolved.reference_urls == ["https://image.nodepass.net/framedrama/1/images/hero.png"]
    assert resolved.reference_video_urls == ["https://image.nodepass.net/framedrama/1/videos/cam.mp4"]
    assert resolved.reference_audio_urls == ["https://image.nodepass.net/framedrama/1/audios/bgm.mp3"]
    assert "@[图片1]" in resolved.resolved_prompt
    assert "@[视频1]" in resolved.resolved_prompt
    assert "@[音频1]" in resolved.resolved_prompt
    assert "@[文本1]" not in resolved.resolved_prompt
    # Referenced @[文本1] is expanded inline once (not duplicated into unreferenced context)
    assert resolved.resolved_prompt.count("冷调雨夜") == 1
    # Unreferenced txt-2 is appended as context
    assert "胶片颗粒感" in resolved.resolved_prompt

    img_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "image",
            "prompt": "把 @[图片1] 调整为 @[文本1] 风格",
            "references": [
                {
                    "nodeId": "img-1",
                    "kind": "image",
                    "title": "主角图",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/images/hero.png",
                },
                {
                    "nodeId": "txt-1",
                    "kind": "text",
                    "title": "画风",
                    "text": "新中式工笔画",
                },
            ],
        }
    )
    img_resolved = resolve_canvas_generation_inputs(img_req)
    assert img_resolved.resolved_prompt == "把 @[图片1] 调整为 新中式工笔画 风格"

    # Canvas text generation: @[文本1] inlined in prompt must not be duplicated in reference_texts
    text_dedup_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "text",
            "prompt": "把 @[文本1] 扩写成电影分镜",
            "references": [
                {
                    "nodeId": "txt-1",
                    "kind": "text",
                    "title": "大纲",
                    "text": "雨夜街头追逐",
                },
                {
                    "nodeId": "txt-2",
                    "kind": "text",
                    "title": "画风要求",
                    "text": "冷峻写实",
                },
            ],
        }
    )
    text_dedup = resolve_canvas_generation_inputs(text_dedup_req)
    assert text_dedup.resolved_prompt == "把 雨夜街头追逐 扩写成电影分镜"
    assert text_dedup.reference_texts == [{"title": "画风要求", "text": "冷峻写实"}]


def test_resolve_canvas_generation_inputs_blocks_removed_reference_tokens():
    from app.core.errors import AppError
    from app.modules.canvas.generation import (
        find_removed_prompt_refs,
        resolve_canvas_generation_inputs,
    )
    from app.modules.canvas.schemas import CanvasGenerateRequest

    assert find_removed_prompt_refs("@[已移除:陈国栋] 与 @[已移除:旧道具] 和 @[已移除:陈国栋]") == [
        "陈国栋",
        "旧道具",
    ]
    assert find_removed_prompt_refs("正常提示词 @[图片1]") == []

    bad_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "video",
            "prompt": "@[已移除:陈国栋] 走进大厅，看向 @[图片1]",
            "references": [
                {
                    "nodeId": "img-1",
                    "kind": "image",
                    "title": "大厅",
                    "mediaUrl": "https://image.nodepass.net/framedrama/1/images/hall.png",
                }
            ],
        }
    )
    with pytest.raises(AppError) as err:
        resolve_canvas_generation_inputs(bad_req)
    assert err.value.code == "prompt_has_removed_reference"
    assert "陈国栋" in err.value.message


@pytest.mark.asyncio
async def test_generate_canvas_text_passes_image_urls_as_multimodal_parts() -> None:
    from pydantic_ai import ImageUrl
    from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    from app.modules.canvas.generation import generate_canvas_text

    seen_image_urls: list[str] = []

    def fake_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for msg in messages:
            for part in getattr(msg, "parts", ()):
                content = getattr(part, "content", None)
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, ImageUrl):
                            seen_image_urls.append(item.url)
        return ModelResponse(parts=[TextPart("身穿驼色大衣与深红围巾的女性全身肖像。")])

    output = await generate_canvas_text(
        FunctionModel(fake_model),
        prompt="这是一张什么样的图片？",
        reference_images=[
            {
                "index": "1",
                "title": "图片素材",
                "url": "https://image.nodepass.net/framedrama/1/images/coat.jpg",
            }
        ],
    )
    assert seen_image_urls == ["https://image.nodepass.net/framedrama/1/images/coat.jpg"]
    assert "驼色大衣" in output

