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
