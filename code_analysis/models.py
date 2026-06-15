from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ClassInfo:
    name: str
    methods: list[str] = field(default_factory=list)
    docstring: str = ""


@dataclass
class FileInfo:
    path: Path
    imports: list[str] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    docstring: str = ""
    line_count: int = 0
    error: str = ""
