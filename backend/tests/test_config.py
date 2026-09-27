from dejavu.config import Settings


def test_defaults_match_spec() -> None:
    s = Settings(_env_file=None)
    assert s.llm_primary == "openai/gpt-oss-120b"
    assert s.llm_fast == "openai/gpt-oss-20b"
    assert s.hindsight_base_url == "https://api.hindsight.vectorize.io"
    assert s.llm_max_context_tokens == 6000
    assert (s.llm_rpm, s.llm_tpm, s.llm_rpd) == (30, 8000, 1000)
    assert s.demo_mode == "live"


def test_fallbacks_parse_from_csv(monkeypatch) -> None:
    monkeypatch.setenv("LLM_FALLBACKS", "qwen/qwen3.8-27b, openai/gpt-oss-20b ,")
    s = Settings(_env_file=None)
    assert s.llm_fallbacks == ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]


def test_configured_models_dedupes_in_priority_order() -> None:
    s = Settings(_env_file=None, llm_fallbacks=["openai/gpt-oss-20b", "x/y"])
    assert s.configured_models == ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "x/y"]


def test_blank_keys_are_none(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("HINDSIGHT_API_KEY", "")
    s = Settings(_env_file=None)
    assert s.groq_api_key is None
    assert s.hindsight_api_key is None


def test_keys_are_secret_in_repr() -> None:
    s = Settings(_env_file=None, groq_api_key="abc123")
    assert "abc123" not in repr(s)
