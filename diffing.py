"""Unified-diff parsing.

We parse the diff ourselves rather than pulling in a heavier dependency, because
every downstream agent needs the same three things: which lines actually
changed (not the whole file), what surrounds them for context, and a stable
per-hunk id so findings can be anchored to a specific line in a GitHub review
comment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Hunk:
    hunk_id: str
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    added: list[tuple[int, str]] = field(default_factory=list)   # (new_line_no, text)
    removed: list[tuple[int, str]] = field(default_factory=list)  # (old_line_no, text)
    context: list[str] = field(default_factory=list)

    def added_text(self) -> str:
        return "\n".join(t for _, t in self.added)


@dataclass
class FileDiff:
    path: str
    old_path: str | None
    status: str  # added | modified | deleted | renamed
    hunks: list[Hunk] = field(default_factory=list)

    def added_lines(self) -> int:
        return sum(len(h.added) for h in self.hunks)

    def removed_lines(self) -> int:
        return sum(len(h.removed) for h in self.hunks)

    def full_added_text(self) -> str:
        return "\n".join(h.added_text() for h in self.hunks)


_FILE_HEADER = re.compile(r"^diff --git a/(.*) b/(.*)$")
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_BINARY = re.compile(r"^Binary files")


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    current_hunk: Hunk | None = None
    old_line = new_line = 0

    for line in diff_text.splitlines():
        if m := _FILE_HEADER.match(line):
            if current is not None:
                files.append(current)
            current = FileDiff(path=m.group(2), old_path=m.group(1), status="modified")
            current_hunk = None
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            current.status = "added"
        elif line.startswith("deleted file mode"):
            current.status = "deleted"
        elif line.startswith("rename to"):
            current.status = "renamed"
        elif _BINARY.match(line):
            current.status = "binary"
        elif m := _HUNK_HEADER.match(line):
            old_line = int(m.group(1))
            new_line = int(m.group(3))
            current_hunk = Hunk(
                hunk_id=f"{current.path}:{new_line}",
                old_start=old_line,
                old_lines=int(m.group(2) or 1),
                new_start=new_line,
                new_lines=int(m.group(4) or 1),
            )
            current.hunks.append(current_hunk)
        elif current_hunk is not None:
            if line.startswith("+") and not line.startswith("+++"):
                current_hunk.added.append((new_line, line[1:]))
                new_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                current_hunk.removed.append((old_line, line[1:]))
                old_line += 1
            elif line.startswith(" "):
                current_hunk.context.append(line[1:])
                old_line += 1
                new_line += 1
            # lines like "\ No newline at end of file" are ignored

    if current is not None:
        files.append(current)
    return files


def render_diff_for_prompt(files: list[FileDiff], max_chars: int) -> str:
    """Compact, line-numbered rendering an LLM can cite precisely from."""
    parts = []
    for f in files:
        if f.status == "binary":
            parts.append(f"### {f.path} (binary file, diff omitted)")
            continue
        parts.append(f"### {f.path} ({f.status}, +{f.added_lines()}/-{f.removed_lines()})")
        for hunk in f.hunks:
            parts.append(f"@@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@")
            for ln, text in hunk.added:
                parts.append(f"+{ln:>5} {text}")
            for ln, text in hunk.removed:
                parts.append(f"-{ln:>5} {text}")
    rendered = "\n".join(parts)
    if len(rendered) > max_chars:
        rendered = rendered[:max_chars] + "\n\n... [diff truncated, exceeded max_diff_chars] ..."
    return rendered


def scope_summary(files: list[FileDiff]) -> dict[str, int]:
    return {
        "files_changed": len(files),
        "lines_added": sum(f.added_lines() for f in files),
        "lines_removed": sum(f.removed_lines() for f in files),
    }
