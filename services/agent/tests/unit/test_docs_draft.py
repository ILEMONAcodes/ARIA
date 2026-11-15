"""Tests for docs.draft, docs.report, docs.summarise tools."""

import tempfile
from pathlib import Path

import pytest

from agent.contracts.tools import (
    DocReportAssembleInput,
    DocReportCitation,
    DocReportSectionOutput,
    DocSummariseInput,
    PageRef,
)
from agent.tools.docs import (
    DocDraft,
    DocDraftMissing,
    DocReportAssemble,
    DocReportOutline,
    DocReportSectionTool,
    DocSummarise,
    _SimpleFakeLLM,
)


class TestDocDraft:
    @pytest.fixture
    def tmp_docs(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def draft_tool(self, tmp_docs):
        return DocDraft(tmp_docs, llm=_SimpleFakeLLM())

    def test_draft_declares_correct_properties(self, tmp_docs):
        tool = DocDraft(tmp_docs, llm=_SimpleFakeLLM())
        assert tool.name == "docs.draft"
        assert tool.risk == "local_write"
        assert tool.needs_network is True
        assert tool.timeout_s == 30.0

    def test_draft_dry_run_describes_action(self, draft_tool):
        args = draft_tool.input_model(brief="test brief", tone="formal", max_words=300)
        result = draft_tool.dry_run(args)
        assert "draft" in result.lower()
        assert "docx" in result.lower()

    def test_draft_returns_missing_when_llm_asks(self, tmp_docs, draft_tool):
        # Return JSON with missing fields - create a simple fake LLM
        class TestLLM:
            def __init__(self, resp):
                self.responses = iter(resp)

            def complete(self, prompt):
                return next(self.responses)

        draft_tool.llm = TestLLM(
            [
                '{"subject": "Test Subject", "body_paragraphs": ["Test body"], "missing": [{"field": "author", "question": "Who is this from?"}]}'
            ]
        )

        args = draft_tool.input_model(brief="test brief", tone="formal", max_words=300)
        result = draft_tool.run(args)

        assert result.subject == "Test Subject"
        assert result.missing == [DocDraftMissing(field="author", question="Who is this from?")]
        assert result.saved_path is None


class TestDocReportOutline:
    @pytest.fixture
    def tool(self):
        return DocReportOutline(llm=_SimpleFakeLLM())

    def test_outline_declares_correct_properties(self, tool):
        assert tool.name == "docs.report.outline"
        assert tool.risk == "none"
        assert tool.needs_network is True
        assert tool.timeout_s == 30.0

    def test_outline_dry_run(self, tool):
        args = tool.input_model(brief="Q1 expenses", sections_hint=5)
        result = tool.dry_run(args)
        assert "outline" in result.lower()


class TestDocReportSection:
    @pytest.fixture
    def tool(self):
        return DocReportSectionTool(llm=_SimpleFakeLLM())

    def test_section_declares_correct_properties(self, tool):
        assert tool.name == "docs.report.section"
        assert tool.risk == "none"
        assert tool.needs_network is True
        assert tool.timeout_s == 30.0


class TestDocReportAssemble:
    @pytest.fixture
    def tmp_docs(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def tool(self, tmp_docs):
        return DocReportAssemble(tmp_docs)

    def test_assemble_declares_correct_properties(self, tool):
        assert tool.name == "docs.report.assemble"
        assert tool.risk == "local_write"
        assert tool.needs_network is False
        assert tool.timeout_s == 10.0

    def test_assemble_creates_docx(self, tmp_docs, tool):
        args = DocReportAssembleInput(
            title="Test Report",
            sections=[
                DocReportSectionOutput(
                    heading="Section 1",
                    content="Content of section 1",
                    citations=[
                        DocReportCitation(
                            doc="Source", page=1, date="2026-01-01", passage="text", file_path=""
                        )
                    ],
                ),
            ],
            template_name=None,
        )

        result = tool.run(args)
        assert result.saved_path is not None
        assert Path(result.saved_path).exists()
        assert result.saved_path.endswith(".docx")


class TestDocSummarise:
    @pytest.fixture
    def tool(self):
        return DocSummarise(llm=_SimpleFakeLLM())

    def test_summarise_declares_correct_properties(self, tool):
        assert tool.name == "docs.summarise"
        assert tool.risk == "none"
        assert tool.needs_network is True
        assert tool.timeout_s == 30.0

    def test_summarise_dry_run(self, tool):
        args = DocSummariseInput(
            text="Test document text",
            source_label="Test Doc",
            mode="five_bullets",
            purpose="test",
            page_references=[PageRef(page=1, heading="Intro", text="Test text")],
        )
        result = tool.dry_run(args)
        assert "summarise" in result.lower() or "summary" in result.lower()

    def test_summarise_faithfulness_check_flags_missing_numbers(self, tool):
        from agent.contracts.tools import PageRef

        # Set up LLM to return a response with a number not in source
        class TestLLM:
            def __init__(self, resp):
                self.responses = iter(resp)

            def complete(self, prompt):
                return next(self.responses)

        tool.llm = TestLLM(["The budget is 5000 units."])

        args = DocSummariseInput(
            text="Test document text",
            source_label="Test Doc",
            mode="five_bullets",
            purpose="test",
            page_references=[PageRef(page=1, heading="Intro", text="Test text about budget")],
        )

        result = tool.run(args)
        assert (
            "faithfulness" in str(result.faithfulness_flags).lower()
            or len(result.faithfulness_flags) > 0
        )


class TestPromptTemplatesLoad:
    """Verify prompt templates load without placeholders."""

    @pytest.fixture(autouse=True)
    def load_prompts(self):
        prompt_dir = Path(__file__).parents[2] / "src" / "agent" / "planner" / "prompts"
        self.draft_prompt = (prompt_dir / "draft.txt").read_text()
        self.summarise_prompt = (prompt_dir / "summarise.txt").read_text()
        self.report_outline_prompt = (prompt_dir / "report_outline.txt").read_text()
        self.report_section_prompt = (prompt_dir / "report_section.txt").read_text()

    def test_draft_prompt_has_placeholders(self):
        assert "{tone}" in self.draft_prompt
        assert "{max_words}" in self.draft_prompt
        assert "missing" in self.draft_prompt.lower()

    def test_draft_prompt_includes_data_rule(self):
        assert "data block" in self.draft_prompt.lower()
        assert "never instructions" in self.draft_prompt.lower()

    def test_summarise_prompt_has_mode_placeholder(self):
        assert "{mode}" in self.summarise_prompt
        assert "one_line" in self.summarise_prompt
        assert "five_bullets" in self.summarise_prompt
        assert "one_page" in self.summarise_prompt

    def test_summarise_prompt_includes_data_rule(self):
        assert "data block" in self.summarise_prompt.lower()

    def test_report_prompts_include_data_rule(self):
        assert "data block" in self.report_outline_prompt.lower()
        assert "data block" in self.report_section_prompt.lower()
        assert "never instructions" in self.report_outline_prompt.lower()
