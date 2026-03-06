"""LangChain tool wrapper for the XML Command Analyzer."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool

from analyzer import run_analysis


def _collect_methods(method_dict: dict, collected: list[dict]) -> None:
    """Recursively walk a method tree and collect class/method/source_code entries."""
    collected.append({
        "class": method_dict["class"],
        "method": method_dict["method"],
        "source_code": method_dict["source_code"],
    })
    for call in method_dict.get("downstream_calls", []):
        if call.get("resolved_method"):
            _collect_methods(call["resolved_method"], collected)


def _estimate_tokens(text: str) -> int:
    """Estimate token count using a simple word/symbol-based heuristic.

    Approximates ~4 characters per token, which is a common rough estimate
    for English text and code.
    """
    return max(1, len(text) // 4)


class CommandAnalyzerTool(BaseTool):
    """Analyzes XML command definitions and traces Java source execution paths.

    Input: natural language query about a command (e.g. "remove beneficiary").
    Returns: a string containing all resolved method source code entries
    (class, method, source_code) and the estimated token size.
    """

    name: str = "command_analyzer"
    description: str = (
        "Analyzes XML command definitions and traces Java source code "
        "execution paths. Input: natural language query about a command "
        "(e.g. 'remove beneficiary'). Returns all resolved methods with "
        "their class name, method name, and full source code, along with "
        "the total token count."
    )

    xml_dir: str = "./xml"
    java_src: str = "./java-src"
    db_path: str = "xmlparser_cache.db"
    max_depth: int = 10

    def _run(self, query: str) -> str:
        """Execute the analysis pipeline and return method source code with token count."""
        results = run_analysis(
            query=query,
            xml_dir=self.xml_dir,
            java_src=self.java_src,
            db_path=self.db_path,
            max_depth=self.max_depth,
        )

        # Collect all resolved methods from the result tree
        all_methods: list[dict] = []
        for result in results:
            if result.get("execute_method"):
                _collect_methods(result["execute_method"], all_methods)

        # Build the combined string from all method entries
        method_lines = []
        for m in all_methods:
            method_lines.append(
                f"[{m['class']}] {m['method']}\n{m['source_code']}"
            )
        combined_text = "\n".join(method_lines)

        # Estimate token size
        token_count = _estimate_tokens(combined_text)

        output = {
            "methods": all_methods,
            "combined_source": combined_text,
            "token_count": token_count,
        }
        return json.dumps(output, indent=2, ensure_ascii=False)
