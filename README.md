# XML Command Analyzer

A Python CLI tool that parses XML command definitions, matches user queries against them, and traces Java source code execution paths — extracting the `execute` method and all downstream method dependencies with their full source code.

## How It Works

1. **Parse XML** — Scans a directory for XML files containing `<command>` elements with `<name>` and `<impl-class>` children.
2. **Query Matching** — Tokenizes the user query, removes stop words, and matches keywords against command names and class names (including camelCase splitting).
3. **Java Source Analysis** — For each matched command, locates the Java source file, extracts the `execute` method, and recursively traces all downstream method calls across classes.
4. **Caching** — Stores parsed data in a local SQLite database. Subsequent runs skip parsing entirely unless source files have changed (detected via SHA-256 hashing).

## Installation

### 1. Create a virtual environment

```bash
python -m venv venv
```

### 2. Activate the virtual environment

**Windows (cmd):**
```bash
venv\Scripts\activate
```

**Windows (PowerShell):**
```bash
venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

The only external dependency is `javalang` (pure Python Java parser).

### Deactivate when done

```bash
deactivate
```

## Usage

```
python main.py <query> [options]
```

### Arguments

| Argument | Default | Description |
|---|---|---|
| `query` | *(required)* | Search query to match against command names and impl-class values |
| `--xml-dir` | `./xml` | Directory containing XML command definition files |
| `--java-src` | `./java-src` | Root directory of Java source files |
| `--output` | `analysis_output.json` | Output JSON file path |
| `--max-depth` | `10` | Max recursion depth for downstream call tracing |
| `--db-path` | `xmlparser_cache.db` | SQLite cache path (use `:memory:` for no persistence) |
| `--verbose, -v` | off | Enable debug logging |

### Examples

```bash
# Basic query
python main.py "remove beneficiary"

# Specify Java source root
python main.py "payout" --xml-dir ./xml --java-src C:/projects/src/main/java

# Limit recursion depth and enable verbose logging
python main.py "benificiary" --max-depth 5 --verbose

# Use in-memory cache (no persistence)
python main.py "remove" --db-path :memory:
```

## LangChain Agent Usage

The tool can be used as a LangChain tool within an AI agent:

```python
from tool import CommandAnalyzerTool

# Create the tool with custom paths
tool = CommandAnalyzerTool(
    xml_dir="./xml",
    java_src="/path/to/java/src",
    db_path="xmlparser_cache.db",
    max_depth=10,
)

# Use directly
result = tool.run("remove beneficiary")

# Or add to a LangChain agent
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOpenAI(model="gpt-4")
tools = [tool]
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant that analyzes Java command implementations."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])
agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)
executor.invoke({"input": "Show me how the remove beneficiary command works"})
```

### Python API

You can also use the analyzer directly without LangChain:

```python
from analyzer import run_analysis

results = run_analysis(
    query="remove beneficiary",
    xml_dir="./xml",
    java_src="/path/to/java/src",
)
# results is a list of dicts with command analysis data
```

## XML Format

The tool expects XML files with `<command>` elements:

```xml
<commands>
    <command>
        <name>benificiary_remove</name>
        <impl-class>sa.gov.pension.business.command.BenificiaryRemove</impl-class>
    </command>
</commands>
```

## Output

Results are written to both the console and a JSON file.

### Console Output

```
================================================================================
  Analysis Results: 1 command(s) matched
================================================================================

[1] Command : benificiary_remove
    Impl Class : sa.gov.pension.business.command.BenificiaryRemove
    Java File  : src/sa/gov/pension/business/command/BenificiaryRemove.java

    ------------------------------------------------------------
    [sa.gov.pension.business.command.BenificiaryRemove]
      public void execute(String beneficiaryId) throws Exception
      Lines 9-13 (5 lines)
      Downstream calls (3 resolved):
        [sa.gov.pension.business.command.BenificiaryRemove]
          private void validateInput(String id)
          Lines 15-19 (5 lines)
        [sa.gov.pension.business.service.BeneficiaryService]
          public void removeBeneficiary(String beneficiaryId)
          Lines 5-8 (4 lines)
          ...
```

### JSON Output

```json
[
  {
    "command_name": "benificiary_remove",
    "impl_class": "sa.gov.pension.business.command.BenificiaryRemove",
    "java_file_path": "...",
    "execute_method": {
      "class": "sa.gov.pension.business.command.BenificiaryRemove",
      "method": "execute",
      "signature": "public void execute(String beneficiaryId) throws Exception",
      "source_code": "...",
      "start_line": 9,
      "end_line": 13,
      "downstream_calls": [
        {
          "expression": "validateInput",
          "resolved_class": "sa.gov.pension.business.command.BenificiaryRemove",
          "resolved_method": { "..." }
        }
      ]
    }
  }
]
```

## Project Structure

```
XMLParser/
├── main.py                  # CLI entry point and orchestration
├── analyzer.py              # Core pipeline function (shared by CLI and LangChain tool)
├── tool.py                  # LangChain BaseTool wrapper
├── models.py                # Dataclasses (AppConfig, CommandEntry, MethodInfo, etc.)
├── db.py                    # SQLite schema initialization and file hashing
├── xml_parser.py            # XML file parsing with cache support
├── query_engine.py          # Query tokenization, stop word removal, keyword matching
├── java_source_resolver.py  # FQN-to-file-path resolution
├── java_analyzer.py         # Method extraction, AST walking, recursive call tracing
├── output_formatter.py      # Console and JSON output formatting
├── stop_words.py            # Built-in English stop word list
├── requirements.txt         # Dependencies (javalang, langchain-core)
└── xml/                     # Place XML command definition files here
```

## SQLite Cache

The tool persists parsed data to a local SQLite file (`xmlparser_cache.db` by default) with four tables:

- **commands** — XML-extracted command entries
- **java_classes** — Java source content with SHA-256 file hash for staleness detection
- **methods** — Extracted method metadata and source code
- **method_invocations** — Downstream call graph edges

On subsequent runs, the tool loads from cache and skips all XML and Java parsing. If a Java source file changes on disk, the cache automatically invalidates and re-parses only that file.
