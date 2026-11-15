# Sample policy library

The library contains eight original Nigerian NITDA public-policy PDFs in
`public_policies/` and three explicitly fictional internal policies in `policies/`.
No confidential office files or U.S. policies are included. The root manifest
covers all eleven sources; each collection also has its own manifest.

Public source URLs, original-byte hashes, date caveats and reuse basis are recorded
in `public_policies/provenance.json` and its README. Unknown dates/numbers remain
unknown. Public source snapshots are not a claim of current legal applicability.
The fictional policies are demo data, not Nigerian government rules.

Run `python -m agent.kb --demo --query "annual leave"` in the installed environment
for a temporary fictional-only demo. `python scripts/bench_policy.py` evaluates
the combined eleven-document corpus offline against the fixed 30 questions.
See docs/OFFLINE_POLICY_SEARCH.md, tests/kb_questions/README.md and
`docs/BACKEND_HANDOFF.md` for setup, scope, results and remaining work.
