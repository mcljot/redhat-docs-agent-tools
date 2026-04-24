#!/usr/bin/env python3
"""Extract code changes for documentation impact analysis.

Runs deterministic extraction (diffs, file categorization, signal detection,
docs repo scanning) so the LLM can focus on judgment. Outputs JSON to stdout.

Usage:
    python3 gather_changes.py --commit <url-or-sha-or-branch> \
        [--repo <path>] [--base-branch <branch>] [--docs-root <path>]

Exit codes:
    0 — success (JSON on stdout)
    1 — error (message on stderr)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GIT_PR_READER = (
    SCRIPT_DIR / ".." / ".." / "git-pr-reader" / "scripts" / "git_pr_reader.py"
).resolve()

GITHUB_PR_RE = re.compile(
    r"https?://github\.com/([^/]+/[^/]+)/pull/(\d+)"
)
GITLAB_MR_RE = re.compile(
    r"https?://([^/]+)/(.+?)/-/merge_requests/(\d+)"
)
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
GITHUB_ISSUE_RE = re.compile(r"(?<![/\w])#(\d+)\b")
BREAKING_RE = re.compile(
    r"\b(BREAKING|deprecated?|removed?|migrat(?:e|ion)|obsolete)\b", re.IGNORECASE
)

CATEGORIES = {
    "documentation": [
        r"\.adoc$", r"\.rst$", r"^docs/", r"^documentation/",
        r"^README", r"^CONTRIBUTING", r"^CHANGELOG",
    ],
    "tests": [
        r"^tests?/", r"/__tests__/", r"_test\.", r"\.test\.",
        r"\.spec\.", r"Test\.(java|py|go|ts|js)$",
        r"^testdata/", r"^fixtures?/",
    ],
    "config": [
        r"\.ya?ml$", r"\.toml$", r"\.ini$", r"\.cfg$", r"\.conf$",
        r"\.env", r"^config/", r"\.properties$",
    ],
    "ci_cd": [
        r"^\.github/", r"\.gitlab-ci", r"[Jj]enkinsfile",
        r"^\.travis", r"^\.circleci/", r"^Makefile$", r"^Tiltfile$",
    ],
    "build": [
        r"^Dockerfile", r"^docker-compose", r"^Containerfile",
        r"go\.(mod|sum)$", r"package\.json$", r"requirements\.txt$",
        r"Pipfile", r"Gemfile", r"Cargo\.(toml|lock)$",
        r"pom\.xml$", r"build\.gradle",
    ],
}

API_PATTERNS = [
    r"^(?:src/)?api/", r"controllers?/", r"routes?/", r"handlers?/",
    r"endpoints?/", r"\.proto$", r"\.graphql$", r"openapi", r"swagger",
]
CONFIG_SIGNAL_PATTERNS = [
    r"defaults?\.(ya?ml|json|toml)$", r"\.env(\.\w+)?$",
    r"settings\.", r"config\.(ya?ml|json|toml|py|ts|js)$",
]

MAX_DIFF_LINES = 100
MAX_DOC_MATCHES_PER_FILE = 5
MAX_CODE_CONTEXT_FILES = 5


def _run(cmd, **kwargs):
    """Run a command and return stdout, or None on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, **kwargs)
        return r.stdout if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _err(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---- Ref type detection ----

def detect_ref_type(ref):
    if GITHUB_PR_RE.match(ref) or GITLAB_MR_RE.match(ref):
        return "pr"
    if SHA_RE.match(ref):
        return "commit"
    return "branch"


# ---- File categorization ----

def categorize_file(path):
    for cat, patterns in CATEGORIES.items():
        for p in patterns:
            if re.search(p, path, re.IGNORECASE):
                return cat
    return "source_code"


# ---- Extraction: PR/MR ----

def extract_pr(ref):
    if not GIT_PR_READER.exists():
        _err(f"git_pr_reader.py not found at {GIT_PR_READER}")

    reader = str(GIT_PR_READER)

    info_raw = _run(["python3", reader, "info", ref, "--json"])
    info = json.loads(info_raw) if info_raw else {}

    files_raw = _run(["python3", reader, "files", ref, "--json"])
    raw_files = json.loads(files_raw) if files_raw else []

    files = [
        {
            "path": f.get("path", ""),
            "status": f.get("status", "modified"),
            "added": f.get("additions", 0),
            "removed": f.get("deletions", 0),
        }
        for f in raw_files
    ]

    diff_text = (_run(["python3", reader, "diff", ref]) or "").strip()

    metadata = _build_pr_metadata(ref, info)
    return files, diff_text, metadata


def _build_pr_metadata(ref, info):
    metadata = {
        "title": info.get("title", ""),
        "description": info.get("body", ""),
        "labels": [],
        "linked_issues": [],
        "milestone": None,
    }

    if GITHUB_PR_RE.match(ref):
        out = _run(["gh", "pr", "view", ref, "--json", "labels,milestone"])
        if out:
            data = json.loads(out)
            metadata["labels"] = [
                l.get("name", "") for l in data.get("labels", [])
            ]
            ms = data.get("milestone")
            if ms:
                metadata["milestone"] = ms.get("title")

    text = f"{metadata['title']} {metadata['description']}"
    metadata["linked_issues"] = sorted(set(JIRA_KEY_RE.findall(text)))
    gh_refs = [f"#{n}" for n in GITHUB_ISSUE_RE.findall(text)]
    metadata["linked_issues"].extend(gh_refs)

    return metadata


# ---- Extraction: local commit / branch ----

def extract_local(ref, repo, base_branch, ref_type):
    if not repo:
        _err("--repo is required for local commits and branches")

    if ref_type == "commit":
        diff_out = _run(["git", "-C", repo, "show", "--format=", ref])
        numstat_out = _run(
            ["git", "-C", repo, "show", "--numstat", "--format=", ref]
        )
        msg_out = _run(["git", "-C", repo, "log", "--format=%B", "-1", ref])
    else:
        range_spec = f"{base_branch}..{ref}"
        diff_out = _run(["git", "-C", repo, "diff", range_spec])
        numstat_out = _run(["git", "-C", repo, "diff", "--numstat", range_spec])
        msg_out = _run(["git", "-C", repo, "log", "--oneline", range_spec])

    diff_text = (diff_out or "").strip()
    files = _parse_numstat(numstat_out or "")
    desc = (msg_out or "").strip()

    metadata = {
        "title": desc.split("\n")[0] if desc else "",
        "description": desc,
        "labels": [],
        "linked_issues": sorted(set(JIRA_KEY_RE.findall(desc))),
        "milestone": None,
    }

    return files, diff_text, metadata


def _parse_numstat(text):
    files = []
    for line in text.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_s, removed_s, path = parts
        try:
            added = int(added_s) if added_s != "-" else 0
            removed = int(removed_s) if removed_s != "-" else 0
        except ValueError:
            added, removed = 0, 0

        # Clean rename syntax: {old => new}
        clean_path = re.sub(r"\{[^}]* => ([^}]*)\}", r"\1", path)
        status = "renamed" if "{" in path and "=>" in path else "modified"
        files.append({
            "path": clean_path, "status": status,
            "added": added, "removed": removed,
        })
    return files


# ---- Analysis ----

def build_categories(files):
    cats = {}
    for name in list(CATEGORIES.keys()) + ["source_code"]:
        cats[name] = {"files": [], "total_added": 0, "total_removed": 0}

    for f in files:
        cat = categorize_file(f["path"])
        cats[cat]["files"].append(f)
        cats[cat]["total_added"] += f.get("added", 0)
        cats[cat]["total_removed"] += f.get("removed", 0)
    return cats


def detect_signals(files, diff_text):
    signals = {
        "new_files": [], "deleted_files": [], "renamed_files": [],
        "api_surface_changes": [], "config_changes": [],
        "schema_changes": [], "docs_modified": [],
        "breaking_indicators": [],
    }

    for f in files:
        path, status = f["path"], f.get("status", "modified")

        if status == "added":
            signals["new_files"].append(path)
        elif status == "deleted":
            signals["deleted_files"].append(path)
        elif status == "renamed":
            signals["renamed_files"].append(path)

        for p in API_PATTERNS:
            if re.search(p, path, re.IGNORECASE):
                signals["api_surface_changes"].append(path)
                break

        for p in CONFIG_SIGNAL_PATTERNS:
            if re.search(p, path, re.IGNORECASE):
                signals["config_changes"].append(path)
                break

        if re.search(r"\.(proto|graphql|gql|avro|thrift)$", path, re.IGNORECASE):
            signals["schema_changes"].append(path)

        if categorize_file(path) == "documentation":
            signals["docs_modified"].append(path)

    if diff_text:
        for line in diff_text.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                if BREAKING_RE.search(line):
                    signals["breaking_indicators"].append(line[:200].strip())

    for k in signals:
        signals[k] = list(dict.fromkeys(signals[k]))
    return signals


def _split_diff_by_file(diff_text):
    sections = {}
    current_file = None
    current_lines = []

    for line in diff_text.split("\n"):
        if line.startswith("diff --git"):
            if current_file:
                sections[current_file] = "\n".join(current_lines)
            match = re.search(r" b/(.+)$", line)
            current_file = match.group(1) if match else None
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_file:
        sections[current_file] = "\n".join(current_lines)
    return sections


def extract_key_diffs(files, diff_text, signals):
    high_signal = set(
        signals.get("new_files", [])
        + signals.get("api_surface_changes", [])
        + signals.get("config_changes", [])
        + signals.get("schema_changes", [])
    )
    if not high_signal:
        return []

    per_file = _split_diff_by_file(diff_text)
    key_diffs = []

    for path in high_signal:
        if path not in per_file:
            continue
        excerpt = per_file[path]
        lines = excerpt.split("\n")
        if len(lines) > MAX_DIFF_LINES:
            excerpt = (
                "\n".join(lines[:MAX_DIFF_LINES])
                + f"\n... ({len(lines) - MAX_DIFF_LINES} more lines)"
            )

        if path in signals.get("new_files", []):
            reason = "new_file"
        elif path in signals.get("api_surface_changes", []):
            reason = "api_change"
        elif path in signals.get("config_changes", []):
            reason = "config_change"
        else:
            reason = "schema_change"

        key_diffs.append({"file": path, "reason": reason, "excerpt": excerpt})

    return key_diffs


def extract_code_context(files, repo, signals):
    if not repo:
        return []

    targets = (
        signals.get("new_files", [])
        + signals.get("api_surface_changes", [])
    )[:MAX_CODE_CONTEXT_FILES]

    contexts = []
    for path in targets:
        basename = Path(path).stem
        grep_out = _run([
            "grep", "-rn", "-l",
            "--include=*.py", "--include=*.ts", "--include=*.js",
            "--include=*.go", "--include=*.java", "--include=*.rb",
            basename, repo,
        ])
        if not grep_out:
            continue
        importers = [
            ln.strip() for ln in grep_out.strip().split("\n")
            if ln.strip() and path not in ln
        ][:5]
        if importers:
            contexts.append({
                "file": path,
                "context_type": "imports",
                "detail": f"Referenced by: {', '.join(importers)}",
            })
    return contexts


def scan_docs(files, docs_root, signals):
    if not docs_root or not Path(docs_root).is_dir():
        return None

    find_out = _run([
        "find", docs_root, "-type", "f",
        "(", "-name", "*.adoc", "-o", "-name", "*.md", ")",
        "!", "-path", "*/.git/*",
        "!", "-path", "*/node_modules/*",
        "!", "-path", "*/.claude/*",
        "!", "-path", "*/.work/*",
    ])
    if not find_out:
        return {
            "docs_root": docs_root, "total_doc_files": 0,
            "affected_files": [], "coverage_gaps": [],
        }

    doc_files = [f.strip() for f in find_out.strip().split("\n") if f.strip()]

    # Build search terms from high-signal files
    interesting = (
        signals.get("api_surface_changes", [])
        + signals.get("new_files", [])
        + signals.get("config_changes", [])
    )[:15]

    search_terms = set()
    skip_generic = {"src", "lib", "pkg", "cmd", "internal", "main", "app", "index"}
    for path in interesting:
        stem = Path(path).stem
        if len(stem) > 3:
            search_terms.add(stem)
        for part in Path(path).parts:
            if len(part) > 3 and part.lower() not in skip_generic:
                search_terms.add(part)

    if not search_terms:
        return {
            "docs_root": docs_root, "total_doc_files": len(doc_files),
            "affected_files": [], "coverage_gaps": [],
        }

    affected = {}
    for term in sorted(search_terms)[:10]:
        grep_out = _run([
            "grep", "-rn", "--include=*.adoc", "--include=*.md",
            "-i", "-w", term, docs_root,
        ])
        if not grep_out:
            continue
        for line in grep_out.strip().split("\n")[:20]:
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            doc_file = parts[0]
            try:
                line_num = int(parts[1])
            except ValueError:
                continue
            text = parts[2].strip()[:200]

            if doc_file not in affected:
                affected[doc_file] = {"doc_file": doc_file, "matches": []}
            if len(affected[doc_file]["matches"]) < MAX_DOC_MATCHES_PER_FILE:
                affected[doc_file]["matches"].append({
                    "line": line_num, "text": text, "matched_term": term,
                })

    matched_terms = {
        m["matched_term"]
        for info in affected.values()
        for m in info["matches"]
    }
    gaps = []
    for path in signals.get("new_files", []) + signals.get("api_surface_changes", []):
        stem = Path(path).stem
        if stem not in matched_terms and len(stem) > 3:
            kind = (
                "New file" if path in signals.get("new_files", [])
                else "API change"
            )
            gaps.append({
                "feature": stem,
                "signal": f"{kind}: {path}",
                "existing_coverage": "none",
            })

    return {
        "docs_root": docs_root,
        "total_doc_files": len(doc_files),
        "affected_files": list(affected.values())[:20],
        "coverage_gaps": gaps[:10],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract code changes for documentation impact analysis"
    )
    parser.add_argument(
        "--commit", required=True,
        help="PR/MR URL, commit SHA, or branch name",
    )
    parser.add_argument("--repo", help="Path to local source repository")
    parser.add_argument(
        "--base-branch", default="main",
        help="Base branch for comparison (default: main)",
    )
    parser.add_argument(
        "--docs-root", default=os.getcwd(),
        help="Docs repo root for scanning (default: cwd)",
    )
    args = parser.parse_args()

    ref_type = detect_ref_type(args.commit)

    if ref_type == "pr":
        files, diff_text, metadata = extract_pr(args.commit)
    else:
        files, diff_text, metadata = extract_local(
            args.commit, args.repo, args.base_branch, ref_type,
        )

    cats = build_categories(files)
    signals = detect_signals(files, diff_text)
    summary = {
        "files_changed": len(files),
        "lines_added": sum(f.get("added", 0) for f in files),
        "lines_removed": sum(f.get("removed", 0) for f in files),
    }
    key_diffs = extract_key_diffs(files, diff_text, signals)
    code_context = extract_code_context(files, args.repo, signals)
    docs_scan = scan_docs(files, args.docs_root, signals)

    output = {
        "ref_type": ref_type,
        "ref": args.commit,
        "repo": args.repo,
        "pr_metadata": metadata,
        "summary": summary,
        "categories": cats,
        "signals": signals,
        "key_diffs": key_diffs,
        "code_context": code_context,
        "docs_scan": docs_scan,
    }

    json.dump(output, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
