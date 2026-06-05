from __future__ import annotations

from datetime import datetime, timezone

# 合法 UUID 格式（与前端 crypto.randomUUID() 保持一致）
_SID_1 = "11111111-0001-0001-0001-000000000001"
_SID_2 = "22222222-0002-0002-0002-000000000002"


def _session_payload(session_id: str = _SID_1) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": session_id,
        "title": "测试会话",
        "messages": [
            {
                "id": "m1",
                "role": "user",
                "content": "hello",
                "timestamp": now,
            },
            {
                "id": "m2",
                "role": "assistant",
                "content": "world",
                "timestamp": now,
                "thinking": {"steps": [], "isExpanded": False},
            },
        ],
        "createdAt": now,
        "updatedAt": now,
        "titleSource": "manual",
        "titleAutoOptimized": False,
        "turnCount": 1,
    }


def test_upsert_and_get_session(client):
    payload = _session_payload(_SID_1)
    upsert = client.put(f"/api/sessions/{_SID_1}", json=payload)
    assert upsert.status_code == 200
    assert upsert.json()["id"] == _SID_1

    detail = client.get(f"/api/sessions/{_SID_1}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["title"] == "测试会话"
    assert len(body["messages"]) == 2
    assert body["messages"][1]["content"] == "world"


def test_list_and_delete_session(client):
    payload = _session_payload(_SID_2)
    client.put(f"/api/sessions/{_SID_2}", json=payload)

    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    rows = listed.json()
    assert any(row["id"] == _SID_2 for row in rows)

    deleted = client.delete(f"/api/sessions/{_SID_2}")
    assert deleted.status_code == 204

    detail = client.get(f"/api/sessions/{_SID_2}")
    assert detail.status_code == 404


def test_invalid_session_id_rejected(client):
    """非 UUID 格式的 session_id 应被拒绝（400）。"""
    for bad_id in ["session-test-1", "not-a-uuid", "12345"]:
        assert client.get(f"/api/sessions/{bad_id}").status_code == 400
        assert client.delete(f"/api/sessions/{bad_id}").status_code == 400
