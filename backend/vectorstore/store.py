import chromadb
from sentence_transformers import SentenceTransformer

from backend.schemas.schemas import Chunk


# ============================================================
# CONFIGURATION
# ============================================================

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

CHROMA_COLLECTION_NAME = "research_papers"

CHROMA_PERSIST_DIRECTORY = "backend/vectorstore/chroma_db"


# ============================================================
# EMBEDDING MODEL
# ============================================================

_embedding_model = None


def get_embedding_model():
    """
    Load the sentence-transformer model.

    The model is loaded only once and then reused.
    """

    global _embedding_model

    if _embedding_model is None:
        print("[Vector Store] Loading embedding model...")

        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )

        print("[Vector Store] Embedding model loaded.")

    return _embedding_model


# ============================================================
# CHROMADB CLIENT
# ============================================================

def get_chroma_client():
    """
    Create or connect to the local ChromaDB database.
    """

    client = chromadb.PersistentClient(
        path=CHROMA_PERSIST_DIRECTORY
    )

    return client


# ============================================================
# COLLECTION
# ============================================================

def get_collection():
    """
    Get the research paper collection.

    Creates the collection if it does not exist.
    """

    client = get_chroma_client()

    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME
    )

    return collection


# ============================================================
# CREATE EMBEDDINGS
# ============================================================

def create_embeddings(
    texts: list[str],
) -> list[list[float]]:
    """
    Convert text into vector embeddings.
    """

    if not texts:
        return []

    model = get_embedding_model()

    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
    )

    return embeddings.tolist()


# ============================================================
# REMOVE DUPLICATE CHUNKS
# ============================================================

def _remove_duplicate_chunks(
    chunks: list[Chunk],
) -> list[Chunk]:
    """
    Remove duplicate chunk IDs from a batch.

    ChromaDB requires every ID inside a single upsert
    operation to be unique.
    """

    unique_chunks = []
    seen_ids = set()

    for chunk in chunks:

        if chunk.chunk_id in seen_ids:
            continue

        seen_ids.add(chunk.chunk_id)
        unique_chunks.append(chunk)

    return unique_chunks


# ============================================================
# STORE CHUNKS
# ============================================================

def add_chunks(
    chunks: list[Chunk],
) -> int:
    """
    Create embeddings for chunks and store them in ChromaDB.

    Duplicate chunk IDs within the same batch are ignored.

    If the same chunk already exists in ChromaDB,
    upsert updates it instead of creating another copy.

    Returns:
        Number of unique chunks processed.
    """

    if not chunks:
        return 0

    # --------------------------------------------------------
    # Remove duplicate IDs from the current batch
    # --------------------------------------------------------

    unique_chunks = _remove_duplicate_chunks(chunks)

    if not unique_chunks:
        return 0

    collection = get_collection()

    # --------------------------------------------------------
    # Prepare documents
    # --------------------------------------------------------

    texts = [
        chunk.text
        for chunk in unique_chunks
    ]

    # --------------------------------------------------------
    # Create embeddings
    # --------------------------------------------------------

    embeddings = create_embeddings(texts)

    # --------------------------------------------------------
    # Prepare IDs
    # --------------------------------------------------------

    ids = [
        chunk.chunk_id
        for chunk in unique_chunks
    ]

    # --------------------------------------------------------
    # Prepare metadata
    # --------------------------------------------------------

    metadatas = [
        {
            "paper_id": chunk.paper_id,
            "page_number": (
                chunk.page_number
                if chunk.page_number is not None
                else -1
            ),
            "section_heading": (
                chunk.section_heading
                if chunk.section_heading
                else ""
            ),
        }
        for chunk in unique_chunks
    ]

    # --------------------------------------------------------
    # Store in ChromaDB
    # --------------------------------------------------------

    collection.upsert(
        ids=ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    print(
        f"[Vector Store] Stored {len(unique_chunks)} chunks."
    )

    return len(unique_chunks)


# ============================================================
# SEARCH SIMILAR CHUNKS
# ============================================================

def search_similar_chunks(
    query: str,
    top_k: int = 5,
):
    """
    Search ChromaDB for chunks similar to a query.
    """

    if not query or not query.strip():
        return []

    collection = get_collection()

    # --------------------------------------------------------
    # Create query embedding
    # --------------------------------------------------------

    query_embedding = create_embeddings(
        [query.strip()]
    )[0]

    # --------------------------------------------------------
    # Search ChromaDB
    # --------------------------------------------------------

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    return results