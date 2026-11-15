"""Bounded lexical retrieval: stemming, documented term families and weighted coverage."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Protocol

from agent.store.database import Database

SEARCH_CONFIGURATION = {
    "chunk_words": 400,
    "overlap_words": 50,
    "passage_limit": 8,
    "candidate_limit": 64,
    "ranking": "weighted_coverage_then_bm25; newest is explicit",
    "query": "question-stopwords, bounded term families, IDF-weighted coverage >= 0.70",
    "tokenizer": "porter unicode61; headings indexed",
}

_STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "what",
        "which",
        "when",
        "where",
        "how",
        "do",
        "does",
        "did",
        "can",
        "may",
        "must",
        "shall",
        "should",
        "i",
        "me",
        "my",
        "we",
        "our",
        "us",
        "you",
        "your",
        "their",
        "its",
        "who",
        "about",
        "of",
        "to",
        "for",
        "in",
        "on",
        "and",
        "or",
        "please",
        "policy",
        "policies",
        "find",
        "show",
        "search",
        "tell",
        "say",
        "says",
        "according",
        "under",
        "as",
        "at",
        "by",
        "from",
        "with",
        "than",
        "that",
        "this",
        "these",
        "those",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "will",
        "would",
        "could",
        "ought",
        "into",
        "each",
        "any",
        "also",
        "it",
        "they",
        "them",
        "before",
        "after",
        "over",
        "next",
        "many",
        "much",
        "often",
        "early",
        "required",
        "require",
        "requires",
        "requiring",
        "specify",
        "specifies",
        "identify",
        "identifies",
        "define",
        "defines",
        "provide",
        "provides",
        "seeking",
        "seek",
        "details",
        "happen",
        "happens",
        "another",
        "need",
        "needs",
        "needed",
    ]
)

# Reusable lexical families, never question IDs, answers or document-specific routing.
_FAMILIES = {
    "register": ("register", "registration"),
    "nigeria": ("nigeria", "nigerian"),
    "agreement": ("agreement", "contract"),
    "storage": ("store", "storage", "folder"),
    "presence": ("presence", "address", "location"),
    "evidence": ("evidence", "proof", "documentation"),
    "fee": ("fee", "charge"),
    "organisation": ("organisation", "organization"),
    "migration": ("move", "migrate", "migration"),
}
_CANONICAL = {
    **{
        t: "register"
        for t in (
            "register",
            "registers",
            "registered",
            "registering",
            "registration",
            "registrations",
        )
    },
    **{t: "nigeria" for t in ("nigeria", "nigerian", "nigerians")},
    **{t: "agreement" for t in ("agreement", "agreements", "contract", "contracts")},
    **{
        t: "storage"
        for t in ("store", "stores", "stored", "storing", "storage", "folder", "folders")
    },
    **{
        t: "organisation"
        for t in ("organisation", "organisations", "organization", "organizations")
    },
    **{
        t: "migration"
        for t in (
            "move",
            "moves",
            "moved",
            "moving",
            "migrate",
            "migrates",
            "migrated",
            "migration",
        )
    },
    "presence": "presence",
    "evidence": "evidence",
    "proof": "evidence",
    "documentation": "evidence",
    "fee": "fee",
    "fees": "fee",
    "charge": "fee",
    "charges": "fee",
}


@dataclass(frozen=True)
class Hit:
    title: str
    path: str
    issued: str | None
    page: int | None
    section: str | None
    text: str
    fingerprint: str
    coverage: float


@dataclass(frozen=True)
class Retrieval:
    hits: tuple[Hit, ...]
    found: bool
    valid_query: bool = True


class PolicyRetriever(Protocol):
    def search(
        self,
        database: Database,
        root: str,
        query: str,
        *,
        year: int | None,
        circular_no: str | None,
        sort: Literal["relevance", "newest"],
    ) -> Retrieval: ...


def terms(query: str) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKC", query).casefold()
    tokens = re.findall(r"[^\W_]+", text)
    return tuple(
        dict.fromkeys(
            _CANONICAL.get(t, t) for t in tokens if t not in _STOP and (len(t) > 1 or t.isdigit())
        )
    )


def expression(term: str, *, financial: bool = False) -> str:
    # All input tokens are alphanumeric; alternatives are fixed application data.
    variants = _FAMILIES.get(term, (term,))
    if term == "evidence" and financial:
        variants = (*variants, "receipt")
    return "(" + " OR ".join('"' + t + '"' for t in variants) + ")"


class KeywordRetriever:
    def search(
        self,
        database: Database,
        root: str,
        query: str,
        *,
        year: int | None = None,
        circular_no: str | None = None,
        sort: Literal["relevance", "newest"] = "relevance",
    ) -> Retrieval:
        tokens = terms(query)
        financial = bool(
            set(tokens)
            & {
                "travel",
                "expense",
                "expenses",
                "claim",
                "claims",
                "reimbursement",
                "reimbursements",
            }
        )
        if not tokens or len(tokens) > 16 or any(len(t) > 64 for t in tokens):
            return Retrieval((), False, False)
        condition = "d.root=? AND d.error IS NULL"
        parameters: list[str] = [root]
        if year is not None:
            condition += " AND substr(d.issue_date,1,4)=?"
            parameters.append(str(year))
        if circular_no is not None:
            condition += " AND d.circular_no=?"
            parameters.append(circular_no)
        base = " FROM kb_passages p JOIN kb_documents d ON p.document_id=d.id WHERE " + condition
        rows = database.fetch_all(
            "SELECT p.rowid,d.title,d.path,d.issue_date,p.page,p.section,p.text,d.fingerprint,bm25(kb_passages,0,0,2,2,3,0.2,1)"
            + base
            + " AND kb_passages MATCH ? ORDER BY bm25(kb_passages,0,0,2,2,3,0.2,1),d.issue_date DESC,d.path,p.rowid LIMIT 64",
            (*parameters, " OR ".join(expression(t, financial=financial) for t in tokens)),
        )
        if not rows:
            return Retrieval((), False)
        total = database.fetch_all("SELECT count(*)" + base, parameters)[0][0]
        row_ids = tuple(int(row[0]) for row in rows)
        placeholders = ",".join("?" for _ in row_ids)
        coverage: dict[int, float] = dict.fromkeys(row_ids, 0.0)
        matched: dict[int, set[str]] = {id: set() for id in row_ids}
        total_weight = 0.0
        for term in tokens:
            match = expression(term, financial=financial)
            frequency = database.fetch_all(
                "SELECT count(*)" + base + " AND kb_passages MATCH ?", (*parameters, match)
            )[0][0]
            weight = 1 + math.log((total + 1) / (frequency + 1))
            total_weight += weight
            found_rows = database.fetch_all(
                "SELECT p.rowid"
                + base
                + " AND p.rowid IN ("
                + placeholders
                + ") AND kb_passages MATCH ?",
                (*parameters, *row_ids, match),
            )
            for (id,) in found_rows:
                coverage[id] += weight
                matched[id].add(term)
        ranked = sorted(rows, key=lambda row: (-coverage[row[0]] / total_weight, float(row[8])))
        # Keep explicit temporal qualifiers: matching 'payroll' does not establish 'current'.
        mandatory = {t for t in tokens if t in {"current", "latest", "today", "now"}}
        strong = [
            row
            for row in ranked
            if coverage[row[0]] / total_weight >= 0.70 and mandatory <= matched[row[0]]
        ]
        selected = strong if strong else ranked
        if sort == "newest":
            selected.sort(key=lambda row: row[3] or "", reverse=True)
        hits = tuple(
            Hit(
                str(r[1]),
                str(r[2]),
                r[3],
                r[4],
                r[5],
                str(r[6]),
                str(r[7]),
                coverage[r[0]] / total_weight,
            )
            for r in selected[:8]
        )
        return Retrieval(hits, bool(strong))
