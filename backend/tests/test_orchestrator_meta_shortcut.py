"""Tests for orchestrator meta-query shortcut (A1/A2 fix from 试用反馈)."""

from __future__ import annotations

import pytest

from agents.orchestrator import _is_meta_query, orchestrate, META_QUERY_REPLY


class TestIsMetaQuery:
    """覆盖 _META_QUERY_PATTERNS 各分支命中与否。"""

    @pytest.mark.parametrize("text", [
        "你是什么模型",
        "你是谁",
        "你是哪个模型",
        "你叫什么",
        "你叫啥",
        "你能做什么",
        "你能帮什么",
        "你用的是什么模型",
        "你的版本",
        "你的能力",
        "介绍一下你",
        "介绍下自己",
        "你好",
        "您好",
        "在吗",
        "在么？",
        "hi",
        "Hello",
        "  你是什么模型  ",  # 含空格
    ])
    def test_hits(self, text: str) -> None:
        assert _is_meta_query(text), f"应识别为 meta query: {text!r}"

    @pytest.mark.parametrize("text", [
        "检查最后升级的这个错误为什么发生",
        "iCGM 升级失败，错误码 0x1234",
        "9月11日晚上车机重启了，怎么回事",
        "帮我看看 MPU 的日志",
        "OTA 卡在 30% 不动了",
        "你能查一下这台车 9 月 11 日为什么 OTA 失败吗",  # >30 字
        "",
    ])
    def test_misses(self, text: str) -> None:
        assert not _is_meta_query(text), f"不应识别为 meta query: {text!r}"


class TestOrchestrateMetaShortcut:
    """端到端验证 meta query 不调 LLM、直接返回固定回复。"""

    @pytest.mark.asyncio
    async def test_meta_query_does_not_call_llm(self, monkeypatch) -> None:
        """命中 meta query 时不应调用 chat_completion。"""
        call_count = {"n": 0}

        async def fake_chat_completion(*args, **kwargs):
            call_count["n"] += 1
            raise AssertionError("不应调用 LLM")

        monkeypatch.setattr(
            "agents.orchestrator.chat_completion", fake_chat_completion
        )

        events = []
        async for ev in orchestrate(
            user_message="你是什么模型",
            scenario_id="fota-diagnostic",
        ):
            events.append(ev)

        assert call_count["n"] == 0
        # 应当包含 step_start + step_complete + content_start + content_delta + content_complete + done
        types = [e["type"] for e in events]
        assert "step_start" in types
        assert "step_complete" in types
        assert "content_delta" in types
        assert "done" in types

        # content_delta 必须包含固定回复的关键短语
        delta_text = "".join(
            e["content"] for e in events if e["type"] == "content_delta"
        )
        assert "Velab FOTA 智能诊断助手" in delta_text
        assert delta_text == META_QUERY_REPLY

    @pytest.mark.asyncio
    async def test_normal_query_still_calls_llm(self, monkeypatch) -> None:
        """非 meta query 必须走正常 router 流程（即调用 LLM）。"""
        called = {"n": 0}

        async def fake_chat_completion(*args, **kwargs):
            called["n"] += 1

            class _Msg:
                content = "<<<THINKING>>>\n短\n<<<USER>>>\n请补充信息"

            return _Msg()

        def fake_parse_tool_calls(_resp):
            return []

        monkeypatch.setattr(
            "agents.orchestrator.chat_completion", fake_chat_completion
        )
        monkeypatch.setattr(
            "agents.orchestrator.parse_tool_calls", fake_parse_tool_calls
        )

        events = []
        async for ev in orchestrate(
            user_message="iCGM 升级失败，错误码 0x1234",
            scenario_id="fota-diagnostic",
        ):
            events.append(ev)

        assert called["n"] == 1
