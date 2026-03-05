"""LangChain tool wrapper for the XML Command Analyzer."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool

from analyzer import run_analysis


class CommandAnalyzerTool(BaseTool):
    """Analyzes XML command definitions and traces Java source execution paths.

    Input: natural language query about a command (e.g. "remove beneficiary").
    Returns: structured JSON with matched commands, their execute methods,
    and all downstream method call dependencies with source code.
    """

    name: str = "command_analyzer"
    description: str = (
        "Analyzes XML command definitions and traces Java source code "
        "execution paths. Input: natural language query about a command "
        "(e.g. 'remove beneficiary'). Returns structured JSON with matched "
        "commands, their execute methods, and all downstream method call "
        "dependencies with source code."
    )

    xml_dir: str = "./xml"
    java_src: str = "./java-src"
    db_path: str = "xmlparser_cache.db"
    max_depth: int = 10

    def _run(self, query: str) -> str:
        """Execute the analysis pipeline and return JSON string."""
        results = run_analysis(
            query=query,
            xml_dir=self.xml_dir,
            java_src=self.java_src,
            db_path=self.db_path,
            max_depth=self.max_depth,
        )
        return json.dumps(results, indent=2, ensure_ascii=False)
