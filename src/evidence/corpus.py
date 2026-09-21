# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The regulation corpus: a versioned, hashed index the judge retrieves from.

Building is a standalone step, run when a jurisdiction's texts change — not
during an evaluation run::

    evidence corpus build EU        # regulations/EU/corpus.yaml -> regulations/EU/index/

Inputs are the source files listed in ``corpus.yaml``: one markdown file per
instrument, headed ``## <paragraph>`` so that a passage is a citable unit.
Outputs, under ``index/``:

- ``passages.jsonl``      one passage per paragraph: id, citation, text
- ``vectors.jsonl``       the embedding of each passage (committed, so a clone
                          needs no rebuild and no embedding call to retrieve)
- ``passages.db``         Milvus Lite vector index over the same vectors (not
                          committed; created when the build can open one)
- ``corpus_manifest.json`` embedding model, chunking rule, sha256 of every
  source and of passages.jsonl — the corpus version a run records

Retrieval uses Milvus Lite when it opens and otherwise a cosine search over
``vectors.jsonl`` in-process. Milvus Lite cannot open a database on a network
filesystem (the cluster's ``/home`` and ``/data``) or on a path with a space;
the fallback gives the same ranking, and the run manifest records which was
used.

At run time the judge embeds the briefing as a query, takes the top passages,
and must cite one of them. Regulations change; a document is swapped and the
index rebuilt. Nothing here fetches from the web.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from evidence.adapters.nvidia_build import MODELS
from evidence.adapters.nvidia_build import embed as _embed_api

CHUNKING = "markdown-h2-paragraph-v1"
COLLECTION = "passages"

Embedder = Callable[[list[str], str], list[list[float]]]


def embed(texts: list[str], input_type: str) -> list[list[float]]:
    """The default embedder: the retriever model on the configured endpoint."""
    return _embed_api(texts, input_type=input_type)


@dataclass(frozen=True)
class Passage:
    passage_id: str
    source_id: str
    citation: str
    title: str
    text: str


def default_regulations_root() -> Path:
    from evidence.regulations import default_rules_root

    return default_rules_root()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_corpus_spec(jurisdiction: str, root: Path | None = None) -> tuple[Path, dict[str, Any]]:
    base = (root or default_regulations_root()) / jurisdiction.upper()
    spec_path = base / "corpus.yaml"
    if not spec_path.is_file():
        raise FileNotFoundError(
            f"no corpus.yaml for jurisdiction {jurisdiction.upper()}: {spec_path}"
        )
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    if not spec.get("sources"):
        raise ValueError(f"{spec_path} lists no sources")
    return base, spec


def split_passages(source: dict[str, Any], text: str) -> list[Passage]:
    """One passage per ``## <n>`` section; the preamble before the first section is dropped.

    A source with no ``##`` sections becomes a single passage.
    """
    parts = re.split(r"(?m)^## +", text)
    citation = str(source["citation"])
    title = str(source.get("title", ""))
    sid = str(source["id"])
    if len(parts) == 1:
        body = re.sub(r"(?m)^# .*\n", "", text).strip()
        return [Passage(sid, sid, citation, title, body)] if body else []
    passages: list[Passage] = []
    for part in parts[1:]:
        head, _, body = part.partition("\n")
        para = head.strip().rstrip(".")
        body = body.strip()
        if not body:
            continue
        passages.append(Passage(f"{sid}#{para}", sid, f"{citation}({para})", title, body))
    return passages


def build_corpus(
    jurisdiction: str,
    root: Path | None = None,
    *,
    embedder: Embedder | None = None,
    embed_model: str | None = None,
) -> dict[str, Any]:
    """Build ``index/`` for a jurisdiction. Returns the corpus manifest."""
    base, spec = load_corpus_spec(jurisdiction, root)
    index = base / "index"
    index.mkdir(exist_ok=True)
    embedder = embedder or embed
    embed_model = embed_model or MODELS["embed"]

    passages: list[Passage] = []
    sources: list[dict[str, Any]] = []
    for src in spec["sources"]:
        path = base / str(src["file"])
        data = path.read_bytes()
        found = split_passages(src, data.decode("utf-8"))
        passages.extend(found)
        sources.append(
            {
                "id": src["id"],
                "file": str(src["file"]),
                "citation": src["citation"],
                "title": src.get("title"),
                "url": src.get("url"),
                "sha256": _sha256(data),
                "passages": len(found),
            }
        )
    if not passages:
        raise ValueError("corpus has no passages")

    lines = [json.dumps(p.__dict__, ensure_ascii=False) for p in passages]
    passages_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    (index / "passages.jsonl").write_bytes(passages_bytes)

    vectors = embedder([p.text for p in passages], "passage")
    (index / "vectors.jsonl").write_text(
        "".join(
            json.dumps({"passage_id": p.passage_id, "vector": [round(x, 6) for x in v]}) + "\n"
            for p, v in zip(passages, vectors, strict=True)
        ),
        encoding="utf-8",
    )
    backend = _build_milvus(index / "passages.db", passages, vectors)

    manifest = {
        "jurisdiction": jurisdiction.upper(),
        "title": spec.get("title"),
        "verified": str(spec.get("verified", "")),
        "chunking": CHUNKING,
        "index_backend": backend,
        "embed_model": embed_model,
        "dimension": len(vectors[0]),
        "passages": len(passages),
        "passages_sha256": _sha256(passages_bytes),
        "sources": sources,
    }
    manifest["corpus_sha256"] = _sha256(
        json.dumps(
            {k: manifest[k] for k in ("chunking", "embed_model", "passages_sha256", "sources")},
            sort_keys=True,
        ).encode("utf-8")
    )
    (index / "corpus_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _build_milvus(db: Path, passages: list[Passage], vectors: list[list[float]]) -> str:
    """Create the Milvus Lite index if the platform and filesystem allow it."""
    try:
        from pymilvus import MilvusClient

        client = MilvusClient(str(db))
        if client.has_collection(COLLECTION):
            client.drop_collection(COLLECTION)
        client.create_collection(COLLECTION, dimension=len(vectors[0]), metric_type="COSINE")
        client.insert(
            COLLECTION,
            [
                {"id": i, "vector": v, "passage_id": p.passage_id}
                for i, (p, v) in enumerate(zip(passages, vectors, strict=True))
            ],
        )
        client.close()
        return "milvus-lite"
    except Exception:  # noqa: BLE001 — any failure to open means: use the in-process index
        import shutil

        shutil.rmtree(db, ignore_errors=True)  # a stale or half-written index must not be reopened
        return "cosine"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


class Corpus:
    """A built index, opened for retrieval."""

    def __init__(
        self, jurisdiction: str, root: Path | None = None, embedder: Embedder | None = None
    ):
        base = (root or default_regulations_root()) / jurisdiction.upper() / "index"
        if not (base / "corpus_manifest.json").is_file() or not (base / "vectors.jsonl").is_file():
            raise FileNotFoundError(
                f"corpus index for {jurisdiction.upper()} not built; run `evidence corpus build "
                f"{jurisdiction.upper()}`"
            )
        self.jurisdiction = jurisdiction.upper()
        self.manifest = json.loads((base / "corpus_manifest.json").read_text(encoding="utf-8"))
        self.passages: dict[str, Passage] = {}
        for line in (base / "passages.jsonl").read_text(encoding="utf-8").splitlines():
            if line:
                p = Passage(**json.loads(line))
                self.passages[p.passage_id] = p
        self._db = base / "passages.db"
        self._embedder = embedder or embed
        self._client = None
        self.backend = (
            "milvus-lite"
            if self._db.exists() and self.manifest.get("index_backend", "milvus-lite") != "cosine"
            else "cosine"
        )
        self._vectors: dict[str, list[float]] = {}
        for line in (base / "vectors.jsonl").read_text(encoding="utf-8").splitlines():
            if line:
                rec = json.loads(line)
                self._vectors[rec["passage_id"]] = rec["vector"]

    @property
    def sha256(self) -> str:
        return str(self.manifest["corpus_sha256"])

    def _search(self, vector: list[float], k: int) -> list[tuple[str, float]]:
        if self.backend == "milvus-lite":
            try:
                from pymilvus import MilvusClient

                if self._client is None:
                    self._client = MilvusClient(str(self._db))
                    self._client.load_collection(COLLECTION)
                hits = self._client.search(
                    COLLECTION, data=[vector], limit=k, output_fields=["passage_id"]
                )
                return [(h["entity"]["passage_id"], float(h["distance"])) for h in hits[0]]
            except Exception:  # noqa: BLE001 — same ranking from the in-process index
                self.backend = "cosine"
                self._client = None
        scored = sorted(
            ((_cosine(v, vector), pid) for pid, v in self._vectors.items()), reverse=True
        )
        return [(pid, score) for score, pid in scored[:k]]

    def retrieve(self, query: str, k: int = 2) -> list[tuple[Passage, float]]:
        vector = self._embedder([query], "query")[0]
        return [(self.passages[pid], score) for pid, score in self._search(vector, k)]

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def list_corpora(root: Path | None = None) -> list[dict[str, Any]]:
    out = []
    for spec_path in sorted((root or default_regulations_root()).glob("*/corpus.yaml")):
        base = spec_path.parent
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
        mpath = base / "index" / "corpus_manifest.json"
        manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.is_file() else None
        out.append(
            {
                "jurisdiction": base.name,
                "title": spec.get("title"),
                "verified": spec.get("verified"),
                "sources": len(spec.get("sources", [])),
                "built": manifest is not None,
                "passages": manifest["passages"] if manifest else None,
                "corpus_sha256": manifest["corpus_sha256"] if manifest else None,
                "embed_model": manifest["embed_model"] if manifest else None,
            }
        )
    return out
