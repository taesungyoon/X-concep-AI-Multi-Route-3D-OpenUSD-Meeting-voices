from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json


def _string_values(value: Any) -> Iterable[str]:
    """Yield useful text values from NeMo Retriever result objects.

    NeMo Retriever result containers can change between releases.  The adapter
    intentionally accepts dict/list/DataFrame-like outputs and converts them
    into the stable X concep chunk contract used by Qdrant.
    """
    if value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            yield text
        return
    if isinstance(value, dict):
        preferred = ("text", "content", "page_content", "caption", "transcript")
        emitted = False
        for key in preferred:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                emitted = True
                yield item.strip()
        if not emitted:
            for item in value.values():
                yield from _string_values(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _string_values(item)
        return
    if hasattr(value, "to_dict"):
        try:
            data = value.to_dict(orient="records")
        except TypeError:
            data = value.to_dict()
        yield from _string_values(data)
        return
    if hasattr(value, "model_dump"):
        yield from _string_values(value.model_dump())
        return


def extract_with_nemo_retriever(path: Path) -> list[str]:
    """Extract and embed media with NVIDIA NeMo Retriever Library.

    The output vectors are not stored in NeMo Retriever's default LanceDB path.
    Instead, extracted text chunks are normalized and embedded again by the
    X concep knowledge service before being stored in Qdrant.  This is a custom
    integration boundary because Qdrant is not the first-party VDB backend of
    NeMo Retriever Library.
    """
    try:
        from nemo_retriever import create_ingestor  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "NeMo Retriever가 설치되지 않음. requirements-nemo-retriever.txt를 설치해야 함"
        ) from exc

    ingestor = create_ingestor(run_mode="batch").files([str(path)]).extract().embed()
    results = ingestor.ingest()
    chunks: list[str] = []
    seen: set[str] = set()
    for text in _string_values(results):
        normalized = " ".join(text.split())
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        chunks.append(normalized)
    if not chunks:
        raise RuntimeError("NeMo Retriever가 검색 가능한 텍스트 Chunk를 반환하지 않음")
    return chunks


def extract_fallback(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".json", ".csv", ".log"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PDF fallback 추출에는 pypdf가 필요함") from exc
        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    else:
        raise RuntimeError(f"Fallback 추출에서 지원하지 않는 파일 형식임: {suffix}")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        raise RuntimeError("파일에서 텍스트를 추출하지 못함")
    size = 1600
    overlap = 200
    return [text[i : i + size] for i in range(0, len(text), max(1, size - overlap))]
