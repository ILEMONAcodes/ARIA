# Sample policy library

Put 8 to 12 publicly available circulars and policies here, plus 3 fictional internal circulars for the leave-policy example. Public and fictional documents only. Never real confidential office files.

Record each document's title, circular number, issue date and issuing office in `manifest.json` so tests can check metadata extraction.

`policies/` contains the three fictional D1 demo policies and their explicit
manifest. Run `python -m agent.kb --demo --query "annual leave"` from an installed
agent environment. The top-level manifest is an earlier placeholder, not an
existing public PDF corpus. See docs/OFFLINE_POLICY_SEARCH.md.
