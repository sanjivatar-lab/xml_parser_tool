"""Tokenize user queries, remove stop words, and match against command entries."""

import logging
import re

from models import CommandEntry
from stop_words import STOP_WORDS

logger = logging.getLogger(__name__)


def tokenize_and_filter(query: str) -> list[str]:
    """Tokenize a query string into keywords, removing stop words.

    Steps:
        1. Lowercase the query
        2. Split on non-alphanumeric characters
        3. Remove empty tokens and stop words
    """
    tokens = re.split(r"[^a-z0-9]+", query.lower())
    keywords = [t for t in tokens if t and t not in STOP_WORDS]
    logger.debug("Query '%s' -> keywords: %s", query, keywords)
    return keywords


def search(commands: list[CommandEntry], query: str) -> list[CommandEntry]:
    """Find commands whose name or impl_class match any query keyword."""
    keywords = tokenize_and_filter(query)
    if not keywords:
        logger.warning("No keywords remaining after stop word removal for query: '%s'", query)
        return []

    matched: list[CommandEntry] = []
    for cmd in commands:
        searchable = _build_searchable_tokens(cmd)
        if any(kw in searchable for kw in keywords):
            matched.append(cmd)

    logger.info("Matched %d commands for query '%s'", len(matched), query)
    return matched


def _build_searchable_tokens(cmd: CommandEntry) -> set[str]:
    """Build a set of searchable tokens from a CommandEntry.

    Extracts tokens from:
        - The command name (split on underscores/hyphens)
        - The impl-class package segments (split on dots)
        - The class name with camelCase splitting
    """
    tokens: set[str] = set()

    # From name (e.g., "benificiary_remove" -> {"benificiary", "remove"})
    tokens.update(re.split(r"[^a-z0-9]+", cmd.name.lower()))

    # From impl_class package segments
    parts = cmd.impl_class.lower().split(".")
    tokens.update(parts)

    # CamelCase split of the class name (last segment)
    class_name = cmd.impl_class.rsplit(".", 1)[-1]
    camel_parts = re.sub(r"([A-Z])", r" \1", class_name).lower().split()
    tokens.update(camel_parts)

    tokens.discard("")
    return tokens
