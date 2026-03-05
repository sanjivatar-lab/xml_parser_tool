"""XML Command Analyzer — CLI entry point.

Parses XML command definitions, matches user queries, and traces Java
source code execution paths including all downstream method dependencies.

Usage:
    python main.py "remove beneficiary" --xml-dir ./xml --java-src /path/to/src
"""

import argparse
import logging
import sys

from analyzer import run_analysis
from output_formatter import print_console_from_dicts, write_json_from_dicts


def _configure_logging(verbose: bool) -> None:
    """Set up logging with appropriate level and format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    """Run the XML Command Analyzer pipeline."""
    parser = argparse.ArgumentParser(
        description="Analyze XML command definitions and trace Java source execution paths.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python main.py "remove beneficiary"\n'
            '  python main.py "payout" --xml-dir ./xml --java-src C:/projects/src/main/java\n'
            '  python main.py "benificiary" --max-depth 5 --verbose\n'
            '  python main.py "remove" --db-path cache.db  # persist cache to file'
        ),
    )
    parser.add_argument(
        "query",
        help="Search query to match against command names and impl-class values",
    )
    parser.add_argument(
        "--xml-dir",
        default="./xml",
        help="Directory containing XML command definition files (default: ./xml)",
    )
    parser.add_argument(
        "--java-src",
        default="./java-src",
        help="Root directory of Java source files (default: ./java-src)",
    )
    parser.add_argument(
        "--output",
        default="analysis_output.json",
        help="Output JSON file path (default: analysis_output.json)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Max recursion depth for downstream call tracing (default: 10)",
    )
    parser.add_argument(
        "--db-path",
        default="xmlparser_cache.db",
        help="SQLite database path for caching (default: xmlparser_cache.db, use :memory: for in-memory only)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()
    _configure_logging(args.verbose)

    results = run_analysis(
        query=args.query,
        xml_dir=args.xml_dir,
        java_src=args.java_src,
        db_path=args.db_path,
        max_depth=args.max_depth,
    )

    if not results:
        print(f"No commands matched the query: '{args.query}'")
        return 0

    print_console_from_dicts(results)
    write_json_from_dicts(results, args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
