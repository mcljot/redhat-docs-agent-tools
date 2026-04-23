#!/usr/bin/env python3
"""Split a markdown file by headings and match sections to AsciiDoc modules.

Reads a markdown file (typically exported from Google Docs), splits it into
sections by heading level, extracts docs.redhat.com URL fragment IDs, and
matches each section to an existing .adoc module in the target repo.

Outputs match-manifest.json to the base-path directory.

Usage:
    import_markdown.py <ticket> --markdown <path> --base-path <path> [--repo-path <path>]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Split markdown and match sections to AsciiDoc modules."
    )
    parser.add_argument("ticket", help="Ticket ID or label")
    parser.add_argument(
        "--markdown", required=True, help="Path to the markdown file"
    )
    parser.add_argument(
        "--base-path", required=True, help="Output base path for manifest"
    )
    parser.add_argument(
        "--repo-path",
        default=None,
        help="Path to the docs repo (default: current working directory)",
    )
    return parser.parse_args()


def split_by_headings(text):
    """Split markdown text into sections by heading level (##, ###, ####).

    Returns a list of dicts with keys: heading, level, content, raw_heading.
    Content before the first ## heading is classified as preamble.
    """
    heading_re = re.compile(r"^(#{2,4})\s+(.+)$", re.MULTILINE)

    sections = []
    matches = list(heading_re.finditer(text))

    if not matches:
        return [{"heading": None, "level": 0, "content": text.strip(), "raw_heading": None, "is_preamble": True}]

    # Preamble: content before first heading
    preamble_text = text[: matches[0].start()].strip()
    if preamble_text:
        sections.append({
            "heading": None,
            "level": 0,
            "content": preamble_text,
            "raw_heading": None,
            "is_preamble": True,
        })

    for i, match in enumerate(matches):
        level = len(match.group(1))
        raw_heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        sections.append({
            "heading": raw_heading,
            "level": level,
            "content": content,
            "raw_heading": raw_heading,
            "is_preamble": False,
        })

    return sections


def extract_id_from_heading(heading):
    """Extract a docs.redhat.com URL fragment ID from a heading.

    Headings may contain links like:
        [2.1. About the Python index](https://docs.redhat.com/...#about-the-python-index_custom-models)

    Returns (id_fragment, id_stem, clean_heading) or (None, None, clean_heading).
    """
    link_re = re.compile(
        r"\[([^\]]+)\]\(https?://docs\.redhat\.com/[^)]*#([^)]+)\)"
    )
    m = link_re.search(heading)
    if not m:
        clean = strip_numbering(heading)
        return None, None, clean

    link_text = m.group(1).strip()
    fragment = m.group(2).strip()

    # Strip the last _<word> segment to get the ID stem
    stem = re.sub(r"_[^_]+$", "", fragment)

    clean = strip_numbering(link_text)
    return fragment, stem, clean


def strip_numbering(text):
    """Remove leading section numbering like '2.1. ' or '2.1.3 '."""
    return re.sub(r"^[\d]+(?:\.[\d]+)*\.?\s+", "", text).strip()


def grep_for_id_stem(stem, repo_path):
    """Search .adoc files for [id="<stem>_" or [id='<stem>_' and return matching file paths."""
    paths = set()
    for quote in ('"', "'"):
        pattern = f"[id={quote}{stem}_"
        try:
            result = subprocess.run(
                ["grep", "-rl", "--include=*.adoc", "-F", pattern, "."],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            continue
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if line.strip():
                    paths.add(line.strip().lstrip("./"))
    return sorted(paths)


def search_by_heading_text(heading_text, repo_path):
    """Search .adoc files for a matching module title (= <title>)."""
    # Escape special grep characters
    escaped = re.sub(r'([\[\]{}()*+?.\\^$|])', r'\\\1', heading_text)
    pattern = f"^= {escaped}"
    try:
        result = subprocess.run(
            ["grep", "-rl", "--include=*.adoc", "-E", pattern, "."],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return []

    if result.returncode != 0:
        return []

    paths = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    return [p.lstrip("./") for p in paths]


def match_sections(sections, repo_path):
    """Match each section to an .adoc module. Returns the manifest sections list."""
    results = []

    for section in sections:
        if section.get("is_preamble"):
            results.append({
                "heading": "(preamble)",
                "level": 0,
                "status": "preamble",
                "module_path": None,
                "matched_by": None,
                "id_fragment": None,
                "content": section["content"],
            })
            continue

        heading = section["heading"]
        level = section["level"]
        content = section["content"]

        fragment, stem, clean_heading = extract_id_from_heading(heading)

        # Try URL fragment matching first
        if stem:
            matches = grep_for_id_stem(stem, repo_path)
            if len(matches) == 1:
                results.append({
                    "heading": clean_heading,
                    "level": level,
                    "status": "matched",
                    "module_path": matches[0],
                    "matched_by": "url_fragment",
                    "id_fragment": fragment,
                    "content": content,
                })
                continue
            elif len(matches) > 1:
                results.append({
                    "heading": clean_heading,
                    "level": level,
                    "status": "skipped",
                    "module_path": None,
                    "matched_by": None,
                    "id_fragment": fragment,
                    "reason": f"Multiple matches: {', '.join(matches)}",
                    "content": content,
                })
                continue

        # Try heading text matching as fallback
        heading_matches = search_by_heading_text(clean_heading, repo_path)
        if len(heading_matches) == 1:
            results.append({
                "heading": clean_heading,
                "level": level,
                "status": "matched",
                "module_path": heading_matches[0],
                "matched_by": "heading_text",
                "id_fragment": fragment,
                "content": content,
            })
            continue
        elif len(heading_matches) > 1:
            results.append({
                "heading": clean_heading,
                "level": level,
                "status": "skipped",
                "module_path": None,
                "matched_by": None,
                "id_fragment": fragment,
                "reason": f"Multiple heading matches: {', '.join(heading_matches)}",
                "content": content,
            })
            continue

        # No match found — classify as new
        if fragment:
            # Had a URL but no .adoc file found — could be deleted or renamed
            results.append({
                "heading": clean_heading,
                "level": level,
                "status": "new",
                "module_path": None,
                "matched_by": None,
                "id_fragment": fragment,
                "content": content,
            })
        else:
            results.append({
                "heading": clean_heading,
                "level": level,
                "status": "new",
                "module_path": None,
                "matched_by": None,
                "id_fragment": None,
                "content": content,
            })

    return results


def build_summary(sections):
    """Build a summary dict from the matched sections."""
    counts = {"matched": 0, "new": 0, "skipped": 0, "preamble_skipped": 0}
    for s in sections:
        status = s["status"]
        if status == "matched":
            counts["matched"] += 1
        elif status == "new":
            counts["new"] += 1
        elif status == "skipped":
            counts["skipped"] += 1
        elif status == "preamble":
            counts["preamble_skipped"] += 1
    counts["total"] = counts["matched"] + counts["new"] + counts["skipped"] + counts["preamble_skipped"]
    return counts


def main():
    args = parse_args()

    markdown_path = Path(args.markdown).resolve()
    if not markdown_path.is_file():
        print(f"ERROR: Markdown file not found: {markdown_path}", file=sys.stderr)
        sys.exit(1)

    repo_path = Path(args.repo_path).resolve() if args.repo_path else Path.cwd()
    if not repo_path.is_dir():
        print(f"ERROR: Repo path not found: {repo_path}", file=sys.stderr)
        sys.exit(1)

    base_path = Path(args.base_path).resolve()
    output_dir = base_path / "import-markdown"
    output_dir.mkdir(parents=True, exist_ok=True)

    text = markdown_path.read_text(encoding="utf-8")
    sections = split_by_headings(text)
    matched_sections = match_sections(sections, str(repo_path))
    summary = build_summary(matched_sections)

    manifest = {
        "source_file": str(markdown_path),
        "repo_path": str(repo_path),
        "sections": matched_sections,
        "summary": summary,
    }

    manifest_path = output_dir / "match-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Emit JSON result on stdout for the skill to consume
    result = {
        "manifest_path": str(manifest_path),
        "output_dir": str(output_dir),
        "summary": summary,
    }
    print(json.dumps(result))

    # Print human-readable summary on stderr
    print(
        f"\nImport matching complete: {summary['matched']} matched, "
        f"{summary['new']} new, {summary['skipped']} skipped",
        file=sys.stderr,
    )
    if summary["skipped"] > 0:
        print(
            "Skipped sections require manual attention — see match-manifest.json for details.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
