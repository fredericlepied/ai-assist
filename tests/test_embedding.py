"""Tests for the embedding model wrapper"""

import numpy as np
import pytest

from ai_assist.embedding import EmbeddingModel


@pytest.fixture(scope="module")
def model():
    return EmbeddingModel.get()


def test_encode_returns_correct_shape(model):
    result = model.encode(["hello world"])
    assert result.shape == (1, 384)


def test_encode_multiple(model):
    result = model.encode(["foo", "bar", "baz"])
    assert result.shape == (3, 384)


def test_encode_normalized(model):
    result = model.encode(["deployment failure"])
    norm = np.linalg.norm(result[0])
    assert abs(norm - 1.0) < 0.01


def test_similar_texts_have_high_similarity(model):
    vecs = model.encode(["deployment failure", "deploy error"])
    sim = float(np.dot(vecs[0], vecs[1]))
    assert sim > 0.5


def test_related_texts_score_higher_than_unrelated(model):
    vecs = model.encode(["deployment failure", "release issue", "recipe for chocolate cake"])
    sim_related = float(np.dot(vecs[0], vecs[1]))
    sim_unrelated = float(np.dot(vecs[0], vecs[2]))
    assert sim_related > sim_unrelated


def test_encode_one_returns_bytes(model):
    result = model.encode_one("hello world")
    assert isinstance(result, bytes)
    assert len(result) == 384 * 4  # float32 = 4 bytes each


def test_singleton():
    a = EmbeddingModel.get()
    b = EmbeddingModel.get()
    assert a is b
