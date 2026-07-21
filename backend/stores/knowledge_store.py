import gc
import json
import shutil
import time
from pathlib import Path

from backend.config import KNOWLEDGE_BASE_FILE, KNOWLEDGE_VECTOR_DIR, RUNTIME_DIR
from backend.embeddings import LocalHashEmbeddings
from backend.utils import read_text_file


def load_knowledge_bases() -> dict[str, dict[str, object]]:
    if not KNOWLEDGE_BASE_FILE.exists():
        return {}
    try:
        data = json.loads(KNOWLEDGE_BASE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(kb_id): knowledge_base
        for kb_id, knowledge_base in data.items()
        if isinstance(knowledge_base, dict)
    }


def save_knowledge_bases(knowledge_bases: dict[str, dict[str, object]]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = KNOWLEDGE_BASE_FILE.with_suffix(".json.tmp")
    temp_file.write_text(
        json.dumps(knowledge_bases, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_file.replace(KNOWLEDGE_BASE_FILE)


def collect_knowledge_files(folder_path: Path) -> list[Path]:
    extensions = {".txt", ".md"}
    return sorted(
        path
        for path in folder_path.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    )


def split_knowledge_documents(files: list[Path]) -> list[dict[str, object]]:
    raw_documents = []
    for file_path in files:
        text = read_text_file(file_path).strip()
        if text:
            raw_documents.append({"text": text, "source": str(file_path), "file_name": file_path.name})

    try:
        from langchain_core.documents import Document
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        documents = [
            Document(
                page_content=document["text"],
                metadata={
                    "source": document["source"],
                    "file_name": document["file_name"],
                },
            )
            for document in raw_documents
        ]
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
        chunks = splitter.split_documents(documents)
        return [
            {
                "text": chunk.page_content,
                "metadata": dict(chunk.metadata),
            }
            for chunk in chunks
        ]
    except ImportError:
        fallback_chunks: list[dict[str, object]] = []
        chunk_size = 800
        overlap = 120
        step = chunk_size - overlap
        for document in raw_documents:
            text = str(document["text"])
            for index in range(0, len(text), step):
                chunk_text = text[index : index + chunk_size]
                if chunk_text.strip():
                    fallback_chunks.append(
                        {
                            "text": chunk_text,
                            "metadata": {
                                "source": document["source"],
                                "file_name": document["file_name"],
                            },
                        }
                    )
        return fallback_chunks


def write_json_vector_store(vector_dir: Path, chunks: list[dict[str, object]]) -> None:
    embeddings = LocalHashEmbeddings()
    payload = {
        "embedding_model": "local-hash-embeddings",
        "dimensions": embeddings.dimensions,
        "chunks": [
            {
                "text": str(chunk["text"]),
                "metadata": chunk["metadata"],
                "embedding": embeddings.embed_query(str(chunk["text"])),
            }
            for chunk in chunks
        ],
    }
    vector_dir.mkdir(parents=True, exist_ok=True)
    (vector_dir / "vectors.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def write_chroma_vector_store(vector_dir: Path, kb_id: str, chunks: list[dict[str, object]]) -> bool:
    if not chunks:
        return False

    try:
        from langchain_core.documents import Document
        try:
            from langchain_chroma import Chroma
        except ImportError:
            from langchain_community.vectorstores import Chroma
    except ImportError:
        return False

    documents = [
        Document(page_content=str(chunk["text"]), metadata=dict(chunk["metadata"]))
        for chunk in chunks
    ]
    store = Chroma.from_documents(
        documents=documents,
        embedding=LocalHashEmbeddings(),
        collection_name=f"kb_{kb_id}",
        persist_directory=str(vector_dir),
    )
    del store
    release_chroma_resources()
    return True


def release_chroma_resources() -> None:
    try:
        from chromadb.api.client import SharedSystemClient

        SharedSystemClient.clear_system_cache()
    except Exception:
        pass
    gc.collect()


def build_knowledge_base_index(kb_id: str, folder_path: Path) -> dict[str, object]:
    files = collect_knowledge_files(folder_path)
    chunks = split_knowledge_documents(files)
    vector_dir = KNOWLEDGE_VECTOR_DIR / kb_id
    if vector_dir.exists():
        shutil.rmtree(vector_dir)

    write_json_vector_store(vector_dir, chunks)
    chroma_enabled = write_chroma_vector_store(vector_dir, kb_id, chunks)
    return {
        "file_count": len(files),
        "chunk_count": len(chunks),
        "vector_path": str(vector_dir),
        "vector_backend": "chroma" if chroma_enabled else "local-json-vector-store",
    }


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right))


def query_json_vector_store(
    kb_id: str,
    query: str,
    top_k: int,
    knowledge_bases: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    vector_file = KNOWLEDGE_VECTOR_DIR / kb_id / "vectors.json"
    if not vector_file.exists():
        return []

    try:
        payload = json.loads(vector_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    embeddings = LocalHashEmbeddings(dimensions=int(payload.get("dimensions", 384)))
    query_vector = embeddings.embed_query(query)
    results = []
    for chunk in payload.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        embedding = chunk.get("embedding")
        if not isinstance(embedding, list):
            continue
        score = cosine_similarity(query_vector, [float(value) for value in embedding])
        results.append(
            {
                "knowledge_base_id": kb_id,
                "knowledge_base_name": knowledge_bases.get(kb_id, {}).get("name", ""),
                "score": score,
                "text": chunk.get("text", ""),
                "metadata": chunk.get("metadata", {}),
            }
        )
    return sorted(results, key=lambda item: float(item["score"]), reverse=True)[:top_k]


def remove_knowledge_vector_dir(kb_id: str) -> None:
    vector_dir = (KNOWLEDGE_VECTOR_DIR / kb_id).resolve()
    root_dir = KNOWLEDGE_VECTOR_DIR.resolve()
    if vector_dir == root_dir or root_dir not in vector_dir.parents:
        return
    if not vector_dir.exists():
        return

    release_chroma_resources()
    last_error: OSError | None = None
    for _ in range(5):
        try:
            shutil.rmtree(vector_dir)
            return
        except OSError as exc:
            last_error = exc
            release_chroma_resources()
            time.sleep(0.2)
    if last_error:
        raise last_error
