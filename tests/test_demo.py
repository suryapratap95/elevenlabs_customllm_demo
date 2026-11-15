"""Demo tests with a fake Azure Foundry stream - no network, no API keys."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DEMO_DB"] = str(Path("/tmp") / "voice_demo_test.db")
os.environ["DEMO_LLM_SECRET"] = "test-secret"
os.environ["TEAMS_WEBHOOK_URL"] = ""

from fastapi.testclient import TestClient  # noqa: E402

import app as demo_app  # noqa: E402
import store  # noqa: E402
import voice  # noqa: E402

AUTH = {"Authorization": "Bearer test-secret"}


def text_ev(t, finish=None):
    return NS(choices=[NS(delta=NS(content=t, tool_calls=None), finish_reason=finish)])


def tool_ev(name, args):
    call = NS(index=0, id="call_1", function=NS(name=name, arguments=json.dumps(args)))
    return NS(choices=[NS(delta=NS(content=None, tool_calls=[call]), finish_reason="tool_calls")])


class FakeOpenAI:
    def __init__(self, tool=None):
        self.tool, self.calls = tool, []
        self.chat = NS(completions=NS(create=self._create))

    async def _create(self, **kw):
        self.calls.append(kw)
        last = kw["messages"][-1]

        async def gen():
            if last["role"] == "tool":
                yield text_ev("Result: " + last["content"], "stop")
            elif self.tool:
                yield tool_ev(*self.tool)
            else:
                yield text_ev("Hello, how can I help?", "stop")
        return gen()


@pytest.fixture(autouse=True)
def fresh():
    store.reset()


@pytest.fixture
def fake(monkeypatch):
    def install(tool=None):
        c = FakeOpenAI(tool)
        monkeypatch.setattr(voice, "get_client", lambda: c)
        return c
    return install


def post(messages, path="/v1/chat/completions", tools=None):
    with TestClient(demo_app.app) as client:
        r = client.post(path, headers=AUTH, json={"messages": messages, "stream": True, "tools": tools or []})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    lines = [l for l in r.text.splitlines() if l.startswith("data: ")]
    assert lines[-1] == "data: [DONE]"
    chunks = [json.loads(l[6:]) for l in lines[:-1]]
    return chunks, "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)


def test_auth_required():
    with TestClient(demo_app.app) as client:
        assert client.post("/v1/chat/completions", json={"messages": []}).status_code == 401


@pytest.mark.parametrize("path", ["/v1/chat/completions", "/chat/completions"])
def test_both_paths_stream(fake, path):
    fake()
    chunks, text = post([{"role": "user", "content": "hi"}], path)
    assert text == "Hello, how can I help?"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


def test_lookup_streams_filler_then_answer(fake):
    fake(("get_case_status", {"case_ref": "p 1042"}))
    _, text = post([{"role": "user", "content": "status of P 1042?"}])
    assert text.startswith("One moment... ")
    assert '"status": "pending"' in text


def test_update_blocked_without_readback(fake):
    fake(("update_case_status", {"case_ref": "P-1042", "status": "approved"}))
    _, text = post([{"role": "user", "content": "approve P-1042"}])
    assert "confirmation_required" in text
    assert store.get_case_status("P-1042")["status"] == "pending"


def test_update_after_readback_and_yes_writes_audit(fake):
    fake(("update_case_status", {"case_ref": "P-1042", "status": "approved"}))
    post([{"role": "user", "content": "approve P-1042"},
          {"role": "assistant", "content": "To confirm: approve case P one zero four two. Shall I go ahead?"},
          {"role": "user", "content": "Yes please."}])
    assert store.get_case_status("P-1042")["status"] == "approved"
    assert store.recent_audit()[0]["new_status"] == "approved"


def test_elevenlabs_system_tool_is_passed_back(fake):
    fake(("end_call", {}))
    el_tools = [{"type": "function", "function": {"name": "end_call", "parameters": {"type": "object", "properties": {}}}}]
    chunks, _ = post([{"role": "user", "content": "bye"}], tools=el_tools)
    tc = [c for c in chunks if c["choices"][0]["delta"].get("tool_calls")]
    assert tc and tc[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "end_call"
    assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"


def test_server_prompt_first_and_tools_merged(fake):
    c = fake()
    post([{"role": "system", "content": "EL prompt"}, {"role": "user", "content": "hi"}],
         tools=[{"type": "function", "function": {"name": "end_call", "parameters": {"type": "object"}}}])
    sent = c.calls[0]
    assert sent["messages"][0]["content"].startswith("You are the VerifyHub")
    assert {t["function"]["name"] for t in sent["tools"]} == {"get_case_status", "list_pending_cases",
                                                              "update_case_status", "end_call"}


def test_state_endpoint_and_page():
    with TestClient(demo_app.app) as client:
        s = client.get("/api/state").json()
        assert len(s["cases"]) == 7 and "events" in s
        assert client.get("/").status_code == 200
