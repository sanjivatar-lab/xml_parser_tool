# CONTEXT.md — Session Context for XML Command Analyzer

## What This Project Does
A Python tool that parses XML command definition files (extracting `<name>` and `<impl-class>`), takes a natural language user query, matches it against commands, resolves Java source files, extracts the `execute` method, and recursively traces all downstream method calls with full source code. Works as a CLI, Python API, and LangChain AI agent tool.

## Repository
- **GitHub**: https://github.com/sanjivatar-lab/xml_parser_tool
- **Local path**: `c:\Code\XMLParser`
- **Branch**: `main`

## Tech Stack
- Python 3.10+ with virtual environment (`venv/`)
- `javalang>=0.13.0` — Java AST parsing (pure Python)
- `langchain-core>=0.3.0` — LangChain BaseTool integration
- SQLite — caching with SHA-256 file staleness detection
- No NLTK — stop words are a built-in frozenset (~180 words)

## File-by-File Summary

| File | Purpose |
|---|---|
| `main.py` | CLI entry point (argparse). Calls `run_analysis()` from `analyzer.py`, then prints console output and writes JSON via `output_formatter.py`. |
| `analyzer.py` | Core shared pipeline. `run_analysis(query, xml_dir, java_src, db_path, max_depth) -> list[dict]`. Used by both CLI and LangChain tool. Opens SQLite, parses XML, searches, analyzes, returns dicts. |
| `tool.py` | LangChain `BaseTool` wrapper (`CommandAnalyzerTool`). Calls `run_analysis()`, then flattens all resolved methods into a list of `{class, method, source_code}` entries, builds a combined source string, estimates token count (~4 chars/token), and returns JSON with `methods`, `combined_source`, and `token_count`. |
| `models.py` | Dataclasses: `AppConfig`, `CommandEntry`, `MethodCall`, `MethodInfo`, `AnalysisResult`. |
| `db.py` | SQLite schema init (`init_db()`) + `file_hash()` utility. 4 tables: `commands`, `java_classes`, `methods`, `method_invocations`. |
| `xml_parser.py` | Parses XML files for `<command>` elements. Cache-aware (checks SQLite first). Fallback `_parse_xml_file_wrapped()` for malformed XML with multiple top-level elements. |
| `query_engine.py` | Tokenizes query, removes stop words, matches keywords against command names and impl-class values (including CamelCase splitting). |
| `java_source_resolver.py` | Converts fully-qualified class name to file path. Handles inner classes by walking backwards. |
| `java_analyzer.py` | ~680 lines. Method extraction via brace-counting (handles strings, chars, comments). Recursive downstream call tracing with cycle detection. SQLite cache with staleness detection. Key functions: `analyze_command()`, `_find_and_extract_method()`, `_extract_source_by_braces()`. |
| `output_formatter.py` | Console + JSON output. Public converters: `result_to_dict()`, `method_to_dict()`, `call_to_dict()`. Dict-based output: `print_console_from_dicts()`, `write_json_from_dicts()`. |
| `stop_words.py` | Built-in English stop word frozenset. |
| `requirements.txt` | `javalang>=0.13.0`, `langchain-core>=0.3.0` |
| `CLAUDE.md` | Project instructions for Claude Code. |

## Three Ways to Use

```bash
# 1. CLI
python main.py "remove beneficiary" --xml-dir ./xml --java-src ./test-java-src

# 2. Python API
from analyzer import run_analysis
results = run_analysis("remove beneficiary", xml_dir="./xml", java_src="./test-java-src")

# 3. LangChain tool
from tool import CommandAnalyzerTool
tool = CommandAnalyzerTool(xml_dir="./xml", java_src="./test-java-src")
result = tool.run("remove beneficiary")
```

## Tool Output Format (LangChain `CommandAnalyzerTool`)
The tool returns a JSON string with:
```json
{
  "methods": [
    {"class": "sa.gov.pension.business.command.BenificiaryRemove", "method": "execute", "source_code": "..."},
    {"class": "sa.gov.pension.business.command.BenificiaryRemove", "method": "validateInput", "source_code": "..."},
    {"class": "sa.gov.pension.business.service.BeneficiaryService", "method": "removeBeneficiary", "source_code": "..."}
  ],
  "combined_source": "[full.Class] execute\n...\n[full.Class] validateInput\n...",
  "token_count": 342
}
```

## Key Architecture Decisions
1. **`analyzer.py` is the shared pipeline** — both `main.py` (CLI) and `tool.py` (LangChain) call `run_analysis()`.
2. **SQLite caching uses direct `sqlite3.Connection` passing** — no wrapper class (user explicitly rejected a CacheDB wrapper).
3. **Java method extraction uses brace-counting** (not AST end positions) to correctly handle strings, char literals, and comments.
4. **Qualifier resolution**: unqualified → same class, `this.` → same class, field types → import resolution, same-package assumption as last resort.
5. **`javalang` quirk**: returns empty string `''` for unqualified method calls (not `None`) — always use `if not qualifier` checks.

## SQLite Cache Tables
- `commands` — XML-extracted command entries (name, impl_class, source_file)
- `java_classes` — Java source content with SHA-256 file hash for staleness
- `methods` — Extracted method metadata and source code
- `method_invocations` — Downstream call graph edges

## Test Data
- `xml/commands.xml` — 2 sample commands (`biner_remove`, `benificiary_remove`)
- `test-java-src/` — 2 test Java classes:
  - `sa/gov/pension/business/command/BenificiaryRemove.java` — has `execute` method calling `validateInput`, `beneficiaryService.removeBeneficiary`, `logAction`
  - `sa/gov/pension/business/service/BeneficiaryService.java` — downstream service with `removeBeneficiary`, `checkPermissions`, `deleteFromDatabase`

## Known Issues & Quirks
- `javalang` returns `''` (empty string) for unqualified method calls, not `None`
- The `=0.13.0` file in the project root is a stale artifact (can be deleted)
- Token estimation is a rough heuristic (~4 chars per token), not an actual tokenizer

## Virtual Environment Setup
```bash
python -m venv venv
venv\Scripts\activate        # Windows cmd
venv\Scripts\Activate.ps1    # Windows PowerShell
source venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

## Git Config
- Username: `sanjivatar-lab`
- Email: `sanjivatar-lab@users.noreply.github.com`
- Remote: `https://github.com/sanjivatar-lab/xml_parser_tool.git`
