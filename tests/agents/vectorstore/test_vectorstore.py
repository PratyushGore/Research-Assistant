from backend.schemas.schemas import Chunk
from backend.vectorstore.store import (
    create_embeddings,
    add_chunks,
    search_similar_chunks,
)


def test_create_embeddings():
    texts = [
        "Machine learning is used in healthcare.",
        "Artificial intelligence can analyze medical data.",
    ]

    embeddings = create_embeddings(texts)

    assert len(embeddings) == 2
    assert len(embeddings[0]) > 0
    assert len(embeddings[1]) > 0


def test_add_chunks():

    chunks = [
        Chunk(
            chunk_id="test-vector-1",
            paper_id="test-paper",
            text=(
                "Machine learning is an important "
                "technology used in healthcare research."
            ),
            page_number=1,
        ),
        Chunk(
            chunk_id="test-vector-2",
            paper_id="test-paper",
            text=(
                "Artificial intelligence can help "
                "analyze medical images."
            ),
            page_number=2,
        ),
    ]

    count = add_chunks(chunks)

    assert count == 2


def test_search_similar_chunks():

    results = search_similar_chunks(
        "machine learning healthcare",
        top_k=2,
    )

    assert results is not None
    assert "documents" in results
    assert len(results["documents"]) > 0