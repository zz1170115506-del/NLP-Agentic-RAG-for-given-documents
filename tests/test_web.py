"""Exercise the actual Streamlit form against the shared synthetic runtime."""
from pathlib import Path
import pytest
import yaml
from streamlit.testing.v1 import AppTest
from rag_agent.config import Settings
from rag_agent.data import DocumentStore, iter_jsonl
from rag_agent.retrieval import build_indexes


@pytest.mark.parametrize("agent_engine", ["baseline", "agent12"])
def test_web_demo_and_missing_live_setup(tmp_path, monkeypatch, agent_engine):
    root = Path(__file__).resolve().parents[1]
    cfg = Settings(mode="demo", method="sparse", agent_engine=agent_engine, store_path=str(tmp_path / "corpus.sqlite"),
                   index_dir=str(tmp_path / "index"), skills_dir=str(root / "skills"))
    store = DocumentStore(cfg.store_path)
    store.import_documents(iter_jsonl(root / "tests/fixtures/corpus.jsonl"), cfg.chunk_size, cfg.chunk_overlap)
    build_indexes(cfg, ["sparse"])
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/demo.yaml").write_text(yaml.safe_dump(cfg.model_dump()))
    (tmp_path / "configs/live.yaml").write_text(yaml.safe_dump(cfg.model_copy(update={"mode": "live"}).model_dump()))
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(root / "src/rag_agent/web_app.py"), default_timeout=20).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    result = app.session_state["result"]
    if agent_engine == "agent12":
        assert "Lumen Observatory" in result["prediction"]["answer"]
        assert result["prediction"]["tool_calls"] == 2
        assert result["state"]["selected_evidence_ids"] == ["E1"]
        assert any("答案引用" in expander.label for expander in app.expander)
    else:
        assert result["prediction"]["answer"] == "Northport"
        assert result["prediction"]["tool_calls"] >= 3
    assert result["mode"] == "demo" and not result["eligible"]
    assert app.session_state["busy"] is False
    assert len(app.tabs) == 3
    app.selectbox[0].select("configs/live.yaml").run()
    assert not app.exception
    assert "result" not in app.session_state
    app.button[0].click().run()
    assert app.error and not app.exception


def test_config_roundtrip_and_wrong_backbone():
    cfg = Settings()
    assert cfg.config_id == Settings.model_validate(cfg.model_dump()).config_id
    with pytest.raises(ValueError, match="not a pinned"):
        Settings(llm_base_url="https://provider.example/v1", llm_model="gpt-test", model_verified=True,
                 model_verification_note="test").check_model_identity()


def test_example_env_preserves_checked_provider(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    for name in ("LLM_MODEL_VERIFIED", "LLM_BASE_URL", "LLM_MODEL", "LLM_MODEL_VERIFICATION_NOTE"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text((root / ".env.example").read_text())
    cfg = Settings.load(root / "configs/openrouter.yaml")
    assert cfg.model_verified
    cfg.check_model_identity()
