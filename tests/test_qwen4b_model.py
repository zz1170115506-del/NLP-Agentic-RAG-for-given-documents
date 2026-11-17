import numpy as np
import pytest

from rag_agent.retrieval.qwen4b_model import (
    NATIVE_DIM, format_text, last_token_pool, prefix_normalize, quantize_rows, score_rows, verify_snapshot,
)


def test_instruction_applies_only_to_query_and_pooling_ignores_padding():
    torch = pytest.importorskip("torch")
    assert format_text("raw passage", query=False, instruction="task") == "raw passage"
    assert format_text("question", query=True, instruction="task") == "Instruct: task\nQuery:question"
    hidden = torch.tensor([[[1], [2], [3]], [[3], [4], [8]], [[8], [6], [3]]])
    mask = torch.tensor([[1, 1, 0], [0, 0, 1], [1, 1, 1]])
    assert last_token_pool(hidden, mask).flatten().tolist() == [2, 8, 3]
    with pytest.raises(ValueError, match="no tokens"):
        last_token_pool(hidden[:1], torch.zeros_like(mask[:1]))


def test_prefix_discards_tail_before_normalizing_and_int8_preserves_ranking():
    full = np.zeros((3, NATIVE_DIM), dtype=np.float32)
    full[:, :3] = [[3, 4, 0], [4, 3, 1], [-3, -4, 0]]
    full[0, -1] = 100
    prefix = prefix_normalize(full, 256)
    np.testing.assert_allclose(prefix[0, :2], [.6, .8], rtol=1e-6)
    codes, scales = quantize_rows(prefix)
    assert codes.nbytes + scales.nbytes == 3 * 260
    restored = codes.astype(np.float32) * scales[:, None]
    assert (np.max(np.abs(restored - prefix), axis=1) <= scales / 2 + 1e-7).all()
    scores = score_rows(prefix[0], codes, scales)
    assert np.argsort(-scores, kind="stable").tolist() == [0, 1, 2]
    np.testing.assert_allclose(scores, (restored / np.linalg.norm(restored, axis=1)[:, None]) @ prefix[0],
                               rtol=1e-6, atol=1e-7)


def test_empty_batch_preserved_but_invalid_shapes_and_zero_vectors_are_rejected():
    empty = prefix_normalize(np.empty((0, NATIVE_DIM), dtype=np.float32), 256)
    assert empty.shape == (0, 256)
    codes, scales = quantize_rows(empty)
    assert score_rows(np.ones(256), codes, scales).shape == (0,)
    with pytest.raises(ValueError, match="2560"):
        prefix_normalize(np.ones((1, 1024)))
    with pytest.raises(ValueError, match="nonzero"):
        prefix_normalize(np.zeros((1, NATIVE_DIM)))
    with pytest.raises(ValueError, match="128|dimensions"):
        score_rows(np.ones(128), codes, scales)


def test_offline_snapshot_cannot_claim_pinned_identity_with_other_bytes(tmp_path):
    (tmp_path / "model-00001-of-00002.safetensors").write_bytes(b"wrong snapshot")
    with pytest.raises(ValueError, match="verification failed"):
        verify_snapshot(tmp_path)
    (tmp_path / "model.safetensors").write_bytes(b"unverified override")
    with pytest.raises(ValueError, match="override"):
        verify_snapshot(tmp_path)
