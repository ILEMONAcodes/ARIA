# Phase D1: offline policy library

Implements the model-free foundations of POL-1, POL-3, POL-4 and POL-5. The user
asked to continue with document ingestion and keyword search while voice assets,
providers, embeddings and generated answers remain deferred. This does not pass
the full Phase D/core-loop acceptance gates.

## Try it

From the repository root, after `uv sync --locked --all-packages --all-extras`:

```sh
uv run --locked --all-packages --all-extras python -m agent.kb --demo --query "annual leave"
```

The demo reads only `library/policies`, which contains three explicitly fictional
policies. It creates a temporary encrypted SQLCipher/FTS5 cache with a fake key,
prints passages and citations, then removes its temporary cache. It uses no
model, API key, network, microphone or native credential vault. Fake keys are
never a fallback for production storage.

For an explicitly chosen policy folder on Windows/macOS:

```sh
uv run --locked --all-packages --all-extras python -m agent.kb --library /path/to/policies --database /path/to/data/aria.db --query "annual leave"
uv run --locked --all-packages --all-extras python -m agent.kb --library /path/to/policies --database /path/to/data/aria.db --watch
```

Use actual platform paths. The cache must be outside the source folder. Real
storage uses the existing native vault-backed SQLCipher key provider; missing
keys/encryption/FTS5 fail closed. `--year 2026` and `--circular-no FICTIONAL/HR/2026/01`
filter explicit metadata. Without a query, the command prints indexed/failed
file counts, passage counts and failed relative filenames. `--watch` refreshes
every five seconds until Ctrl-C. It does not watch in the desktop's background
unless this maintenance process is running; each search tool/CLI query also
refreshes before retrieval. Failed files produce a nonzero one-shot CLI exit.

## Desktop text service

Add `policy_folder` and `policy_database` to the root of your local-tools TOML,
before any `[apps.*]` tables. Paths are relative to that file. For example:

```toml
timezone = "Africa/Lagos"
policy_folder = "../library/policies"
policy_database = "../data/aria.db"
```

Then use the existing authenticated `agent.local` service and send the v1
`text.input` command `search policy annual leave`. The planner emits only a
registered offline `kb.search` step. The killable worker refreshes its encrypted
cache and searches locally. The executor emits `result.answer` with extracted
passages/source references, activity and a caption. No cloud routing or new
public fields are added. The terminal local-command mode prints the caption;
use `agent.kb` to see the full citations in a terminal.

Index maintenance is internal cache housekeeping for this read-only source tool;
it never modifies or deletes source documents and adds no general filesystem
write authority. Changed/removed/failed source files replace/remove their old
passages. Changes to one document commit atomically with its metadata; refresh
is not a single transaction across the whole folder. A failed replacement rolls
back that document, and the request fails rather than serve the old answer.

## Provenance and extraction

A folder may contain a `manifest.json` with `documents` entries containing `file`,
`title`, optional `circular_no`, ISO `issue_date`, `issuer` and `supersedes`.
See the fictional manifest. Dates and circular numbers are never inferred from
filenames, filesystem timestamps or model output. Unlisted documents use the
filename as their display title, with unknown dates left null. Duplicate entries,
invalid dates, unknown fields and paths outside the folder are rejected.

UTF-8 text uses `# Heading` sections. DOCX retains body paragraphs, headings and
table cell text, including nested tables. Headers/footers, tracked changes,
textboxes and visual layout are outside this first reader. DOCX and text page
numbers stay null; sections are explicitly labelled in the citation passage.
PDF extraction retains actual one-based page numbers; it does not invent section
headings. Encrypted, malformed and textless/scanned PDF pages are reported as
unsupported for this reader. OCR remains outside the MVP; even a blank PDF page
currently makes that file unsupported. PDF tables/layout still need source review.
Reader behavior follows the [python-docx document API](https://python-docx.readthedocs.io/en/latest/api/document.html)
and [pypdf reader API](https://pypdf.readthedocs.io/en/stable/modules/PdfReader.html).

Documents are split within page/section boundaries into windows of at most 400
whitespace-separated words with 50-word overlap. Short passages are retained.
These are model-free windows, not the final model-token chunk-size decision.
Limits include 1,000 source files, 10 MiB per input, 256 PDF pages, 2 million
extracted characters, 5,000 passages per file, 2,000 DOCX ZIP entries and bounded
expanded DOCX size. Symlinks/nonregular files are excluded and source paths are
checked for containment. Parser warnings do not enter diagnostics. The production
worker has a 30-second tool budget and is terminated on cancellation/timeout.
These checks are not a sandbox or a hard memory quota against hostile parsers;
the standalone indexing CLI has no per-file process deadline. Library folders
are explicitly selected local sources.

## Retrieval and remaining work

The current lexical strategy is behind `PolicyRetriever` in `kb/retrieval.py`.
FTS5 English stemming searches body text and headings. It removes common question
words and uses bounded reusable lexical families (including British/American
spelling, registration/movement terminology and financial proof/receipts).
Raw FTS operators/SQL are never accepted from a query.

At most 64 candidates receive IDF-weighted query-term coverage and BM25 ranking;
coverage of at least 0.70 produces a keyword-match signal. Otherwise results remain
closest suggestions. Temporal qualifiers such as "current" are not silently dropped,
but literal keyword matching still does not establish legal currency or answer truth.
Keep at most eight passages. Relevance is the default; `SearchInput.sort="newest"`
or the CLI's `--newest` requests date-first listing explicitly. Year/circular filters
still use explicit metadata. Unknown issue dates remain unknown. Roots stay isolated.
This is a lexical heuristic, not a semantic probability or generated answer.

Source text remains data even when it looks like instructions. It is only
returned as citations; it cannot add tools or change confirmations. SQLCipher
migration 2 stores metadata and FTS5 content together, preserving migration 1
settings/history and refusing a plaintext fallback. Migration 3 preserves existing
passage rows while enabling English stemming and indexed headings; migrations 1
and 2 remain unchanged.

`test_policy_search.py` covers actual PDF/DOCX/TXT parsing, changed/deleted/failed
files, provenance, filtering, closest/no-match behavior, encryption, atomic
replacement, v1 migration upgrade, traversal/symlink/input bounds, watch refresh
and the authenticated real-session/mock scenario. Unit-test sockets remain blocked.
The separate worker smoke also indexes/searches fictional data in its own temporary
folder through a real subprocess. CI runs both paths on Linux/Windows/macOS.

Still open: vector embeddings/hybrid retrieval, generated grounded answers and
conflict handling, the full generated-answer 30-question quality gate,
frontend index-status/settings controls, real staff/UI
acceptance and performance evaluation. No model setup is needed for this slice.

D2 adds opening the cited snapshot through explicitly configured Windows viewers;
see [OPEN_POLICY_SOURCES.md](OPEN_POLICY_SOURCES.md). Its native viewer/frontend
acceptance checks remain open.

The bundled Nigerian corpus and fixed offline evaluation are documented in
[tests/kb_questions/README.md](../tests/kb_questions/README.md). Its 30/30 keyword
result does not close the full Phase D answer-quality/real-staff gate.
