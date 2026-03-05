"""Core analysis pipeline — shared by CLI and LangChain tool."""

from __future__ import annotations

import logging
import sqlite3

from db import init_db
from java_analyzer import analyze_command
from models import AppConfig
from output_formatter import result_to_dict
from query_engine import search
from xml_parser import parse_all_xml

logger = logging.getLogger(__name__)


def run_analysis(
    query: str,
    xml_dir: str = "./xml",
    java_src: str = "./java-src",
    db_path: str = "xmlparser_cache.db",
    max_depth: int = 10,
) -> list[dict]:
    """Run the full analysis pipeline and return results as a list of dicts.

    Parameters
    ----------
    query : str
        Natural language search query (e.g. "remove beneficiary").
    xml_dir : str
        Directory containing XML command definition files.
    java_src : str
        Root directory of Java source files.
    db_path : str
        SQLite database path for caching.
    max_depth : int
        Max recursion depth for downstream call tracing.

    Returns
    -------
    list[dict]
        JSON-serializable list of analysis results.
    """
    config = AppConfig(
        xml_dir=xml_dir,
        java_source_root=java_src,
        query=query,
        output_json="",  # not used in this path
        max_depth=max_depth,
        db_path=db_path,
    )

    conn = init_db(config.db_path)
    logger.info("Cache database opened: %s", config.db_path)

    try:
        # Step 1: Parse all XML files (cache-aware)
        commands = parse_all_xml(config.xml_dir, conn=conn)
        if not commands:
            logger.warning("No commands found in XML files.")
            return []

        # Step 2: Search commands by query keywords
        matched = search(commands, config.query)
        if not matched:
            logger.info("No commands matched the query: '%s'", config.query)
            return []

        # Step 3: Analyze each matched command (cache-aware)
        results = []
        for cmd in matched:
            logger.info("Analyzing: %s -> %s", cmd.name, cmd.impl_class)
            result = analyze_command(cmd, config, conn=conn)
            results.append(result)

        # Step 4: Convert to dicts
        return [result_to_dict(r) for r in results]

    finally:
        conn.close()
