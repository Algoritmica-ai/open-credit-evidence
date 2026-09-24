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

The vectors only mean something to the embedder that made them. The manifest
names that embedder (the model the endpoint serves, and its fingerprint when it
is self-hosted), and before a run makes its first judge call the corpus
re-embeds one stored passage and compares: a different embedder, or the same one
called differently, gives a different vector and the run stops
(:meth:`Corpus.check_embedder`).

Our source files are transcriptions. ``evidence corpus verify-sources`` checks
each passage, word for word after normalising whitespace, quotes and dashes,
against a saved copy of the official text, and writes the result to
``source_check.json`` next to ``corpus.yaml``.

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
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evidence.adapters.nvidia_build import embed as _embed_api
from evidence.adapters.nvidia_build import endpoint_for

CHUNKING = "markdown-h2-paragraph-v2"
COLLECTION = "passages"
# Re-embedding a stored passage with the embedder that built the index gives the
# same vector up to rounding (6 decimals) and GPU arithmetic. Another embedder,
# or the same one given a different input type, lands well below this.
PROBE_MIN_COSINE = 0.999
# A heading of the act's structure. Inside a passage it means the source file
# carried the start of the next part of the act into the paragraph before it.
_STRUCTURE = re.compile(
    r"(?m)^(?:(?:SECTION|CHAPTER|TITLE|ANNEX)\s+[0-9IVXLC]+|Article\s+\d+\w*)\s*$"
)

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
    """One passage per ``## <n>`` section; everything before the first section is dropped.

    The file's title and our note on where the text came from sit before the
    first section and are never part of a passage. Every passage is headed, so
    a source with no ``##`` section is an error, as is a passage that runs into
    a heading of the act (``SECTION 3``, ``Article 16``). A source cites its
    paragraphs as ``{citation}({para})`` unless it sets ``paragraph_citation``.
    """
    parts = re.split(r"(?m)^## +", text)
    citation = str(source["citation"])
    title = str(source.get("title", ""))
    sid = str(source["id"])
    fmt = str(source.get("paragraph_citation") or "{citation}({para})")
    if len(parts) == 1:
        raise ValueError(f"{sid}: no '## <paragraph>' sections; head every passage")
    passages: list[Passage] = []
    for part in parts[1:]:
        head, _, body = part.partition("\n")
        para = head.strip().rstrip(".")
        body = body.strip()
        if not body:
            continue
        pid = f"{sid}#{para}"
        m = _STRUCTURE.search(body)
        if m:
            raise ValueError(f"{pid}: contains the heading '{m.group(0).strip()}', which starts "
                             "the next part of the act; end the passage before it")
        passages.append(Passage(pid, sid, fmt.format(citation=citation, para=para), title, body))
    return passages


def normalise(text: str) -> str:
    """Text as compared with the official publication: typography and spacing ignored."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u2018\u2019\u201b\u2032]", "'", text)
    text = re.sub(r"[\u201c\u201d]", '"', text)
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def text_sha256(text: str) -> str:
    """SHA-256 of a passage's normalised text: what a source check vouches for."""
    return _sha256(normalise(text).encode("utf-8"))


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
    embedder_facts: dict[str, Any] = {"model": embed_model}
    if embedder is None:  # the configured endpoint: name what it actually serves
        from evidence.fingerprint import model_fingerprint

        ep = endpoint_for("embed")
        fp = model_fingerprint("embed")
        embed_model = embed_model or ep.model_id
        embedder_facts = {"model": embed_model, "endpoint": ep.base_url,
                          "fingerprint": fp.get("fingerprint"), "level": fp.get("level")}
    embedder = embedder or embed
    embed_model = embed_model or "unnamed"
    embedder_facts["model"] = embed_model

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
    vectors_bytes = "".join(
        json.dumps({"passage_id": p.passage_id, "vector": [round(x, 6) for x in v]}) + "\n"
        for p, v in zip(passages, vectors, strict=True)
    ).encode("utf-8")
    (index / "vectors.jsonl").write_bytes(vectors_bytes)
    backend = _build_milvus(index / "passages.db", passages, vectors)

    manifest = {
        "jurisdiction": jurisdiction.upper(),
        "title": spec.get("title"),
        "verified": str(spec.get("verified", "")),
        "chunking": CHUNKING,
        "index_backend": backend,
        "embed_model": embed_model,
        # Who made the vectors, recorded but outside the version hash: the vectors
        # themselves are hashed, and the fingerprint would change with a restart
        # that changes nothing about them.
        "embedder": embedder_facts,
        "dimension": len(vectors[0]),
        "passages": len(passages),
        "passages_sha256": _sha256(passages_bytes),
        # The vectors decide what the judge retrieves. A new embedder under the same
        # model name, or a rebuild that embeds differently, is a new corpus version.
        "vectors_sha256": _sha256(vectors_bytes),
        "sources": sources,
    }
    manifest["corpus_sha256"] = _sha256(
        json.dumps(
            {k: manifest[k] for k in ("chunking", "embed_model", "passages_sha256",
                                      "vectors_sha256", "sources")},
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
        self._root = root
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

    def check_embedder(self) -> dict[str, Any]:
        """Re-embed the first stored passage and compare it with its stored vector.

        The index is only valid for the embedder that built it. Call before the
        first retrieval of a run; ``ok`` False means rebuild the index against
        this embedder, or point the run at the one that built it.
        """
        pid = next(iter(self.passages))
        stored = self._vectors[pid]
        got = self._embedder([self.passages[pid].text], "passage")[0]
        cos = _cosine(got, stored) if len(got) == len(stored) else 0.0
        return {"probe": pid, "cosine": round(cos, 6), "min_cosine": PROBE_MIN_COSINE,
                "ok": cos >= PROBE_MIN_COSINE, "dimension": len(got),
                "index_dimension": len(stored), "index_embed_model": self.manifest["embed_model"],
                "query_embed_model": _query_model()}

    def source_check(self) -> dict[str, Any] | None:
        """How many of these passages a recorded source check found in the official text."""
        return source_check_status(self.jurisdiction, self.passages.values(), self._root)

    def retrieve(self, query: str, k: int = 2) -> list[tuple[Passage, float]]:
        vector = self._embedder([query], "query")[0]
        return [(self.passages[pid], score) for pid, score in self._search(vector, k)]

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def _query_model() -> str | None:
    try:
        return endpoint_for("embed").model_id
    except Exception:  # noqa: BLE001 — an unconfigured endpoint is reported, not raised here
        return None


SOURCE_CHECK = "source_check.json"


def verify_sources(
    jurisdiction: str, official_text: str, *, official: dict[str, Any], root: Path | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Check every built passage against the official text; write ``source_check.json``.

    ``official`` names what the text is (document id, URL, how it was obtained).
    A passage is found when its normalised text occurs in the normalised
    official text. For one that is not, the record gives how far it matches.
    """
    base = (root or default_regulations_root()) / jurisdiction.upper()
    rows = [json.loads(x) for x in (base / "index" / "passages.jsonl").read_text(
        encoding="utf-8").splitlines() if x]
    doc = normalise(official_text)
    results = []
    for r in rows:
        n = normalise(r["text"])
        entry: dict[str, Any] = {"passage_id": r["passage_id"], "text_sha256": text_sha256(n),
                                 "found": n in doc}
        if not entry["found"]:
            lo, hi = 0, len(n)
            while lo < hi:  # the longest prefix of the passage that the official text contains
                mid = (lo + hi + 1) // 2
                lo, hi = (mid, hi) if n[:mid] in doc else (lo, mid - 1)
            entry |= {"matches_up_to": lo, "of": len(n), "diverges_at": n[max(0, lo - 40):lo + 60]}
        results.append(entry)
    record = {
        "jurisdiction": jurisdiction.upper(),
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "official": official | {"text_sha256": _sha256(doc.encode("utf-8")), "chars": len(doc)},
        "method": "passage text normalised (NFKC, quotes, dashes, whitespace) and searched "
                  "for verbatim in the normalised official text",
        "passages": len(results),
        "found": sum(1 for x in results if x["found"]),
        "results": results,
    }
    if write:
        (base / SOURCE_CHECK).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def source_check_status(
    jurisdiction: str, passages: Any, root: Path | None = None
) -> dict[str, Any] | None:
    """The recorded source check, applied to the passages as they are now.

    A passage counts as checked only if its current text is the text that was
    found; an edit since the check makes it unchecked again.
    """
    path = (root or default_regulations_root()) / jurisdiction.upper() / SOURCE_CHECK
    if not path.is_file():
        return None
    rec = json.loads(path.read_text(encoding="utf-8"))
    found = {(r["passage_id"], r["text_sha256"]) for r in rec.get("results", []) if r["found"]}
    ps = list(passages)
    unchecked = sorted(p.passage_id for p in ps if (p.passage_id, text_sha256(p.text)) not in found)
    return {"checked_at": rec.get("checked_at"), "official": rec.get("official", {}).get("id"),
            "official_text_sha256": rec.get("official", {}).get("text_sha256"),
            "passages": len(ps), "found": len(ps) - len(unchecked), "unchecked": unchecked}


def list_corpora(root: Path | None = None) -> list[dict[str, Any]]:
    out = []
    for spec_path in sorted((root or default_regulations_root()).glob("*/corpus.yaml")):
        base = spec_path.parent
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
        mpath = base / "index" / "corpus_manifest.json"
        manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.is_file() else None
        ppath = base / "index" / "passages.jsonl"
        checked = source_check_status(
            base.name,
            [Passage(**json.loads(x)) for x in ppath.read_text(encoding="utf-8").splitlines() if x],
            spec_path.parent.parent,
        ) if ppath.is_file() else None
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
                "source_check": checked,
            }
        )
    return out
