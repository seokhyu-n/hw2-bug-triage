"""Shared fixtures: a fake Anthropic client that returns canned responses."""
from types import SimpleNamespace

import pytest

from app import llm


def make_response(text: str = "{}", stop_reason: str = "end_turn", content=None,
                  input_tokens: int = 100, output_tokens: int = 50,
                  cache_read: int | None = 0, cache_write: int | None = 0):
    if content is None:
        content = [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
    )


class FakeClient:
    """Returns queued responses in order and records the kwargs of each call."""

    def __init__(self):
        self.responses: list = []
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def queue(self, *responses):
        self.responses.extend(responses)
        return self

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_llm(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(llm, "get_client", lambda: client)
    return client
