"""Format analysis results for console display and JSON file output."""

import json
import logging
from pathlib import Path

from models import AnalysisResult, MethodCall, MethodInfo

logger = logging.getLogger(__name__)

SEPARATOR = "=" * 80
THIN_SEP = "-" * 60


def write_results(results: list[AnalysisResult], output_path: str) -> None:
    """Write results to both console and a JSON file."""
    _print_console(results)
    _write_json(results, output_path)


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------


def _print_console(results: list[AnalysisResult]) -> None:
    """Pretty-print analysis results to stdout."""
    if not results:
        print("\nNo matching commands found.")
        return

    print(f"\n{SEPARATOR}")
    print(f"  Analysis Results: {len(results)} command(s) matched")
    print(SEPARATOR)

    for idx, result in enumerate(results, 1):
        print(f"\n[{idx}] Command : {result.command_name}")
        print(f"    Impl Class : {result.impl_class}")
        print(f"    Java File  : {result.java_file_path or 'NOT FOUND'}")

        if result.execute_method:
            print(f"\n    {THIN_SEP}")
            _print_method_tree(result.execute_method, indent=4)
        else:
            print("    [execute method not found]")

    print(f"\n{SEPARATOR}")
    print(f"  Total resolved methods: {sum(len(r.all_resolved_methods) for r in results)}")
    print(SEPARATOR)


def _print_method_tree(method: MethodInfo, indent: int) -> None:
    """Recursively print a method and its downstream calls."""
    prefix = " " * indent
    line_count = method.end_line - method.start_line + 1

    print(f"{prefix}[{method.class_fqn}]")
    print(f"{prefix}  {method.signature}")
    print(f"{prefix}  Lines {method.start_line}-{method.end_line} ({line_count} lines)")

    if method.downstream_calls:
        resolved = [c for c in method.downstream_calls if c.resolved_method]
        unresolved = [c for c in method.downstream_calls if not c.resolved_method]

        if resolved:
            print(f"{prefix}  Downstream calls ({len(resolved)} resolved):")
            for call in resolved:
                assert call.resolved_method is not None
                _print_method_tree(call.resolved_method, indent + 4)

        if unresolved:
            print(f"{prefix}  Unresolved calls ({len(unresolved)}):")
            for call in unresolved:
                target = call.resolved_class_fqn or "unknown"
                print(f"{prefix}    -> {call.target_expression} [{target}]")


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


def _write_json(results: list[AnalysisResult], output_path: str) -> None:
    """Serialize results to a JSON file."""
    json_data = [result_to_dict(r) for r in results]

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    logger.info("JSON output written to %s", output)
    print(f"\nJSON output saved to: {output}")


def result_to_dict(result: AnalysisResult) -> dict:
    """Convert an AnalysisResult to a JSON-serializable dict."""
    return {
        "command_name": result.command_name,
        "impl_class": result.impl_class,
        "java_file_path": result.java_file_path,
        "execute_method": (
            method_to_dict(result.execute_method)
            if result.execute_method
            else None
        ),
    }


def method_to_dict(method: MethodInfo) -> dict:
    """Recursively convert a MethodInfo tree to a dict."""
    return {
        "class": method.class_fqn,
        "method": method.method_name,
        "signature": method.signature,
        "source_code": method.source_code,
        "start_line": method.start_line,
        "end_line": method.end_line,
        "downstream_calls": [call_to_dict(c) for c in method.downstream_calls],
    }


def call_to_dict(call: MethodCall) -> dict:
    """Convert a MethodCall to a dict."""
    return {
        "expression": call.target_expression,
        "resolved_class": call.resolved_class_fqn,
        "resolved_method": (
            method_to_dict(call.resolved_method)
            if call.resolved_method
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Dict-based output (used by CLI via analyzer.py)
# ---------------------------------------------------------------------------


def print_console_from_dicts(results: list[dict]) -> None:
    """Pretty-print analysis results (as dicts) to stdout."""
    if not results:
        print("\nNo matching commands found.")
        return

    print(f"\n{SEPARATOR}")
    print(f"  Analysis Results: {len(results)} command(s) matched")
    print(SEPARATOR)

    for idx, r in enumerate(results, 1):
        print(f"\n[{idx}] Command : {r['command_name']}")
        print(f"    Impl Class : {r['impl_class']}")
        print(f"    Java File  : {r.get('java_file_path') or 'NOT FOUND'}")

        if r.get("execute_method"):
            print(f"\n    {THIN_SEP}")
            _print_method_dict(r["execute_method"], indent=4)
        else:
            print("    [execute method not found]")

    print(f"\n{SEPARATOR}")


def _print_method_dict(method: dict, indent: int) -> None:
    """Recursively print a method dict and its downstream calls."""
    prefix = " " * indent
    line_count = method["end_line"] - method["start_line"] + 1

    print(f"{prefix}[{method['class']}]")
    print(f"{prefix}  {method['signature']}")
    print(f"{prefix}  Lines {method['start_line']}-{method['end_line']} ({line_count} lines)")

    calls = method.get("downstream_calls", [])
    if calls:
        resolved = [c for c in calls if c.get("resolved_method")]
        unresolved = [c for c in calls if not c.get("resolved_method")]

        if resolved:
            print(f"{prefix}  Downstream calls ({len(resolved)} resolved):")
            for call in resolved:
                _print_method_dict(call["resolved_method"], indent + 4)

        if unresolved:
            print(f"{prefix}  Unresolved calls ({len(unresolved)}):")
            for call in unresolved:
                target = call.get("resolved_class") or "unknown"
                print(f"{prefix}    -> {call['expression']} [{target}]")


def write_json_from_dicts(results: list[dict], output_path: str) -> None:
    """Write pre-built result dicts to a JSON file."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info("JSON output written to %s", output)
    print(f"\nJSON output saved to: {output}")
