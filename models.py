"""Data models for the XML Command Analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AppConfig:
    """Runtime configuration for the analyzer."""

    xml_dir: str
    java_source_root: str
    query: str
    output_json: str
    max_depth: int = 10
    db_path: str = "xmlparser_cache.db"


@dataclass
class CommandEntry:
    """A single <command> extracted from an XML file."""

    name: str
    impl_class: str  # fully-qualified Java class name
    source_file: str  # which XML file it came from


@dataclass
class MethodCall:
    """A method invocation found inside a method body."""

    target_expression: str
    resolved_class_fqn: str | None = None
    resolved_method: MethodInfo | None = None


@dataclass
class MethodInfo:
    """A Java method with its source code and downstream calls."""

    class_fqn: str
    method_name: str
    signature: str
    source_code: str
    start_line: int
    end_line: int
    downstream_calls: list[MethodCall] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Top-level result for one matched impl-class."""

    command_name: str
    impl_class: str
    java_file_path: str
    execute_method: MethodInfo | None = None
    all_resolved_methods: dict[str, MethodInfo] = field(default_factory=dict)
