"""On an 8 GB host only one ~1 GB GGUF should be resident (H4 / decision Q8)."""
from services import recommendation_explainer as explainer
from services import stylist_selector
from services.local_llm import LocalLLM, local_llm
from settings import settings


def test_chat_defaults_to_the_fine_tuned_stylist_when_installed(tmp_path, monkeypatch):
    stylist_file = tmp_path / "aura-stylist.gguf"
    stylist_file.write_bytes(b"stub")
    previous = settings.stylist_llm_model_path
    object.__setattr__(settings, "stylist_llm_model_path", stylist_file)
    monkeypatch.setattr(stylist_selector, "_stylist_llm", None)
    try:
        assert settings.chat_use_stylist is True  # the default
        chat_model = stylist_selector.chat_llm()
        assert chat_model is not local_llm and isinstance(chat_model, LocalLLM)
        assert stylist_selector.chat_model_source() == "fine_tuned_stylist"
    finally:
        object.__setattr__(settings, "stylist_llm_model_path", previous)


def test_recommendation_comparison_uses_the_chat_model_not_the_base_model(monkeypatch):
    calls = []

    class FakeChatModel:
        def get_model_info(self):
            return {"present": True}

        def generate_response(self, prompt, **kwargs):
            calls.append(prompt)
            return "reply"

    monkeypatch.setattr(stylist_selector, "chat_llm", lambda: FakeChatModel())
    monkeypatch.setattr(local_llm, "generate_response", lambda *a, **k: (_ for _ in ()).throw(AssertionError("base model used")))
    assert explainer.get_model_info() == {"present": True}
    assert explainer.generate_response("payload") == "reply"
    assert calls == ["payload"]
