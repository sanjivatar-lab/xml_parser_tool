"""Resolve fully-qualified Java class names to source file paths."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_java_file(fqn: str, java_source_root: str) -> Path | None:
    """Convert a fully-qualified Java class name to a .java file path.

    Example:
        fqn = "sa.gov.pension.business.command.BenificiaryRemove"
        java_source_root = "C:/projects/src/main/java"
        -> Path(".../sa/gov/pension/business/command/BenificiaryRemove.java")

    Also handles inner classes by walking backwards through FQN segments.
    """
    root = Path(java_source_root)
    if not root.is_dir():
        logger.error("Java source root directory not found: %s", java_source_root)
        return None

    # Direct resolution: replace dots with path separators
    relative = fqn.replace(".", "/") + ".java"
    full_path = root / relative
    if full_path.is_file():
        return full_path

    # Inner class fallback: try progressively shorter paths
    # e.g., "com.example.Outer.Inner" -> try "com/example/Outer.java"
    parts = fqn.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = root / ("/".join(parts[:i]) + ".java")
        if candidate.is_file():
            logger.info("Resolved %s as inner class in %s", fqn, candidate)
            return candidate

    logger.warning(
        "Java source file not found for: %s (expected %s)", fqn, full_path
    )
    return None


def read_java_source(file_path: Path) -> str:
    """Read a Java source file and return its content."""
    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.error("Failed to read Java file %s: %s", file_path, e)
        return ""
