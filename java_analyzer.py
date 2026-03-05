"""Core analysis engine: extract Java methods and trace downstream call dependencies.

Uses the `javalang` library for AST parsing with a regex fallback for files
that fail to parse (e.g., newer Java syntax not supported by javalang).

Supports an optional sqlite3 connection to cache parsed data and avoid
re-parsing source files on repeated runs.
"""

from __future__ import annotations

import logging
import re
import sqlite3

import javalang
import javalang.tree as jtree

from db import file_hash
from java_source_resolver import read_java_source, resolve_java_file
from models import AnalysisResult, AppConfig, CommandEntry, MethodCall, MethodInfo

logger = logging.getLogger(__name__)

# In-process AST cache (javalang trees are not serializable to SQLite,
# so we still keep a per-run dict for parsed ASTs).
_ast_cache: dict[str, tuple[jtree.CompilationUnit | None, str]] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_command(
    cmd: CommandEntry, config: AppConfig, conn: sqlite3.Connection | None = None
) -> AnalysisResult:
    """Full analysis pipeline for one matched command.

    Resolves the Java source file, locates the ``execute`` method, and
    recursively traces all downstream method calls.
    """
    java_path = resolve_java_file(cmd.impl_class, config.java_source_root)
    result = AnalysisResult(
        command_name=cmd.name,
        impl_class=cmd.impl_class,
        java_file_path=str(java_path) if java_path else "",
    )

    if not java_path:
        return result

    visited: set[str] = set()
    execute = _find_and_extract_method(
        fqn=cmd.impl_class,
        method_name="execute",
        java_source_root=config.java_source_root,
        visited=visited,
        depth=0,
        max_depth=config.max_depth,
        conn=conn,
    )
    result.execute_method = execute
    if execute:
        result.all_resolved_methods = _collect_all_methods(execute)
    return result


# ---------------------------------------------------------------------------
# Recursive method extraction
# ---------------------------------------------------------------------------


def _find_and_extract_method(
    fqn: str,
    method_name: str,
    java_source_root: str,
    visited: set[str],
    depth: int,
    max_depth: int,
    conn: sqlite3.Connection | None = None,
) -> MethodInfo | None:
    """Find a method in a class, extract source, and recursively trace calls."""
    visit_key = f"{fqn}#{method_name}"
    if visit_key in visited:
        logger.debug("Already visited %s, skipping", visit_key)
        return None
    if depth > max_depth:
        logger.warning("Max recursion depth (%d) reached at %s", max_depth, visit_key)
        return None

    visited.add(visit_key)

    # --- Check SQLite cache for a non-stale method ---
    if conn is not None:
        java_path = resolve_java_file(fqn, java_source_root)
        file_path_str = str(java_path) if java_path else ""

        if file_path_str and not _is_class_stale(conn, fqn, file_path_str):
            cached_method = _get_cached_method(conn, fqn, method_name)
            if cached_method is not None:
                logger.debug("Cache hit for %s", visit_key)
                # Rebuild downstream calls from cached invocations
                rows = conn.execute(
                    "SELECT target_expression, resolved_class, resolved_method "
                    "FROM method_invocations WHERE caller_class = ? AND caller_method = ?",
                    (fqn, method_name),
                ).fetchall()
                for target_expr, resolved_cls, resolved_meth in rows:
                    call = MethodCall(
                        target_expression=target_expr,
                        resolved_class_fqn=resolved_cls,
                    )
                    if resolved_cls and resolved_meth:
                        call.resolved_method = _find_and_extract_method(
                            fqn=resolved_cls,
                            method_name=resolved_meth,
                            java_source_root=java_source_root,
                            visited=visited,
                            depth=depth + 1,
                            max_depth=max_depth,
                            conn=conn,
                        )
                    cached_method.downstream_calls.append(call)
                return cached_method
        elif file_path_str and java_path:
            # Class is stale — invalidate all cached data for it
            _invalidate_class(conn, fqn)

    # --- Parse from source ---
    tree, raw_source = _get_parsed_tree(fqn, java_source_root, conn)
    if raw_source == "":
        return None

    source_lines = raw_source.splitlines(keepends=True)

    # Try javalang AST first, fall back to regex
    method_info = _extract_method_via_ast(
        tree, fqn, method_name, source_lines, raw_source
    )
    if method_info is None:
        method_info = _extract_method_via_regex(fqn, method_name, raw_source)
    if method_info is None:
        logger.debug("Method %s not found in %s", method_name, fqn)
        return method_info

    # Find and resolve downstream invocations
    invocations = _find_invocations_in_source(method_info.source_code)
    if tree is not None:
        invocations = _find_invocations_via_ast(tree, method_name) or invocations

    for inv_qualifier, inv_method in invocations:
        target_fqn = _resolve_qualifier(inv_qualifier, fqn, tree, java_source_root)
        expr = f"{inv_qualifier}.{inv_method}" if inv_qualifier else inv_method

        call = MethodCall(
            target_expression=expr,
            resolved_class_fqn=target_fqn,
        )

        if target_fqn:
            resolved = _find_and_extract_method(
                fqn=target_fqn,
                method_name=inv_method,
                java_source_root=java_source_root,
                visited=visited,
                depth=depth + 1,
                max_depth=max_depth,
                conn=conn,
            )
            call.resolved_method = resolved

        method_info.downstream_calls.append(call)

    # --- Store in cache ---
    if conn is not None:
        _store_method(conn, method_info)
        _store_invocations(conn, fqn, method_name, method_info.downstream_calls)

    return method_info


# ---------------------------------------------------------------------------
# SQLite cache helpers
# ---------------------------------------------------------------------------


def _is_class_stale(conn: sqlite3.Connection, fqn: str, file_path: str) -> bool:
    """Check if a cached class entry is stale (file changed on disk)."""
    row = conn.execute(
        "SELECT file_hash FROM java_classes WHERE fqn = ?", (fqn,)
    ).fetchone()
    if row is None:
        return True
    return row[0] != file_hash(file_path)


def _get_cached_method(
    conn: sqlite3.Connection, class_fqn: str, method_name: str
) -> MethodInfo | None:
    """Retrieve a cached method (without downstream_calls)."""
    row = conn.execute(
        "SELECT signature, source_code, start_line, end_line FROM methods "
        "WHERE class_fqn = ? AND method_name = ?",
        (class_fqn, method_name),
    ).fetchone()
    if row is None:
        return None
    return MethodInfo(
        class_fqn=class_fqn,
        method_name=method_name,
        signature=row[0],
        source_code=row[1],
        start_line=row[2],
        end_line=row[3],
    )


def _store_method(conn: sqlite3.Connection, method: MethodInfo) -> None:
    """Store a method's metadata in the cache."""
    conn.execute(
        "INSERT OR REPLACE INTO methods "
        "(class_fqn, method_name, signature, source_code, start_line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            method.class_fqn,
            method.method_name,
            method.signature,
            method.source_code,
            method.start_line,
            method.end_line,
        ),
    )
    conn.commit()


def _store_invocations(
    conn: sqlite3.Connection,
    caller_class: str,
    caller_method: str,
    calls: list[MethodCall],
) -> None:
    """Store downstream invocations for a method."""
    conn.execute(
        "DELETE FROM method_invocations WHERE caller_class = ? AND caller_method = ?",
        (caller_class, caller_method),
    )
    conn.executemany(
        "INSERT INTO method_invocations "
        "(caller_class, caller_method, target_expression, resolved_class, resolved_method) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (
                caller_class,
                caller_method,
                c.target_expression,
                c.resolved_class_fqn,
                c.resolved_method.method_name if c.resolved_method else None,
            )
            for c in calls
        ],
    )
    conn.commit()


def _invalidate_class(conn: sqlite3.Connection, fqn: str) -> None:
    """Remove all cached data for a stale class."""
    conn.execute("DELETE FROM java_classes WHERE fqn = ?", (fqn,))
    conn.execute("DELETE FROM methods WHERE class_fqn = ?", (fqn,))
    conn.execute("DELETE FROM method_invocations WHERE caller_class = ?", (fqn,))
    conn.commit()
    logger.info("Invalidated cache for stale class: %s", fqn)


# ---------------------------------------------------------------------------
# AST-based method extraction
# ---------------------------------------------------------------------------


def _get_parsed_tree(
    fqn: str, java_source_root: str, conn: sqlite3.Connection | None = None
) -> tuple[jtree.CompilationUnit | None, str]:
    """Parse a Java file and return (AST, raw_source).

    Uses the in-process AST cache for javalang trees, and optionally reads
    raw source from the SQLite cache to avoid disk I/O.
    """
    java_path = resolve_java_file(fqn, java_source_root)
    if java_path is None:
        return None, ""

    ast_key = str(java_path)
    if ast_key in _ast_cache:
        return _ast_cache[ast_key]

    # Try to get raw source from SQLite cache
    raw_source = ""
    if conn is not None:
        row = conn.execute(
            "SELECT raw_source FROM java_classes WHERE fqn = ?", (fqn,)
        ).fetchone()
        if row is not None and not _is_class_stale(conn, fqn, ast_key):
            raw_source = row[0]
            logger.debug("Loaded source for %s from cache", fqn)

    if not raw_source:
        raw_source = read_java_source(java_path)
        if not raw_source:
            _ast_cache[ast_key] = (None, "")
            return None, ""
        # Store raw source in SQLite cache
        if conn is not None:
            fhash = file_hash(ast_key)
            conn.execute(
                "INSERT OR REPLACE INTO java_classes (fqn, file_path, raw_source, file_hash) "
                "VALUES (?, ?, ?, ?)",
                (fqn, ast_key, raw_source, fhash),
            )
            conn.commit()

    try:
        tree = javalang.parse.parse(raw_source)
    except javalang.parser.JavaSyntaxError as e:
        logger.warning("javalang failed to parse %s: %s (using regex fallback)", java_path, e)
        tree = None
    except Exception as e:
        logger.warning("Unexpected parse error for %s: %s", java_path, e)
        tree = None

    _ast_cache[ast_key] = (tree, raw_source)
    return tree, raw_source


def _extract_method_via_ast(
    tree: jtree.CompilationUnit | None,
    fqn: str,
    method_name: str,
    source_lines: list[str],
    raw_source: str,
) -> MethodInfo | None:
    """Extract a method's source code using the javalang AST."""
    if tree is None:
        return None

    method_node = _find_method_node(tree, fqn, method_name)
    if method_node is None:
        return None

    if method_node.position is None:
        return None

    start_line = method_node.position.line
    signature = _build_signature(method_node)
    start_line_idx, end_line_idx, source_code = _extract_source_by_braces(
        source_lines, start_line - 1
    )

    return MethodInfo(
        class_fqn=fqn,
        method_name=method_name,
        signature=signature,
        source_code=source_code,
        start_line=start_line_idx + 1,
        end_line=end_line_idx + 1,
    )


def _find_method_node(
    tree: jtree.CompilationUnit, fqn: str, method_name: str
) -> jtree.MethodDeclaration | None:
    """Walk the AST to find a MethodDeclaration by name."""
    target_class = fqn.rsplit(".", 1)[-1]

    for path, node in tree.filter(jtree.MethodDeclaration):
        if node.name != method_name:
            continue
        for ancestor in path:
            if isinstance(ancestor, jtree.ClassDeclaration) and ancestor.name == target_class:
                return node
        return node

    return None


def _build_signature(node: jtree.MethodDeclaration) -> str:
    """Build a human-readable method signature string."""
    parts: list[str] = []

    if node.modifiers:
        parts.extend(sorted(node.modifiers))

    if node.return_type:
        parts.append(_type_to_str(node.return_type))
    else:
        parts.append("void")

    params = []
    if node.parameters:
        for p in node.parameters:
            ptype = _type_to_str(p.type) if p.type else "Object"
            params.append(f"{ptype} {p.name}")

    parts.append(f"{node.name}({', '.join(params)})")

    if node.throws:
        throws_str = ", ".join(node.throws)
        parts.append(f"throws {throws_str}")

    return " ".join(parts)


def _type_to_str(type_node: object) -> str:
    """Convert a javalang type node to a string representation."""
    if isinstance(type_node, jtree.ReferenceType):
        name = type_node.name
        if type_node.arguments:
            args = ", ".join(_type_to_str(a.type) for a in type_node.arguments if a.type)
            name += f"<{args}>"
        return name
    if isinstance(type_node, jtree.BasicType):
        name = type_node.name
        if type_node.dimensions:
            name += "[]" * len(type_node.dimensions)
        return name
    return str(type_node)


# ---------------------------------------------------------------------------
# Brace-counting source extraction
# ---------------------------------------------------------------------------


def _extract_source_by_braces(
    source_lines: list[str], start_idx: int
) -> tuple[int, int, str]:
    """Extract a method body by counting braces from a start line.

    Correctly skips braces inside string literals, char literals,
    single-line comments, and block comments.
    """
    brace_depth = 0
    found_open = False
    in_string = False
    in_char = False
    in_block_comment = False
    escape_next = False

    for line_idx in range(start_idx, len(source_lines)):
        line = source_lines[line_idx]
        in_line_comment = False
        i = 0

        while i < len(line):
            ch = line[i]

            if escape_next:
                escape_next = False
                i += 1
                continue

            if ch == "\\" and (in_string or in_char):
                escape_next = True
                i += 1
                continue

            if in_line_comment:
                break

            if in_block_comment:
                if ch == "*" and i + 1 < len(line) and line[i + 1] == "/":
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_string:
                if ch == '"':
                    in_string = False
                i += 1
                continue

            if in_char:
                if ch == "'":
                    in_char = False
                i += 1
                continue

            if ch == "/" and i + 1 < len(line):
                if line[i + 1] == "/":
                    in_line_comment = True
                    break
                if line[i + 1] == "*":
                    in_block_comment = True
                    i += 2
                    continue

            if ch == '"':
                in_string = True
                i += 1
                continue
            if ch == "'":
                in_char = True
                i += 1
                continue

            if ch == "{":
                brace_depth += 1
                found_open = True
            elif ch == "}":
                brace_depth -= 1
                if found_open and brace_depth == 0:
                    source = "".join(source_lines[start_idx : line_idx + 1])
                    return start_idx, line_idx, source

            i += 1

    logger.warning("Could not find method end brace starting at line %d", start_idx + 1)
    source = "".join(source_lines[start_idx:])
    return start_idx, len(source_lines) - 1, source


# ---------------------------------------------------------------------------
# Regex fallback for method extraction
# ---------------------------------------------------------------------------


def _extract_method_via_regex(
    fqn: str, method_name: str, raw_source: str
) -> MethodInfo | None:
    """Fallback: extract a method using regex + brace counting."""
    pattern = re.compile(
        rf"^\s*(?:(?:public|protected|private)\s+)?"
        rf"(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?"
        rf"(?:[\w<>\[\],\s]+?)\s+{re.escape(method_name)}\s*\(",
        re.MULTILINE,
    )
    match = pattern.search(raw_source)
    if not match:
        return None

    source_lines = raw_source.splitlines(keepends=True)
    start_line = raw_source[: match.start()].count("\n")

    start_idx, end_idx, source_code = _extract_source_by_braces(source_lines, start_line)

    first_line = source_lines[start_line].strip()
    sig_end = first_line.find("{")
    signature = first_line[:sig_end].strip() if sig_end != -1 else first_line

    return MethodInfo(
        class_fqn=fqn,
        method_name=method_name,
        signature=signature,
        source_code=source_code,
        start_line=start_idx + 1,
        end_line=end_idx + 1,
    )


# ---------------------------------------------------------------------------
# Method invocation discovery
# ---------------------------------------------------------------------------


def _find_invocations_via_ast(
    tree: jtree.CompilationUnit, method_name: str
) -> list[tuple[str | None, str]] | None:
    """Extract method invocations from a method's AST subtree."""
    method_node = None
    for _, node in tree.filter(jtree.MethodDeclaration):
        if node.name == method_name:
            method_node = node
            break

    if method_node is None:
        return None

    invocations: list[tuple[str | None, str]] = []
    _walk_for_invocations(method_node, invocations)
    return invocations


def _walk_for_invocations(
    node: object, result: list[tuple[str | None, str]]
) -> None:
    """Recursively walk AST nodes to collect MethodInvocation entries."""
    if isinstance(node, jtree.MethodInvocation):
        qualifier = node.qualifier if hasattr(node, "qualifier") else None
        result.append((qualifier, node.member))

    if not isinstance(node, jtree.Node):
        return

    for attr_name in node.attrs:
        attr = getattr(node, attr_name, None)
        if attr is None:
            continue
        if isinstance(attr, jtree.Node):
            _walk_for_invocations(attr, result)
        elif isinstance(attr, list):
            for item in attr:
                if isinstance(item, jtree.Node):
                    _walk_for_invocations(item, result)


def _find_invocations_in_source(
    source_code: str,
) -> list[tuple[str | None, str]]:
    """Regex fallback: find method invocations in raw source code."""
    pattern = re.compile(r"(?:(\w+)\.)?\b(\w+)\s*\(")
    invocations: list[tuple[str | None, str]] = []
    seen: set[tuple[str | None, str]] = set()

    for match in pattern.finditer(source_code):
        qualifier = match.group(1)
        method = match.group(2)

        if method in {"if", "for", "while", "switch", "catch", "return", "new", "throw", "synchronized"}:
            continue

        key = (qualifier, method)
        if key not in seen:
            seen.add(key)
            invocations.append(key)

    return invocations


# ---------------------------------------------------------------------------
# Qualifier resolution
# ---------------------------------------------------------------------------


def _resolve_qualifier(
    qualifier: str | None,
    current_fqn: str,
    tree: jtree.CompilationUnit | None,
    java_source_root: str,
) -> str | None:
    """Resolve a method call qualifier to a fully-qualified class name."""
    if not qualifier or qualifier == "this":
        return current_fqn

    if qualifier == "super":
        return _resolve_parent_class(current_fqn, tree)

    if tree is None:
        return None

    resolved = _resolve_field_type(qualifier, tree, current_fqn)
    if resolved:
        return resolved

    resolved = _resolve_via_imports(qualifier, tree)
    if resolved:
        if resolve_java_file(resolved, java_source_root):
            return resolved

    package = tree.package.name if tree.package else ""
    if package:
        candidate = f"{package}.{qualifier}"
        if resolve_java_file(candidate, java_source_root):
            return candidate

    return None


def _resolve_parent_class(
    current_fqn: str, tree: jtree.CompilationUnit | None
) -> str | None:
    """Resolve the parent class of the current class."""
    if tree is None:
        return None

    target_class = current_fqn.rsplit(".", 1)[-1]
    for _, node in tree.filter(jtree.ClassDeclaration):
        if node.name == target_class and node.extends:
            parent_name = node.extends.name
            return _resolve_via_imports(parent_name, tree)
    return None


def _resolve_field_type(
    field_name: str, tree: jtree.CompilationUnit, current_fqn: str
) -> str | None:
    """Resolve a field name to its declared type's FQN."""
    target_class = current_fqn.rsplit(".", 1)[-1]

    for _, node in tree.filter(jtree.ClassDeclaration):
        if node.name != target_class:
            continue
        for member in node.body or []:
            if not isinstance(member, jtree.FieldDeclaration):
                continue
            for declarator in member.declarators or []:
                if declarator.name == field_name and member.type:
                    type_name = _type_to_str(member.type)
                    resolved = _resolve_via_imports(type_name, tree)
                    if resolved:
                        return resolved
    return None


def _resolve_via_imports(
    simple_name: str, tree: jtree.CompilationUnit
) -> str | None:
    """Resolve a simple class name to FQN using the file's import statements."""
    if not simple_name or not tree.imports:
        return None

    base_name = simple_name.split("<")[0]
    if not base_name:
        return None

    for imp in tree.imports:
        if imp.path.endswith(f".{base_name}"):
            return imp.path
        if imp.wildcard:
            return f"{imp.path}.{base_name}"

    return None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _collect_all_methods(method: MethodInfo) -> dict[str, MethodInfo]:
    """Flatten the method call tree into a dict keyed by 'fqn#methodName'."""
    result: dict[str, MethodInfo] = {}
    key = f"{method.class_fqn}#{method.method_name}"
    result[key] = method

    for call in method.downstream_calls:
        if call.resolved_method:
            result.update(_collect_all_methods(call.resolved_method))

    return result
