"""Offline, checksum-verified policy retrieval evaluation. Never calls a model."""

from __future__ import annotations

import hashlib
import json
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.kb.library import (
    Manifest,
    Metadata,
    PolicyLibrary,
    SearchInput,
    SearchOutput,
)
from agent.kb.reader import LocalDocumentReader, Passage
from agent.kb.retrieval import SEARCH_CONFIGURATION


class EvaluationError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            "Policy evaluation data is invalid; check fixture hashes and evidence labels."
        )


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    file: str
    doc: str
    page: int | None = Field(default=None, ge=1, le=256)
    date: str | None = None
    section: str | None = None
    evidence: str = Field(min_length=12, max_length=800)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^Q[0-9]{3}$")
    question: str = Field(min_length=10, max_length=512)
    answerable: bool
    expected_points: list[str]
    expected_citations: list[Evidence] = Field(max_length=4)

    @model_validator(mode="after")
    def labelled(self) -> Question:
        if self.answerable != bool(self.expected_points) or self.answerable != bool(
            self.expected_citations
        ):
            raise ValueError(
                "Positive labels require source evidence; negative labels must not invent answers"
            )
        return self


class GoldenSet(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1]
    scope: str
    questions: list[Question] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def balanced(self) -> GoldenSet:
        if (
            len({q.id for q in self.questions}) != 30
            or len({q.question for q in self.questions}) != 30
            or sum(q.answerable for q in self.questions) != 20
        ):
            raise ValueError("Use 30 unique questions: 20 supported and 10 unsupported")
        return self


class SourceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(gt=0, le=10 * 1024 * 1024)
    retrieved_at: str
    rights: str
    rights_url: str
    date_notes: str | None = None
    approval_date: str | None = None
    effective_date: str | None = None


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    purpose: str
    catalog_url: str
    sources: list[SourceProvenance] = Field(min_length=8, max_length=12)


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class EvaluationCorpus:
    """Prepared immutable labels and parsed source snapshots for one benchmark run."""

    def __init__(
        self,
        folder: Path,
        metadata: dict[str, Metadata],
        passages: dict[str, list[Passage]],
        fingerprint: str,
    ):
        self.folder, self.metadata, self.passages, self.fingerprint = (
            folder,
            metadata,
            passages,
            fingerprint,
        )

    def validate_labels(self, golden: GoldenSet) -> None:
        for question in golden.questions:
            for label in question.expected_citations:
                meta = self.metadata.get(label.file)
                if (
                    meta is None
                    or label.doc != meta.title
                    or label.date != (meta.issue_date.isoformat() if meta.issue_date else None)
                ):
                    raise EvaluationError()
                if not any(
                    p.page == label.page
                    and p.section == label.section
                    and normalized(label.evidence) in normalized(p.text)
                    for p in self.passages[label.file]
                ):
                    raise EvaluationError()

    def check_citations(self, output: SearchOutput) -> tuple[list[dict[str, Any]], bool]:
        returned = []
        for citation in output.citations:
            valid = False
            try:
                path = Path(citation.file_path)
                file = path.relative_to(self.folder).as_posix()
                meta = self.metadata[file]
                valid = (
                    path.resolve(strict=True) == path
                    and citation.doc == meta.title
                    and citation.date == (meta.issue_date.isoformat() if meta.issue_date else None)
                    and any(
                        p.page == citation.page
                        and citation.passage
                        == (f"Section: {p.section}\n\n" if p.section else "") + p.text
                        for p in self.passages[file]
                    )
                )
            except (KeyError, ValueError, OSError):
                file = "unrecognized-source"
            returned.append({"file": file, "page": citation.page, "valid": valid})
        return returned, all(c["valid"] for c in returned)


def prepare_corpus(repo: Path, destination: Path) -> EvaluationCorpus:
    """Copy only bundled, verified inputs. No downloads, native vault or user files."""
    try:
        destination.mkdir(parents=True, exist_ok=False)
        public = repo / "library/public_policies"
        provenance = Provenance.model_validate_json((public / "provenance.json").read_bytes())
        sources = {s.file: s for s in provenance.sources}
        if len(sources) != len(provenance.sources):
            raise EvaluationError()
        metadata: dict[str, Metadata] = {}
        passages: dict[str, list[Passage]] = {}
        identity = []
        reader = LocalDocumentReader()
        for prefix, source in (("public", public), ("fictional", repo / "library/policies")):
            manifest = Manifest.model_validate_json((source / "manifest.json").read_bytes())
            files = [m.file for m in manifest.documents]
            if len(set(files)) != len(files) or prefix == "public" and set(files) != set(sources):
                raise EvaluationError()
            if prefix == "fictional" and len(files) != 3:
                raise EvaluationError()
            for item in manifest.documents:
                path = source / item.file
                if path.is_symlink() or not path.resolve(strict=True).is_relative_to(
                    source.resolve()
                ):
                    raise EvaluationError()
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                if prefix == "public":
                    origin = sources[item.file]
                    if (
                        digest != origin.sha256
                        or len(data) != origin.bytes
                        or urlsplit(origin.url).scheme != "https"
                        or urlsplit(origin.url).hostname not in {"nitda.gov.ng", "www.nitda.gov.ng"}
                    ):
                        raise EvaluationError()
                file = prefix + "/" + item.file
                meta = item.model_copy(update={"file": file})
                if file in metadata:
                    raise EvaluationError()
                metadata[file] = meta
                passages[file] = reader.read(data, path.suffix.casefold())
                target = destination / file
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                identity.append(
                    {"file": file, "sha256": digest, "metadata": meta.model_dump(mode="json")}
                )
        (destination / "manifest.json").write_text(
            json.dumps(
                {"documents": [m.model_dump(mode="json") for m in metadata.values()]},
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        fingerprint = hashlib.sha256(
            json.dumps(sorted(identity, key=lambda x: x["file"]), sort_keys=True).encode()
        ).hexdigest()
        return EvaluationCorpus(destination.resolve(), metadata, passages, fingerprint)
    except Exception:  # noqa: BLE001 - do not dump source text/parser/native exceptions
        raise EvaluationError() from None


def evaluate(library: PolicyLibrary, corpus: EvaluationCorpus, golden: GoldenSet) -> dict[str, Any]:
    corpus.validate_labels(golden)
    status = library.refresh()
    if status.failed or status.indexed != len(corpus.metadata):
        raise EvaluationError()
    cases: list[dict[str, Any]] = []
    checked = invalid = 0
    for question in golden.questions:
        output = library.search(SearchInput(query=question.question))
        returned, citations_valid = corpus.check_citations(output)
        checked += len(returned)
        invalid += sum(not c["valid"] for c in returned)
        hit = (
            any(
                Path(c.file_path).relative_to(corpus.folder).as_posix() == label.file
                and c.doc == label.doc
                and c.page == label.page
                and c.date == label.date
                and normalized(label.evidence) in normalized(c.passage)
                for c in output.citations
                for label in question.expected_citations
            )
            if question.answerable and citations_valid
            else False
        )
        passed = citations_valid and (
            output.found and hit if question.answerable else not output.found
        )
        cases.append(
            {
                "id": question.id,
                "answerable": question.answerable,
                "found": output.found,
                "support_hit_at_8": hit if question.answerable else None,
                "citation_integrity": citations_valid,
                "passed": passed,
                "returned": returned,
            }
        )
    supported = [c for c in cases if c["answerable"]]
    unsupported = [c for c in cases if not c["answerable"]]
    return {
        "report_version": 1,
        "scope": "offline_keyword_retrieval_only",
        "corpus_sha256": corpus.fingerprint,
        "golden_sha256": hashlib.sha256(golden.model_dump_json().encode()).hexdigest(),
        "documents": status.indexed,
        "passages": status.passages,
        "questions": len(cases),
        "configuration": dict(SEARCH_CONFIGURATION),
        "retriever_sha256": hashlib.sha256(
            Path(__file__).with_name("library.py").read_bytes()
        ).hexdigest(),
        "retrieval_strategy_sha256": hashlib.sha256(
            Path(__file__).with_name("retrieval.py").read_bytes()
        ).hexdigest(),
        "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "metrics": {
            "support_hits": sum(c["support_hit_at_8"] for c in supported),
            "support_questions": len(supported),
            "correct_not_found": sum(not c["found"] for c in unsupported),
            "unsupported_questions": len(unsupported),
            "case_passes": sum(c["passed"] for c in cases),
            "case_pass_pct": round(100 * sum(c["passed"] for c in cases) / len(cases), 2),
            "checked_citations": checked,
            "invalid_citations": invalid,
            "citation_integrity_pct": round(100 * (checked - invalid) / checked, 2)
            if checked
            else None,
        },
        "phase_d_gate_passed": False,
        "deferred": [
            "generated_answer_correctness",
            "semantic_retrieval_and_conflict_resolution",
            "real_staff_pc_acceptance",
        ],
        "cases": cases,
    }
