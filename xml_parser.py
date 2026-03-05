"""Parse XML command definition files and extract name/impl-class pairs."""

from __future__ import annotations

import logging
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from models import CommandEntry

logger = logging.getLogger(__name__)


def parse_all_xml(
    xml_dir: str, conn: sqlite3.Connection | None = None
) -> list[CommandEntry]:
    """Scan a directory for .xml files and extract all <command> entries.

    If a database connection is provided and already contains commands,
    returns cached data instead of re-parsing from disk.
    """
    # Check cache first
    if conn is not None:
        row = conn.execute("SELECT COUNT(*) FROM commands").fetchone()
        if row[0] > 0:
            logger.info("Loading commands from cache (skipping XML parsing)")
            rows = conn.execute(
                "SELECT name, impl_class, source_file FROM commands"
            ).fetchall()
            commands = [
                CommandEntry(name=r[0], impl_class=r[1], source_file=r[2])
                for r in rows
            ]
            logger.info("Loaded %d commands from cache", len(commands))
            return commands

    xml_path = Path(xml_dir)
    if not xml_path.is_dir():
        logger.error("XML directory not found: %s", xml_dir)
        return []

    commands: list[CommandEntry] = []
    xml_files = list(xml_path.glob("*.xml"))

    if not xml_files:
        logger.warning("No XML files found in %s", xml_dir)
        return []

    for xml_file in xml_files:
        commands.extend(_parse_xml_file(xml_file))

    logger.info(
        "Parsed %d commands from %d XML files", len(commands), len(xml_files)
    )

    # Populate cache
    if conn is not None and commands:
        conn.execute("DELETE FROM commands")
        conn.executemany(
            "INSERT OR REPLACE INTO commands (name, impl_class, source_file) VALUES (?, ?, ?)",
            [(c.name, c.impl_class, c.source_file) for c in commands],
        )
        conn.commit()
        logger.info("Cached %d commands in database", len(commands))

    return commands


def _parse_xml_file(file_path: Path) -> list[CommandEntry]:
    """Parse a single XML file and extract <command> entries.

    Handles files with or without a root wrapper element.
    """
    entries: list[CommandEntry] = []

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except ET.ParseError as e:
        logger.warning("Failed to parse XML file %s: %s", file_path, e)
        # Try wrapping content in a root element in case the file has
        # multiple top-level <command> elements (not valid XML by itself).
        return _parse_xml_file_wrapped(file_path)

    # Find all <command> elements at any depth
    for cmd_elem in root.iter("command"):
        name = cmd_elem.findtext("name")
        impl_class = cmd_elem.findtext("impl-class")

        if not name or not impl_class:
            logger.warning(
                "Skipping malformed <command> in %s: name=%r, impl-class=%r",
                file_path,
                name,
                impl_class,
            )
            continue

        entries.append(
            CommandEntry(
                name=name.strip(),
                impl_class=impl_class.strip(),
                source_file=str(file_path),
            )
        )

    logger.debug("Extracted %d commands from %s", len(entries), file_path)
    return entries


def _parse_xml_file_wrapped(file_path: Path) -> list[CommandEntry]:
    """Fallback parser: wrap file content in a <root> element and retry.

    This handles XML files that have multiple top-level <command> elements
    without a single root element (technically not well-formed XML).
    """
    try:
        raw = file_path.read_text(encoding="utf-8")
        wrapped = f"<root>{raw}</root>"
        root = ET.fromstring(wrapped)
    except (ET.ParseError, OSError) as e:
        logger.error("Could not parse XML file %s even with wrapper: %s", file_path, e)
        return []

    entries: list[CommandEntry] = []
    for cmd_elem in root.iter("command"):
        name = cmd_elem.findtext("name")
        impl_class = cmd_elem.findtext("impl-class")

        if not name or not impl_class:
            continue

        entries.append(
            CommandEntry(
                name=name.strip(),
                impl_class=impl_class.strip(),
                source_file=str(file_path),
            )
        )

    return entries
