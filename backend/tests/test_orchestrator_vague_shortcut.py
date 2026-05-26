"""Tests for orchestrator vague-diagnosis-query shortcut (AI首-2 fix from 试用反馈)."""

from __future__ import annotations

import pytest

from agents.orchestrator import (
    VAGUE_QUERY_REPLY,
    _is_vague_diagnosis_query,
    orchestrate,
)


class TestIsVagueDiagnosisQuery:
    """覆盖 _is_vague_diagnosis_query 各分支命中与否。"""

    @pytest.mark.parametrize("text", [
        "检查下这台车的问题",
        "看看这台车有什么问题",
        "分析下这个车的情况",
        "诊断下这台车",
        "帮我看看有什么问题",
        "看看这台车",
        "查一下这台车",
        "看下这台车情况",
        "分析一下日志",
        "看看日志",
    ])
    def test_hits(self, text: str) -> None:
        assert _is_vague_diagnosis_query(text), f"应识别为模糊提问: {text!r}"

    @pytest.mark.parametrize("text", [
        # 命中具体现象/动词
        "看看 iCGM 升级失败的原因",
        "分析下 OTA 卡在 30% 的问题",
        "检查下 MPU 黑屏的故障",
        "看看为什么刷写失败",
        "帮我看看错误码 0x1234",
        # 命中时间锚点
        "看看昨天的日志",
        "分析下今天上午的故障",
        # 命中 ECU
        "分析下 TBOX 情况",
        "看看 IVI 的问题",
        # meta-query 不应被误判
        "你是谁",
        "你好",
        # 长描述
        "这台车在 9 月 11 日凌晨发生了多次重启，可能跟 FOTA 有关",
        # 空字符串
        "",
        # 太短
        "看",
    ])
    def test_misses(self, text: str) -> None:
        assert not _is_vague_diagnosis_query(text), f"不应识别为模糊提问: {text!r}"


class TestOrchestrateVagueShortcut:
    """端到端验证模糊提问不调 LLM、直接返回引导式澄清。"""

    @pytest.mark.asyncio
    async def test_vague_query_does_not_call_llm(self, monkeypatch) -> None:
        async def fake_chat_completion(*args, **kwargs):
            raise AssertionError("模糊提问命中时不应调用 LLM")

        monkeypatch.setattr(
            "agents.orchestrator.chat_completion", fake_chat_completion
        )

        events = []
        async for ev in orchestrate(
            user_message="检查下这台车的问题",
            scenario_id="fota-diagnostic",
        ):
            events.append(ev)

        types = [e["type"] for e in events]
        assert "step_start" in types
        assert "step_complete" in types
        assert "content_delta" in types
        assert "done" in types

        delta_text = "".join(
            e["content"] for e in events if e["type"] == "content_delta"
        )
        assert delta_text == VAGUE_QUERY_REPLY
        assert "故障现象" in delta_text
        assert "ECU" in delta_text

    @pytest.mark.asyncio
    async def test_specific_query_still_calls_llm(self, monkeypatch) -> None:
        """有具体锚点（ECU+错误码）的提问必须走正常 router 流程。"""
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
        assert any(e["type"] == "done" for e in events)
