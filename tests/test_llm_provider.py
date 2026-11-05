"""Kiểm tra serialize schema bằng SDK thật, mock HTTP và thông báo lỗi Gemini sạch."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from google import genai
from google.genai import errors, types

from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.llm.llm_provider import LLMProvider

CONTEXT = "[S1] Tài liệu kiểm thử — Mục kiểm thử\nThis is evidence used only for a software test."


def test_json_schema_serialization_with_real_sdk():
    """Chạy bộ serialize SDK thật để bắt lỗi additionalProperties trước khi gọi mạng."""
    captured = []
    answer = {
        "claims": [
            {
                "text": "Nội dung dành riêng cho kiểm thử phần mềm.",
                "supporting_passage_ids": ["S1.P1"],
            }
        ],
        "insufficient_evidence": False,
    }

    def handle(request: httpx.Request) -> httpx.Response:
        """Ghi request đã serialize và trả JSON giả lập, không gọi Gemini thật."""
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": json.dumps(answer)}]},
                        "finishReason": "STOP",
                    }
                ],
            },
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as transport,
        genai.Client(
            api_key="test-only", http_options=types.HttpOptions(httpx_client=transport)
        ) as client,
    ):
        result = LLMProvider(Settings(gemini_api_key=""), client).generate("Kiểm thử", CONTEXT)
    assert result.claims[0].citation_ids == ["S1"]
    assert result.claims[0].supporting_quotes == {
        "S1": "This is evidence used only for a software test."
    }
    payload = json.loads(captured[0]["contents"][0]["parts"][0]["text"])
    assert payload["EVIDENCE"][0]["passage_id"] == "S1.P1"
    assert payload["EVIDENCE"][0]["text"] == result.claims[0].supporting_quotes["S1"]
    config = captured[0]["generationConfig"]
    thinking = config["thinkingConfig"]
    # SDK có thể giữ tên proto snake_case hoặc đổi sang JSON camelCase.
    assert thinking.get("thinkingBudget", thinking.get("thinking_budget")) == 0
    assert "responseSchema" not in config
    schema = config["responseJsonSchema"]
    assert schema["additionalProperties"] is False
    claim_schema = schema["$defs"]["PassageClaim"]
    assert claim_schema["additionalProperties"] is False
    assert claim_schema["properties"]["supporting_passage_ids"]["items"] == {"type": "string"}


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "llm_request_invalid"),
        (404, "llm_model_not_found"),
        (429, "llm_rate_limited"),
        (504, "llm_timeout"),
    ],
)
def test_provider_failure_has_safe_specific_error(status, code):
    """Phân biệt lỗi cấu hình, model, quota, timeout mà không lộ nội dung provider."""
    client = Mock()
    client.models.generate_content.side_effect = errors.APIError(
        status,
        {
            "error": {"code": status, "message": "private-provider-details-and-test-key"},
        },
    )
    with pytest.raises(ServiceError) as caught:
        LLMProvider(Settings(), client).generate("Kiểm thử", CONTEXT)
    assert caught.value.code == code
    assert "private-provider-details" not in str(caught.value)


@pytest.mark.parametrize(
    "text", ["not-json", '{"claims": [], "insufficient_evidence": true, "extra": 1}']
)
def test_invalid_json_response_still_rejected(text):
    """Dùng JSON Schema mới vẫn phải xác thực chặt nội dung response ở backend."""
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    with pytest.raises(ServiceError) as caught:
        LLMProvider(Settings(), client).generate("Kiểm thử", CONTEXT)
    assert caught.value.code == "llm_response_invalid"


@pytest.mark.parametrize("passage_ids", [["S99.P1"], ["S1.P99"], ["S1.P1", "S1.P1"]])
def test_unknown_or_duplicate_passages_are_rejected(passage_ids):
    """Không chấp nhận mã bịa, mã từ request khác hoặc lựa chọn trùng."""
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps(
            {
                "claims": [{"text": "Nhận định kiểm thử.", "supporting_passage_ids": passage_ids}],
                "insufficient_evidence": False,
            }
        )
    )
    with pytest.raises(ServiceError) as caught:
        LLMProvider(Settings(), client).generate("Kiểm thử", CONTEXT)
    assert caught.value.code == "llm_evidence_invalid"


def test_empty_context_does_not_call_gemini():
    """Thiếu nguồn thì báo thiếu bằng chứng, tránh gọi Gemini vô ích."""
    client = Mock()
    answer = LLMProvider(Settings(), client).generate("Kiểm thử", "")
    assert answer.insufficient_evidence
    assert not answer.claims
    client.models.generate_content.assert_not_called()
