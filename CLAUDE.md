# CLAUDE.md — XML Command Analyzer

## Project Overview
Python CLI tool and LangChain tool that parses XML command definitions, matches user queries, resolves Java source files, extracts `execute` methods, and recursively traces all downstream method dependencies with full source code.

## Tech Stack
- Python 3.10+
- `javalang` — Java AST parsing (pure Python)
- `langchain-core` — LangChain BaseTool integration
- SQLite — caching parsed data with SHA-256 staleness detection
- No NLTK — stop words are a built-in frozenset

## Project Structure
```
main.py                  — CLI entry point (argparse)
analyzer.py              — Core pipeline: run_analysis() returns list[dict]
tool.py                  — LangChain BaseTool wrapper (CommandAnalyzerTool)
models.py                — Dataclasses: AppConfig, CommandEntry, MethodInfo, MethodCall, AnalysisResult
db.py                    — SQLite schema init (init_db) + file_hash utility
xml_parser.py            — XML parsing with cache support, handles malformed XML
query_engine.py          — Tokenization, stop word removal, keyword matching with CamelCase splitting
java_source_resolver.py  — FQN-to-file-path resolution (handles inner classes)
java_analyzer.py         — Method extraction, AST walking, recursive call tracing (~680 lines)
output_formatter.py      — Console + JSON output; public dict converters (result_to_dict, method_to_dict, call_to_dict)
stop_words.py            — Built-in English stop word frozenset (~180 words)
```

## Key Architecture Decisions
- `analyzer.py` contains the shared pipeline used by both CLI (`main.py`) and LangChain tool (`tool.py`)
- SQLite caching uses direct `sqlite3.Connection` passing — no wrapper class
- Java method extraction uses brace-counting (not AST end positions) to handle strings, chars, and comments correctly
- Qualifier resolution: unqualified → same class, `this.` → same class, field types → import resolution
- `javalang` returns empty string `''` for unqualified method calls (not `None`) — use `if not qualifier` checks

## Running
```bash
# CLI
python main.py "remove beneficiary" --xml-dir ./xml --java-src ./test-java-src

# Python API
from analyzer import run_analysis
results = run_analysis("remove beneficiary", xml_dir="./xml", java_src="./test-java-src")

# LangChain tool
from tool import CommandAnalyzerTool
tool = CommandAnalyzerTool(xml_dir="./xml", java_src="./test-java-src")
result = tool.run("remove beneficiary")
```

## Virtual Environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows cmd
pip install -r requirements.txt
```

## Common Patterns
- All modules accept `conn: sqlite3.Connection | None = None` for optional caching
- Cache tables: `commands`, `java_classes`, `methods`, `method_invocations`
- File staleness detected via SHA-256 hash comparison in `java_analyzer.py`
- XML parser has a fallback (`_parse_xml_file_wrapped`) for files with multiple top-level `<command>` elements
- Max recursion depth for call tracing defaults to 10 (`--max-depth`)

## Testing
Sample data lives in `xml/commands.xml` and `test-java-src/` with two test Java classes:
- `BenificiaryRemove.java` — has an `execute` method calling `validateInput` and `beneficiaryService.removeBeneficiary`
- `BeneficiaryService.java` — downstream service class
