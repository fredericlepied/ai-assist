#!/usr/bin/env python3
"""Check that local links in markdown files point to existing files and anchors."""

import re
import sys
from pathlib import Path

# Match markdown links: [text](target) but not external URLs
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def heading_to_anchor(heading: str) -> str:
    """Convert a markdown heading to a GitHub-style anchor."""
    anchor = heading.strip().lower()
    # Remove markdown formatting
    anchor = re.sub(r"[*_`~]", "", anchor)
    # Replace spaces with hyphens
    anchor = re.sub(r"\s+", "-", anchor)
    # Remove non-alphanumeric chars except hyphens
    anchor = re.sub(r"[^\w-]", "", anchor)
    return anchor


def get_anchors(filepath: Path) -> set[str]:
    """Extract all heading anchors from a markdown file."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    anchors = set()
    for match in HEADING_RE.finditer(content):
        anchors.add(heading_to_anchor(match.group(1)))
    return anchors


def check_file(filepath: Path, repo_root: Path) -> list[str]:
    """Check all local links in a markdown file."""
    errors = []
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return errors

    file_dir = filepath.parent

    for match in LINK_RE.finditer(content):
        target = match.group(2)

        # Skip external URLs, mailto, and fragment-only links
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue

        # Split target into path and optional anchor
        if "#" in target:
            path_part, anchor = target.split("#", 1)
        else:
            path_part, anchor = target, None

        if not path_part:
            continue

        # Resolve relative to the file's directory
        target_path = (file_dir / path_part).resolve()

        if not target_path.exists():
            line_num = content[: match.start()].count("\n") + 1
            errors.append(f"{filepath}:{line_num}: broken link to '{target}' (file not found: {path_part})")
        elif anchor and target_path.is_file() and target_path.suffix == ".md":
            anchors = get_anchors(target_path)
            if anchor not in anchors:
                line_num = content[: match.start()].count("\n") + 1
                errors.append(f"{filepath}:{line_num}: broken anchor '#{anchor}' in '{path_part}'")

    return errors


def main() -> int:
    repo_root = Path.cwd()

    # Find all markdown files, excluding .venv and .pytest_cache
    md_files = sorted(
        p
        for p in repo_root.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(repo_root).parts[:-1])
        and "node_modules" not in p.parts
    )

    all_errors = []
    for md_file in md_files:
        all_errors.extend(check_file(md_file, repo_root))

    for error in all_errors:
        print(error)

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
