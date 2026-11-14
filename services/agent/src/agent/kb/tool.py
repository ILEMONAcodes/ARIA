"""Offline search tool; only the configured policy folder is readable."""

from pathlib import Path
from typing import ClassVar

from agent.contracts.plan import Risk
from agent.kb.library import PolicyLibrary, SearchInput, SearchOutput
from agent.security.keys import OSVaultKeyProvider
from agent.store.database import open_database
from agent.tools.base import Tool


class PolicySearch(Tool[SearchInput, SearchOutput]):
    name = "kb.search"
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 30.0
    input_model = SearchInput
    output_model = SearchOutput

    def __init__(self, folder: Path, database: Path) -> None:
        self.folder, self.database = folder.resolve(strict=True), database.resolve()
        if not self.folder.is_dir() or self.database.is_relative_to(self.folder):
            raise ValueError("The policy cache must be outside the source folder")

    def dry_run(self, args: SearchInput) -> str:
        return "Search the configured policy library locally."

    def run(self, args: SearchInput) -> SearchOutput:
        with open_database(self.database, OSVaultKeyProvider()) as database:
            library = PolicyLibrary(self.folder, database)
            library.refresh()
            return library.search(args)
