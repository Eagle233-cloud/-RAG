from dataclasses import dataclass
from pathlib import Path
import json
import shutil

import chromadb

from .documents import ParsedDocument, parse_file
from .errors import DuplicateDocumentError
from .ollama import OllamaClient


@dataclass(frozen=True)
class SearchResult:
    text: str
    filename: str
    distance: float


class DocumentStore:
    collection_name = "local_documents"

    def __init__(self, data_dir: Path, ollama: OllamaClient, chunk_size: int, chunk_overlap: int, top_k: int):
        self.data_dir = data_dir
        self.uploads_dir = data_dir / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(data_dir / "chroma"))
        self.collection = self.client.get_or_create_collection(self.collection_name)
        self.ollama = ollama
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k

    def documents(self) -> list[dict[str, str | int]]:
        data = self.collection.get(include=["metadatas"])
        grouped: dict[str, dict[str, str | int]] = {}
        for metadata in data.get("metadatas", []):
            if not metadata:
                continue
            document_id = str(metadata["document_id"])
            grouped[document_id] = {
                "document_id": document_id,
                "filename": str(metadata["filename"]),
                "chunks": int(metadata.get("chunk_count", 0)),
            }
        return sorted(grouped.values(), key=lambda item: str(item["filename"]).lower())

    def index_file(self, source: Path) -> dict[str, str | int]:
        parsed = parse_file(source, self.chunk_size, self.chunk_overlap)
        if any(item["document_id"] == parsed.document_id for item in self.documents()):
            raise DuplicateDocumentError(f"文档“{parsed.filename}”已经导入过了。")
        embeddings = self.ollama.embed(parsed.chunks)
        destination = self.uploads_dir / f"{parsed.document_id}{source.suffix.lower()}"
        shutil.copy2(source, destination)
        ids = [f"{parsed.document_id}:{index}" for index in range(len(parsed.chunks))]
        self.collection.add(
            ids=ids,
            documents=parsed.chunks,
            embeddings=embeddings,
            metadatas=[
                {
                    "document_id": parsed.document_id,
                    "filename": parsed.filename,
                    "chunk_count": len(parsed.chunks),
                }
                for _ in parsed.chunks
            ],
        )
        return {"document_id": parsed.document_id, "filename": parsed.filename, "chunks": len(parsed.chunks)}

    def search(self, question: str) -> list[SearchResult]:
        embedding = self.ollama.embed([question])[0]
        result = self.collection.query(query_embeddings=[embedding], n_results=self.top_k)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            SearchResult(str(text), str(metadata["filename"]), float(distance))
            for text, metadata, distance in zip(documents, metadatas, distances)
        ]

    def rebuild(self) -> int:
        old_documents = list(self.documents())
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(self.collection_name)
        count = 0
        for document in old_documents:
            matches = list(self.uploads_dir.glob(f"{document['document_id']}.*"))
            if matches:
                self.index_file(matches[0])
                count += 1
        return count

    def status(self) -> dict[str, int]:
        return {"documents": len(self.documents()), "chunks": self.collection.count()}

