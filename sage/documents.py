import io
import math
import re
from collections import Counter
from pathlib import Path


def extract_text(name, content):
    if len(content) > 5_000_000:
        raise ValueError("Files must be smaller than 5 MB")
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("Install pypdf to import PDF documents") from exc
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) > 150:
            raise ValueError("PDF limit is 150 pages")
        text = "\n".join(f"[Page {i + 1}]\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages))
        if not text.replace("\n", "").strip() or not any(p.extract_text() for p in reader.pages):
            raise ValueError("This PDF has no extractable text; OCR it before importing")
    elif suffix in {".txt", ".md", ".csv", ".json", ".py"}:
        text = content.decode("utf-8-sig")
    else:
        raise ValueError("Supported files: PDF, TXT, Markdown, CSV, JSON, Python")
    if len(text) > 300_000:
        raise ValueError("Extracted text exceeds 300,000 characters")
    return text


def tokens(text):
    return re.findall(r"[^\W_]{2,}", text.casefold(), re.UNICODE)


def search(documents, query, k=4):
    """Local lexical retrieval, including Arabic; no downloads or external embedding service."""
    chunks = []
    for doc in documents:
        for start in range(0, len(doc["text"]), 1000):
            text = doc["text"][start:start + 1200]
            chunks.append({"source": f"{doc['id']}:{start // 1000 + 1}", "document_id": doc["id"],
                           "name": doc["name"], "text": text})
    query_terms = set(tokens(query))
    counts = [Counter(tokens(c["text"])) for c in chunks]
    frequencies = Counter(term for count in counts for term in count)
    for chunk, count in zip(chunks, counts):
        chunk["score"] = sum((1 + math.log(count[t])) * math.log(1 + len(chunks) / (1 + frequencies[t]))
                             for t in query_terms if count[t]) / math.sqrt(max(1, sum(count.values())))
    return sorted((c for c in chunks if c["score"] > 0), key=lambda c: c["score"], reverse=True)[:k]
