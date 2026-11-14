# Nigerian policy retrieval evaluation

`golden_set.json` contains 30 fixed questions: 20 supported by the bundled
source snapshots and 10 unsupported. Sixteen positive questions cover all eight
Nigerian NITDA PDFs; four cover the explicitly fictional leave/travel/records
policies. Labels contain source file/title, physical PDF page or text section,
known issue date (often null), a supporting excerpt and future answer points.
The obsolete two-question placeholder referring to a missing circular was replaced.

Run from the installed repository environment:

```sh
uv run --locked --all-packages --all-extras python scripts/bench_policy.py
uv run --locked --all-packages --all-extras python scripts/bench_policy.py --output new-policy-report.json --min-case-pass 100
```

This is **offline keyword retrieval evaluation**, not a live model evaluation.
It copies only the eight checksum-verified Nigerian PDFs and three fictional
texts into its own temporary folder, uses a temporary encrypted SQLCipher/FTS5
cache with fake keys, and removes that cache afterward. No native vault, model,
credentials, network, user documents or paid calls are used. Output files must be
new: the CLI refuses to overwrite an existing report.

The verifier rejects changed public PDF bytes, non-approved source hosts,
incorrect titles/dates/pages, fabricated evidence and unbalanced/duplicate labels
before scoring. Every returned citation is checked against the exact extracted
passage and metadata; source integrity is not the same as answer correctness.
Questions are not rewritten by the evaluator, and labels are never imported by
runtime retrieval. Expected points are retained for future model evaluation but
are **not** awarded as correct model answers today.

Metrics:

- `support_hits / support_questions`: supported questions whose top eight results
  contain at least one expected source/page and the labelled supporting excerpt.
- `correct_not_found / unsupported_questions`: unsupported questions with
  `found=false`; suggestions are permitted and must still have intact provenance.
- `case_passes`: a positive case needs both `found=true` and expected support;
  a negative needs `found=false`. Every citation in either case must be intact.
- `citation_integrity_pct`: exact source/page/date/passage checks for returned
  citations. It is null when no citations were checked, rather than a false 100%.

Reports pin the corpus, golden labels and code hashes, plus retrieval configuration.
Case-level failures remain visible. `phase_d_gate_passed` stays false because
answer generation, semantic quality/conflicts and real staff acceptance remain open.
`--min-case-pass` is an explicit keyword regression threshold, not that Phase D gate.

## Preserved before/after results

| Result | Original keyword baseline | Improved lexical retrieval |
|---|---:|---:|
| Supporting source/excerpt in top eight | 18/20 | 20/20 |
| Unsupported questions signalled not found | 10/10 | 10/10 |
| Full keyword decision cases | 11/30 | 30/30 |
| Intact returned citations | 227/227 | 157/157 |

See `reports/keyword_baseline.json` and `reports/keyword_improved.json`. Both use
the same corpus and question hashes. The improvements use stemming, heading
search, reusable lexical families, question-word handling, relevance-first ranking
and weighted term coverage. They contain no question IDs or expected answers.
Eighteen additional paraphrase/negative/migration/ranking regressions live in
`services/agent/tests/unit/test_policy_retrieval.py`; they are regression cases,
not a claim of a blind external quality test.

Do not change labels or mark a question unsupported merely to improve a score.
Add reviewed evidence/version changes explicitly and preserve comparable reports.
The full Phase D target remains at least 90% on correct generated answer,
correct citation and honest unsupported behavior when model work resumes.
