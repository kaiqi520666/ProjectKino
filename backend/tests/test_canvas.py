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

    bad_video_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "video",
            "prompt": "参考视频",
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
        resolve_canvas_generation_inputs(bad_video_req)
    assert err.value.code == "unsupported_video_reference"

    bad_img_req = CanvasGenerateRequest.model_validate(
        {
            "kind": "image",
            "prompt": "参考图",
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
    with pytest.raises(AppError) as img_err:
        resolve_canvas_generation_inputs(bad_img_req)
    assert img_err.value.code == "image_reference_not_supported"

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

