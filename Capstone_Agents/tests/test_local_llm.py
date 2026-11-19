import sys
import types
from dataclasses import asdict

import pytest

from services.local_llm import LocalLLM, LocalModelError


def _replace_settings(monkeypatch, **updates):
    from services import local_llm as local_llm_module
    from settings import settings
    values = asdict(settings)
    values.update(updates)
    monkeypatch.setattr(local_llm_module, "settings", types.SimpleNamespace(**values))


def test_missing_local_weights_has_actionable_error(tmp_path, monkeypatch):
    _replace_settings(monkeypatch, llm_model_path=tmp_path / "missing.gguf")
    with pytest.raises(LocalModelError, match="weights are missing"):
        LocalLLM().generate_response("hello")


def test_local_model_loads_once_and_generates(tmp_path, monkeypatch):
    path = tmp_path / "tiny.gguf"
    path.write_bytes(b"mock")
    calls = []

    class MockLlama:
        def __init__(self, **kwargs):
            calls.append(("load", kwargs["model_path"]))

        def create_chat_completion(self, **kwargs):
            calls.append(("generate", kwargs["messages"][-1]["content"]))
            return {"choices": [{"message": {"content": "Local answer"}}]}

        def apply_chat_template(self, messages, **kwargs):
            return [1, 2]

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=MockLlama))
    _replace_settings(monkeypatch, llm_model_path=path)
    model = LocalLLM()
    assert model.generate_response("hello") == "Local answer"
    assert model.generate_response("again") == "Local answer"
    assert len([c for c in calls if c[0] == "load"]) == 1


def test_rejects_oversized_input(tmp_path, monkeypatch):
    _replace_settings(monkeypatch, llm_max_input_tokens=2)
    with pytest.raises(ValueError, match="maximum input"):
        LocalLLM().generate_response("x" * 11)


def test_rejects_actual_token_overflow(tmp_path, monkeypatch):
    path = tmp_path / "tiny.gguf"
    path.write_bytes(b"mock")

    class MockLlama:
        def __init__(self, **kwargs):
            pass

        def apply_chat_template(self, messages, **kwargs):
            return list(range(12))

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=MockLlama))
    _replace_settings(monkeypatch, llm_model_path=path, llm_max_input_tokens=10,
                      llm_context_length=32, llm_max_output_tokens=4)
    with pytest.raises(ValueError, match="maximum is 10"):
        LocalLLM().generate_response("short", max_tokens=4)


def test_legacy_agents_share_local_interface(monkeypatch):
    from services.local_llm import local_llm
    from tools.llm_client import call_llm
    monkeypatch.setattr(local_llm, "generate_response", lambda prompt, **kwargs: "local:" + prompt)
    assert call_llm("occasion prompt") == "local:occasion prompt"
