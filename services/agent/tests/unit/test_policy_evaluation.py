"""Model-free evaluator tests, using public Nigerian and explicitly fictional fixtures."""

import copy
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from agent.contracts.events import Citation
from agent.fakes import FakeDatabaseKeys
from agent.kb.evaluation import (
    EvaluationCorpus,
    EvaluationError,
    GoldenSet,
    evaluate,
    prepare_corpus,
)
from agent.kb.library import Metadata, PolicyLibrary, SearchOutput
from agent.kb.reader import Passage
from agent.store.database import open_database

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("policy-evaluation")
    corpus = prepare_corpus(ROOT, root / "sources")
    golden = GoldenSet.model_validate_json(
        (ROOT / "tests/kb_questions/golden_set.json").read_bytes()
    )
    return root, corpus, golden


def test_real_nigerian_corpus_and_thirty_questions_run_with_sockets_blocked(prepared):
    root, corpus, golden = prepared
    assert len(corpus.metadata) == 11
    assert sum(file.startswith("public/") for file in corpus.metadata) == 8
    assert sum(q.answerable for q in golden.questions) == 20
    with open_database(root / "evaluation.db", FakeDatabaseKeys()) as database:
        report = evaluate(PolicyLibrary(corpus.folder, database), corpus, golden)
    assert report["questions"] == 30 and report["documents"] == 11
    assert report["metrics"]["invalid_citations"] == 0
    assert report["metrics"]["checked_citations"] > 0
    assert report["metrics"]["case_passes"] == sum(c["passed"] for c in report["cases"])
    assert report["phase_d_gate_passed"] is False
    assert str(root) not in json.dumps(report)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate_id", "duplicate_question", "unbalanced", "invented_answer"]
)
def test_golden_set_requires_twenty_supported_ten_unsupported_unique_questions(mutation):
    data = json.loads((ROOT / "tests/kb_questions/golden_set.json").read_text())
    if mutation == "missing":
        data["questions"].pop()
    elif mutation == "duplicate_id":
        data["questions"][1]["id"] = data["questions"][0]["id"]
    elif mutation == "duplicate_question":
        data["questions"][1]["question"] = data["questions"][0]["question"]
    elif mutation == "unbalanced":
        data["questions"][20] = {
            **data["questions"][0],
            "id": "Q021",
            "question": "Another supported question?",
        }
    else:
        data["questions"][20]["expected_points"] = ["Invented fictional answer"]
    with pytest.raises(ValueError):
        GoldenSet.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("page", 256),
        ("file", "public/missing.pdf"),
        ("evidence", "This phrase does not appear in the cited source."),
        ("date", "2001-01-01"),
        ("doc", "Wrong source title"),
    ],
)
def test_evidence_labels_are_verified_against_actual_pages_and_metadata(prepared, field, value):
    _, corpus, golden = prepared
    changed = copy.deepcopy(golden)
    setattr(changed.questions[0].expected_citations[0], field, value)
    with pytest.raises(EvaluationError):
        corpus.validate_labels(changed)


def test_public_pdf_hash_changes_fail_before_benchmarking(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "library", repo / "library")
    path = repo / "library/public_policies/ng-domain-management.pdf"
    path.write_bytes(path.read_bytes() + b"\nchanged source snapshot")
    with pytest.raises(EvaluationError):
        prepare_corpus(repo, tmp_path / "output")


def test_public_source_links_cannot_silently_switch_to_non_nigerian_publishers(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "library", repo / "library")
    path = repo / "library/public_policies/provenance.json"
    data = json.loads(path.read_text())
    data["sources"][0]["url"] = "https://example.invalid/foreign-policy.pdf"
    path.write_text(json.dumps(data))
    with pytest.raises(EvaluationError):
        prepare_corpus(repo, tmp_path / "output")


def toy_corpus(tmp_path):
    (tmp_path / "right.txt").write_text("Annual leave requires a request form.")
    (tmp_path / "other.txt").write_text("Travel expenses require receipts.")
    meta = {
        "right.txt": Metadata(file="right.txt", title="Fictional Leave"),
        "other.txt": Metadata(file="other.txt", title="Fictional Travel"),
    }
    corpus = EvaluationCorpus(
        tmp_path,
        meta,
        {
            "right.txt": [Passage("Annual leave requires a request form.")],
            "other.txt": [Passage("Travel expenses require receipts.")],
        },
        "a" * 64,
    )
    questions = []
    for i in range(1, 31):
        positive = i <= 20
        questions.append(
            {
                "id": f"Q{i:03d}",
                "question": f"What is the fictional policy for example {i}?",
                "answerable": positive,
                "expected_points": ["A request form"] if positive else [],
                "expected_citations": [
                    {
                        "file": "right.txt",
                        "doc": "Fictional Leave",
                        "evidence": "Annual leave requires a request form.",
                    }
                ]
                if positive
                else [],
            }
        )
    golden = GoldenSet.model_validate(
        {"schema_version": 1, "scope": "Unit fixture only", "questions": questions}
    )
    return corpus, golden


def result(corpus, *, found=True, wrong=False):
    name = "other.txt" if wrong else "right.txt"
    return SearchOutput(
        message="Fictional result",
        found=found,
        citations=[
            Citation(
                doc=corpus.metadata[name].title,
                passage=corpus.passages[name][0].text,
                file_path=str(corpus.folder / name),
            )
        ],
    )


def test_scorer_does_not_credit_suggestions_or_wrong_evidence_as_full_success(tmp_path):
    from agent.kb.library import IndexStatus

    corpus, golden = toy_corpus(tmp_path)

    class Library:
        calls = 0

        def refresh(self):
            return IndexStatus(indexed=2, failed=0, passages=2, errors=[])

        def search(self, args):
            self.calls += 1
            if self.calls == 1:
                return result(corpus)
            if self.calls == 2:
                return result(corpus, wrong=True)
            if self.calls <= 20:
                return result(corpus, found=False)  # Correct passage, suggestions only.
            if self.calls == 21:
                return result(corpus)  # False-positive keyword decision.
            return SearchOutput(message="Not found", found=False, citations=[])

    report = evaluate(Library(), corpus, golden)
    assert report["metrics"]["support_hits"] == 19
    assert report["metrics"]["correct_not_found"] == 9
    assert report["metrics"]["case_passes"] == 10
    assert report["metrics"]["invalid_citations"] == 0
    assert report["cases"][2]["support_hit_at_8"] is True and report["cases"][2]["passed"] is False


def test_empty_retrieval_does_not_claim_perfect_citation_integrity(tmp_path):
    from agent.kb.library import IndexStatus

    corpus, golden = toy_corpus(tmp_path)

    class Library:
        def refresh(self):
            return IndexStatus(indexed=2, failed=0, passages=2, errors=[])

        def search(self, args):
            return SearchOutput(message="Not found", found=False, citations=[])

    report = evaluate(Library(), corpus, golden)
    assert report["metrics"]["citation_integrity_pct"] is None
    assert report["metrics"]["support_hits"] == 0 and report["metrics"]["case_passes"] == 10


@pytest.mark.parametrize(
    "field,value",
    [
        ("file_path", "/outside/private.txt"),
        ("passage", "Invented source passage"),
        ("date", "2001-01-01"),
        ("doc", "Unrelated document"),
    ],
)
def test_unfaithful_citations_are_flagged(tmp_path, field, value):
    corpus, _ = toy_corpus(tmp_path)
    output = result(corpus)
    setattr(output.citations[0], field, value)
    checked, valid = corpus.check_citations(output)
    assert valid is False and checked[0]["valid"] is False


def cli_module():
    spec = importlib.util.spec_from_file_location("bench_policy", ROOT / "scripts/bench_policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_threshold_is_separate_from_fixture_health_and_refuses_overwrites(
    tmp_path, monkeypatch, capsys
):
    module = cli_module()

    class Corpus:
        folder = tmp_path

    monkeypatch.setattr(module, "prepare_corpus", lambda *args: Corpus())
    monkeypatch.setattr(
        module,
        "evaluate",
        lambda *args: {
            "metrics": {"invalid_citations": 0, "case_pass_pct": 36.67},
            "phase_d_gate_passed": False,
        },
    )
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["bench_policy", "--output", str(output)])
    assert module.main() == 0
    assert json.loads(output.read_text())["phase_d_gate_passed"] is False
    before = output.read_bytes()
    assert module.main() == 1 and output.read_bytes() == before
    monkeypatch.setattr("sys.argv", ["bench_policy", "--min-case-pass", "90"])
    assert module.main() == 1
    assert "offline" in module.__doc__
    capsys.readouterr()


def test_root_manifest_describes_all_nigerian_and_fictional_documents():
    from agent.kb.library import Manifest

    root = Manifest.model_validate_json((ROOT / "library/manifest.json").read_bytes())
    expected = []
    for prefix in ("public_policies", "policies"):
        manifest = Manifest.model_validate_json(
            (ROOT / "library" / prefix / "manifest.json").read_bytes()
        )
        expected.extend(
            m.model_copy(update={"file": prefix + "/" + m.file}) for m in manifest.documents
        )
    assert {m.file: m.model_dump() for m in root.documents} == {
        m.file: m.model_dump() for m in expected
    }


def test_before_and_after_reports_use_identical_frozen_questions_and_sources(prepared):
    _, corpus, golden = prepared
    baseline = json.loads((ROOT / "tests/kb_questions/reports/keyword_baseline.json").read_text())
    improved = json.loads((ROOT / "tests/kb_questions/reports/keyword_improved.json").read_text())
    import hashlib

    assert baseline["corpus_sha256"] == improved["corpus_sha256"] == corpus.fingerprint
    assert (
        baseline["golden_sha256"]
        == improved["golden_sha256"]
        == hashlib.sha256(golden.model_dump_json().encode()).hexdigest()
    )
    assert baseline["metrics"]["case_passes"] < improved["metrics"]["case_passes"]
    assert not baseline["phase_d_gate_passed"] and not improved["phase_d_gate_passed"]
