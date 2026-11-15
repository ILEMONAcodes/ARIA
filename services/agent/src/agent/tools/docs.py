"""Document tools: draft memo, report, and summarise."""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar, Protocol

from docx import Document
from docx.shared import Pt, RGBColor
from pydantic import BaseModel

from agent.contracts.plan import Risk
from agent.contracts.tools import (
    DocDraftInput,
    DocDraftMissing,
    DocDraftOutput,
    DocReportAssembleInput,
    DocReportAssembleOutput,
    DocReportCitation,
    DocReportOutlineInput,
    DocReportOutlineOutput,
    DocReportSection,
    DocReportSectionInput,
    DocReportSectionOutput,
    DocSummariseInput,
    DocSummariseOutput,
    PageRef,
)
from agent.tools.base import Tool


class _LLMAdapter(Protocol):
    """Protocol for LLM adapters used by document tools."""

    def complete(self, prompt: str) -> str: ...


class DocDraft(Tool[DocDraftInput, DocDraftOutput]):
    name = "docs.draft"
    risk: ClassVar[Risk] = "local_write"
    needs_network = True
    timeout_s = 30.0
    input_model = DocDraftInput
    output_model = DocDraftOutput

    def __init__(
        self,
        documents_root: Path,
        llm: _LLMAdapter | None = None,
    ) -> None:
        self.documents_root = documents_root.resolve()
        self.llm = llm or _SimpleFakeLLM()

    def dry_run(self, args: DocDraftInput) -> str:
        return f"Draft a {args.tone} memo from brief (max {args.max_words} words) and save as .docx"

    def run(self, args: DocDraftInput) -> DocDraftOutput:
        prompt = self._build_prompt(args)
        response = self.llm.complete(prompt)
        result = self._parse_response(response)

        if result.missing:
            return DocDraftOutput(
                subject=result.subject,
                body_paragraphs=result.body_paragraphs,
                missing=[
                    DocDraftMissing(field=m["field"], question=m["question"])
                    for m in result.missing
                ],
                saved_path=None,
            )

        saved_path = self._save_docx(args, result)
        return DocDraftOutput(
            subject=result.subject,
            body_paragraphs=result.body_paragraphs,
            missing=[],
            saved_path=saved_path,
        )

    def _build_prompt(self, args: DocDraftInput) -> str:
        template = (Path(__file__).parent.parent / "planner" / "prompts" / "draft.txt").read_text()
        data_block = f'<data id="d1" label="brief">\n{args.brief}\n</data>'
        return template.format(tone=args.tone, max_words=args.max_words) + "\n\n" + data_block

    def _parse_response(self, response: str) -> _DraftResult:
        data = json.loads(response)
        return _DraftResult(
            subject=data["subject"],
            body_paragraphs=data["body_paragraphs"],
            missing=data.get("missing", []),
        )

    def _save_docx(self, args: DocDraftInput, result: _DraftResult) -> str:
        doc = Document()
        self._apply_template(doc)

        # Metadata
        today = datetime.date.today().strftime("%B %d, %Y")

        # To
        p = doc.add_paragraph()
        p.add_run("To: ").bold = True
        p.add_run("Team")

        # From
        p = doc.add_paragraph()
        p.add_run("From: ").bold = True
        p.add_run(self._get_author_name())

        # Date
        p = doc.add_paragraph()
        p.add_run("Date: ").bold = True
        p.add_run(today)

        # Subject
        p = doc.add_paragraph()
        p.add_run("Subject: ").bold = True
        p.add_run(result.subject)

        doc.add_paragraph()  # blank line

        for para in result.body_paragraphs:
            doc.add_paragraph(para)

        # Save
        safe_subject = re.sub(r"[^\w\s-]", "", result.subject).strip().replace(" ", "_")
        date_str = datetime.date.today().isoformat()
        filename = f"{safe_subject}_{date_str}.docx"
        save_path = self.documents_root / filename
        self.documents_root.mkdir(parents=True, exist_ok=True)
        doc.save(str(save_path))
        return str(save_path)

    def _apply_template(self, doc: Any) -> None:
        style = doc.styles["Normal"]
        font = style.font
        font.name = "Calibri"
        font.size = Pt(11)
        font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.line_spacing = 1.15

    def _get_author_name(self) -> str:
        return "ARIA User"


class _DraftResult(BaseModel):
    subject: str
    body_paragraphs: list[str]
    missing: list[dict[str, str]] = []


class DocReportOutline(Tool[DocReportOutlineInput, DocReportOutlineOutput]):
    name = "docs.report.outline"
    risk: ClassVar[Risk] = "none"
    needs_network = True
    timeout_s = 30.0
    input_model = DocReportOutlineInput
    output_model = DocReportOutlineOutput

    def __init__(self, llm: _LLMAdapter | None = None) -> None:
        self.llm = llm or _SimpleFakeLLM()

    def dry_run(self, args: DocReportOutlineInput) -> str:
        return f"Propose a report outline with {args.sections_hint or '5-8'} sections"

    def run(self, args: DocReportOutlineInput) -> DocReportOutlineOutput:
        prompt = self._build_prompt(args)
        response = self.llm.complete(prompt)
        data = json.loads(response)
        sections = [
            DocReportSection(heading=s["heading"], purpose=s["purpose"]) for s in data["sections"]
        ]
        return DocReportOutlineOutput(title=data["title"], sections=sections)

    def _build_prompt(self, args: DocReportOutlineInput) -> str:
        template = (
            Path(__file__).parent.parent / "planner" / "prompts" / "report_outline.txt"
        ).read_text()
        return template


class DocReportSectionTool(Tool[DocReportSectionInput, DocReportSectionOutput]):
    name = "docs.report.section"
    risk: ClassVar[Risk] = "none"
    needs_network = True
    timeout_s = 30.0
    input_model = DocReportSectionInput
    output_model = DocReportSectionOutput

    def __init__(self, llm: _LLMAdapter | None = None) -> None:
        self.llm = llm or _SimpleFakeLLM()

    def dry_run(self, args: DocReportSectionInput) -> str:
        return f"Write report section '{args.heading}'"

    def run(self, args: DocReportSectionInput) -> DocReportSectionOutput:
        prompt = self._build_prompt(args)
        response = self.llm.complete(prompt)
        # The model returns plain text for the section content
        citations = [
            DocReportCitation(
                doc=c.doc,
                page=c.page,
                date=c.date,
                passage=c.passage,
                file_path=c.file_path,
            )
            for c in args.citations
        ]
        return DocReportSectionOutput(
            heading=args.heading, content=response.strip(), citations=citations
        )

    def _build_prompt(self, args: DocReportSectionInput) -> str:
        template = (
            Path(__file__).parent.parent / "planner" / "prompts" / "report_section.txt"
        ).read_text()
        data_blocks = "\n".join(
            f'<data id="d{i}" label="passage" document="{c.doc}" page="{c.page or ""}" date="{c.date or ""}">\n{c.passage}\n</data>'
            for i, c in enumerate(args.citations, 1)
        )
        return template.format(heading=args.heading, purpose=args.purpose) + "\n\n" + data_blocks


class DocReportAssemble(Tool[DocReportAssembleInput, DocReportAssembleOutput]):
    name = "docs.report.assemble"
    risk: ClassVar[Risk] = "local_write"
    needs_network = False
    timeout_s = 10.0
    input_model = DocReportAssembleInput
    output_model = DocReportAssembleOutput

    def __init__(self, documents_root: Path) -> None:
        self.documents_root = documents_root.resolve()

    def dry_run(self, args: DocReportAssembleInput) -> str:
        return f"Assemble {len(args.sections)} sections into a report .docx"

    def run(self, args: DocReportAssembleInput) -> DocReportAssembleOutput:
        doc = Document()
        self._apply_template(doc)

        doc.add_heading(args.title, level=1)
        doc.add_paragraph()

        for section in args.sections:
            doc.add_heading(section.heading, level=2)
            doc.add_paragraph(section.content)
            if section.citations:
                p = doc.add_paragraph()
                p.add_run("Sources: ").italic = True
                cites = "; ".join(
                    f"{c.doc}" + (f", page {c.page}" if c.page else "") for c in section.citations
                )
                p.add_run(cites).italic = True
            doc.add_paragraph()

        safe_title = re.sub(r"[^\w\s-]", "", args.title).strip().replace(" ", "_")
        date_str = datetime.date.today().isoformat()
        filename = f"{safe_title}_{date_str}.docx"
        save_path = self.documents_root / filename
        self.documents_root.mkdir(parents=True, exist_ok=True)
        doc.save(str(save_path))
        return DocReportAssembleOutput(saved_path=str(save_path))

    def _apply_template(self, doc: Any) -> None:
        style = doc.styles["Normal"]
        font = style.font
        font.name = "Calibri"
        font.size = Pt(11)
        font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.line_spacing = 1.15


class DocSummarise(Tool[DocSummariseInput, DocSummariseOutput]):
    name = "docs.summarise"
    risk: ClassVar[Risk] = "none"
    needs_network = True
    timeout_s = 30.0
    input_model = DocSummariseInput
    output_model = DocSummariseOutput

    def __init__(self, llm: _LLMAdapter | None = None) -> None:
        self.llm = llm or _SimpleFakeLLM()

    def dry_run(self, args: DocSummariseInput) -> str:
        return f"Summarise '{args.source_label}' in {args.mode} mode"

    def run(self, args: DocSummariseInput) -> DocSummariseOutput:
        prompt = self._build_prompt(args)
        response = self.llm.complete(prompt)

        # Build citations from page references
        citations = [
            DocReportCitation(
                doc=args.source_label,
                page=ref.page,
                date=None,
                passage=ref.text[:200],
                file_path="",
            )
            for ref in args.page_references
            if ref.text.strip()
        ]

        # Faithfulness check
        flags = self._faithfulness_check(response, args.page_references)

        return DocSummariseOutput(
            summary=response.strip(), citations=citations, faithfulness_flags=flags
        )

    def _build_prompt(self, args: DocSummariseInput) -> str:
        template = (
            Path(__file__).parent.parent / "planner" / "prompts" / "summarise.txt"
        ).read_text()
        purpose = args.purpose or "general reference"
        data_blocks = "\n".join(
            f'<data id="d{i}" label="{args.source_label}" page="{ref.page or ""}" heading="{ref.heading or ""}">\n{ref.text}\n</data>'
            for i, ref in enumerate(args.page_references, 1)
        )
        return template.format(mode=args.mode, purpose=purpose) + "\n\n" + data_blocks

    def _faithfulness_check(self, summary: str, page_refs: list[PageRef]) -> list[str]:
        """Check that every number, date, and proper noun in summary appears in source."""
        flags = []
        source_text = " ".join(ref.text for ref in page_refs)

        # Simple check for numbers
        import re

        numbers = re.findall(r"\b\d+(?:[.,]\d+)?\b", summary)
        for num in numbers:
            if num not in source_text:
                flags.append(f"Number '{num}' not found in source")

        # Simple check for dates (ISO format)
        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", summary)
        for date in dates:
            if date not in source_text:
                flags.append(f"Date '{date}' not found in source")

        # Simple check for capitalized words (proper nouns)
        proper_nouns = re.findall(r"\b[A-Z][a-z]+\b", summary)
        for noun in proper_nouns:
            if noun not in source_text and noun not in [
                "The",
                "This",
                "That",
                "And",
                "But",
                "For",
                "With",
            ]:
                flags.append(f"Proper noun '{noun}' not found in source")

        return flags


class _SimpleFakeLLM:
    """Simple fake LLM adapter for tests. Returns minimal valid JSON for each prompt type."""

    def __init__(self) -> None:
        self.responses: Iterator[str] = iter([])

    def complete(self, prompt: str) -> str:
        try:
            return next(self.responses)
        except StopIteration:
            # Return default valid responses based on prompt content
            if "draft" in prompt.lower() or "memo" in prompt.lower():
                return (
                    '{"subject": "Test Subject", "body_paragraphs": ["Test body."], "missing": []}'
                )
            elif "outline" in prompt.lower():
                return '{"title": "Test Report", "sections": [{"heading": "Section 1", "purpose": "Test"}]}'
            elif "summarise" in prompt.lower() or "summarize" in prompt.lower():
                return "Test summary with no invented facts."
            else:
                return "Test response."
