#!/usr/bin/env python3
"""Wire assembly include directives from a match manifest.

Reads match-manifest.json, builds section hierarchy, parses original
assembly files to learn inline vs include structure, then rebuilds
each assembly with correct include:: directives and inline sections.

Handles new assemblies (creates them) and updates master.adoc.

Usage:
    wire_assemblies.py --manifest <path> --repo-path <path> [--dry-run]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Wire assembly include directives from a match manifest."
    )
    parser.add_argument(
        "--manifest", required=True, help="Path to match-manifest.json"
    )
    parser.add_argument(
        "--repo-path", required=True, help="Path to the docs repo"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without writing files",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Step 1: Build section tree from flat manifest
# ---------------------------------------------------------------------------

def build_section_tree(sections):
    """Walk flat sections and build parent-child relationships.

    Returns a list of top-level (level 2) nodes, each with a `children`
    list. Level 3 children can themselves have `children` (level 4).
    """
    top_level = []
    current_l2 = None
    current_l3 = None

    for section in sections:
        status = section.get("status", "")
        level = section.get("level", 0)
        heading = section.get("heading", "")

        if status in ("preamble", "skipped"):
            continue
        if level == 0:
            continue
        if not heading or not heading.strip():
            continue
        # Filter markdown artifacts: bare heading markers, numbering-only
        stripped = re.sub(r"^[#*\s]+", "", heading).strip()
        stripped = re.sub(r"^[\d]+(?:\.[\d]+)*\.?\s*$", "", stripped).strip()
        if not stripped and not section.get("content", "").strip():
            continue

        node = {**section, "children": []}

        if level == 2:
            current_l2 = node
            current_l3 = None
            top_level.append(node)
        elif level == 3:
            current_l3 = node
            if current_l2 is not None:
                current_l2["children"].append(node)
            else:
                top_level.append(node)
        elif level == 4:
            if current_l3 is not None:
                current_l3["children"].append(node)
            elif current_l2 is not None:
                current_l2["children"].append(node)

    return top_level


# ---------------------------------------------------------------------------
# Step 2: Parse original assembly for inline vs include structure
# ---------------------------------------------------------------------------

INCLUDE_RE = re.compile(
    r"^include::(.+?\.adoc)\[leveloffset=\+(\d+)\]\s*$"
)
INLINE_HEADING_RE = re.compile(r"^(={2,})\s+(.+)$")


def parse_assembly(assembly_path):
    """Parse an assembly file and return its structure.

    Returns a dict with:
        includes: dict mapping filename to {path, offset}
        inline_headings: set of heading titles that are inline sections
        inline_sections: dict mapping heading title to list of body lines
        raw_text: full file text
    """
    if not assembly_path.is_file():
        return None

    text = assembly_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    includes = {}
    inline_headings = set()
    inline_sections = {}
    footer_start = None

    current_inline_heading = None
    current_inline_lines = []

    for i, line in enumerate(lines):
        if line.strip().startswith("ifdef::parent-context"):
            footer_start = i
            if current_inline_heading:
                inline_sections[current_inline_heading] = current_inline_lines
            break

        m_inc = INCLUDE_RE.match(line)
        if m_inc:
            if current_inline_heading:
                inline_sections[current_inline_heading] = current_inline_lines
                current_inline_heading = None
                current_inline_lines = []
            path = m_inc.group(1)
            offset = int(m_inc.group(2))
            filename = Path(path).name
            includes[filename] = {"path": path, "offset": offset}
            continue

        m_heading = INLINE_HEADING_RE.match(line)
        if m_heading:
            heading_level = len(m_heading.group(1))
            if heading_level >= 2:
                if current_inline_heading:
                    inline_sections[current_inline_heading] = current_inline_lines
                heading_text = m_heading.group(2).strip()
                inline_headings.add(heading_text)
                current_inline_heading = heading_text
                current_inline_lines = []
                continue

        if current_inline_heading is not None:
            current_inline_lines.append(line)

    return {
        "includes": includes,
        "inline_headings": inline_headings,
        "inline_sections": inline_sections,
        "raw_text": text,
    }


# ---------------------------------------------------------------------------
# Step 3: Compute include path for a child section
# ---------------------------------------------------------------------------

def module_path_to_include_path(module_path):
    """Convert a manifest module_path to an assembly include:: path.

    upstream/opendatahub-documentation-main/modules/foo.adoc -> upstream-modules/foo.adoc
    modules/foo.adoc -> modules/foo.adoc
    """
    if module_path is None:
        return None

    if module_path.startswith("upstream/opendatahub-documentation-main/modules/"):
        filename = Path(module_path).name
        return f"upstream-modules/{filename}"

    if module_path.startswith("modules/"):
        return module_path

    return module_path


def clean_heading(heading):
    """Strip markdown formatting, numbering, and anchors from a heading."""
    h = heading
    # Remove markdown anchor fragments {#...}
    h = re.sub(r"\{#[^}]+\}", "", h)
    # Remove bold markers
    h = h.replace("**", "")
    # Remove leading ### or ## markers
    h = re.sub(r"^#+\s*", "", h)
    # Remove leading chapter/section numbering (e.g., "4.1.1 ", "Chapter 6: ")
    h = re.sub(r"^(?:Chapter\s+)?\d+(?:\.\d+)*\.?\s*:?\s*", "", h, flags=re.IGNORECASE)
    # Truncate at trailing content blended into the heading (double space
    # or markdown link that follows the title)
    h = re.sub(r"\s{2,}.*$", "", h)
    return h.strip()


def _slug_from_text(text):
    """Convert text to a kebab-case slug. Returns empty string if nothing usable."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    if len(slug) > 80:
        slug = slug[:80].rsplit("-", 1)[0]
    return slug


def heading_to_filename(heading, id_fragment=None):
    """Convert a heading to a kebab-case module filename.

    Falls back to id_fragment (with context suffix stripped) when the
    heading cleans to an empty string.  Returns None if no usable slug
    can be derived.
    """
    slug = _slug_from_text(clean_heading(heading))

    if not slug and id_fragment:
        # Strip context suffix (e.g., "_custom-models") — context suffixes
        # contain hyphens while the ID stem uses underscores exclusively
        frag = re.sub(r"_[a-z][a-z0-9]*(?:-[a-z0-9]+)+$", "", id_fragment)
        slug = _slug_from_text(frag.replace("_", " "))

    if not slug:
        return None

    return f"{slug}.adoc"


_title_index_cache = {}


def _build_title_index(repo_path):
    """Build a map of AsciiDoc title -> relative include path for modules/."""
    if repo_path in _title_index_cache:
        return _title_index_cache[repo_path]

    index = {}
    modules_dir = repo_path / "modules"
    if modules_dir.is_dir():
        for f in modules_dir.glob("*.adoc"):
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    if line.startswith("= "):
                        title = line[2:].strip()
                        index[title.lower()] = f"modules/{f.name}"
                        break
            except (OSError, UnicodeDecodeError):
                continue

    _title_index_cache[repo_path] = index
    return index


def resolve_include_path(child, repo_path):
    """Determine the include path for a child section.

    Returns (include_path, exists_on_disk) tuple.
    include_path is None when no usable filename can be derived.
    """
    if child.get("module_path"):
        inc_path = module_path_to_include_path(child["module_path"])
        return inc_path, True

    filename = heading_to_filename(
        child["heading"], id_fragment=child.get("id_fragment")
    )
    if filename is not None:
        candidate = f"modules/{filename}"
        if (repo_path / candidate).is_file():
            return candidate, True

    cleaned = clean_heading(child.get("heading", ""))
    if cleaned:
        title_index = _build_title_index(repo_path)
        match = title_index.get(cleaned.lower())
        if match:
            return match, True

    if filename is not None:
        return f"modules/{filename}", False

    return None, False


def leveloffset_for_child(child, parent_level, assembly_info=None, resolved_path=None):
    """Compute leveloffset based on child level relative to parent.

    If the child's resolved include path exists in the original assembly's
    includes, use the original leveloffset to preserve the document hierarchy.
    """
    if assembly_info and resolved_path:
        filename = Path(resolved_path).name
        inc_info = assembly_info.get("includes", {}).get(filename)
        if inc_info:
            return f"+{inc_info['offset']}"

    delta = child["level"] - parent_level
    return f"+{delta}"


# ---------------------------------------------------------------------------
# Step 4: Decide inline vs include
# ---------------------------------------------------------------------------

def should_inline(child, assembly_info):
    """Decide whether a child section should be inlined in the assembly.

    - Previously included -> stays as include
    - Previously inlined -> stays inline
    - New section -> default to include
    """
    heading = child.get("heading", "")
    cleaned = clean_heading(heading)

    if assembly_info is None:
        return False

    if heading in assembly_info["inline_headings"]:
        return True
    if cleaned in assembly_info["inline_headings"]:
        return True

    if child.get("module_path"):
        filename = Path(child["module_path"]).name
        if filename in assembly_info["includes"]:
            return False

    if child.get("status") == "new":
        return False

    return False


# ---------------------------------------------------------------------------
# Step 5: Read the writing-agent-updated assembly to get current body text
# ---------------------------------------------------------------------------

def read_updated_assembly_body(assembly_path):
    """Read the intro/abstract text from the assembly.

    Returns only the text between the title line and the first include
    directive or inline heading (== Section).  Inline sections and
    includes are handled separately by build_children_block.
    """
    if not assembly_path.is_file():
        return ""

    text = assembly_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    body_start = None

    for i, line in enumerate(lines):
        if line.startswith("= ") and body_start is None:
            body_start = i + 1

    if body_start is None:
        return ""

    body_lines = []
    for line in lines[body_start:]:
        if INCLUDE_RE.match(line):
            break
        if INLINE_HEADING_RE.match(line):
            break
        if line.strip().startswith("ifdef::parent-context"):
            break
        body_lines.append(line)

    body = "\n".join(body_lines).strip()
    return body


# ---------------------------------------------------------------------------
# Step 6: Build assembly content
# ---------------------------------------------------------------------------

ASSEMBLY_TEMPLATE = """:_module-type: ASSEMBLY

ifdef::context[:parent-context: {{context}}]

[id="{assembly_id}_{{context}}"]
= {title}

{body}

{children_block}

ifdef::parent-context[:context: {{parent-context}}]
ifndef::parent-context[:!context:]
"""


def extract_assembly_header(assembly_path):
    """Extract the header section of an existing assembly file.

    Returns everything from the start through the title line and any
    abstract/role tags, stopping before the first include or inline section.
    """
    if not assembly_path.is_file():
        return None

    text = assembly_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    header = []
    past_title = False

    for line in lines:
        if INCLUDE_RE.match(line):
            break
        m_heading = INLINE_HEADING_RE.match(line)
        if m_heading and past_title:
            break
        if line.startswith("= "):
            past_title = True
        if line.strip().startswith("ifdef::parent-context"):
            break
        header.append(line)

    while header and not header[-1].strip():
        header.pop()

    return header


def _get_inline_content(heading, assembly_info):
    """Get inline section content from the assembly file (already AsciiDoc).

    Falls back to empty string if not found.
    """
    if assembly_info is None:
        return ""
    sections = assembly_info.get("inline_sections", {})
    content = sections.get(heading)
    if content is not None:
        return "\n".join(content).strip()
    return ""


def build_children_block(children, parent_level, assembly_info, repo_path):
    """Build the include/inline block for an assembly's children.

    Returns (text, unresolvable) where unresolvable is a list of headings
    that could not be mapped to a module file.
    """
    parts = []
    unresolvable = []

    for child in children:
        inline = should_inline(child, assembly_info)

        if inline:
            heading = clean_heading(child["heading"]) or child["heading"]
            parts.append(f"== {heading}")
            parts.append("")
            content = _get_inline_content(heading, assembly_info)
            if not content:
                content = child.get("content", "").strip()
            if content:
                parts.append(content)
                parts.append("")

            for grandchild in child.get("children", []):
                gc_inline = should_inline(grandchild, assembly_info)
                if gc_inline:
                    gc_heading = clean_heading(grandchild["heading"]) or grandchild["heading"]
                    parts.append(f"=== {gc_heading}")
                    parts.append("")
                    gc_content = _get_inline_content(gc_heading, assembly_info)
                    if not gc_content:
                        gc_content = grandchild.get("content", "").strip()
                    if gc_content:
                        parts.append(gc_content)
                        parts.append("")
                else:
                    gc_path, _ = resolve_include_path(grandchild, repo_path)
                    if gc_path is None:
                        unresolvable.append(grandchild.get("heading", ""))
                        continue
                    gc_offset = leveloffset_for_child(
                        grandchild, parent_level, assembly_info, gc_path
                    )
                    parts.append(f"include::{gc_path}[leveloffset={gc_offset}]")
                    parts.append("")
        else:
            inc_path, _ = resolve_include_path(child, repo_path)
            if inc_path is None:
                unresolvable.append(child.get("heading", ""))
                continue
            offset = leveloffset_for_child(
                child, parent_level, assembly_info, inc_path
            )
            parts.append(f"include::{inc_path}[leveloffset={offset}]")
            parts.append("")

            for grandchild in child.get("children", []):
                gc_path, _ = resolve_include_path(grandchild, repo_path)
                if gc_path is None:
                    unresolvable.append(grandchild.get("heading", ""))
                    continue
                gc_offset = leveloffset_for_child(
                    grandchild, parent_level, assembly_info, gc_path
                )
                parts.append(f"include::{gc_path}[leveloffset={gc_offset}]")
                parts.append("")

    return "\n".join(parts), unresolvable


def build_assembly_file(assembly_node, assembly_info, repo_path):
    """Build the complete assembly file content.

    Returns (content, unresolvable) tuple.
    """
    assembly_path = repo_path / assembly_node.get("module_path", "")
    header_lines = extract_assembly_header(assembly_path)

    if header_lines is None:
        title = clean_heading(assembly_node["heading"])
        assembly_id = (heading_to_filename(title) or "assembly.adoc").replace(".adoc", "")
        header_lines = [
            ":_module-type: ASSEMBLY",
            "",
            "ifdef::context[:parent-context: {context}]",
            "",
            f'[id="{assembly_id}_{{context}}"]',
            f"= {title}",
        ]

    children_block, unresolvable = build_children_block(
        assembly_node.get("children", []),
        assembly_node["level"],
        assembly_info,
        repo_path,
    )

    parts = []
    parts.append("\n".join(header_lines))
    parts.append("")

    if children_block.strip():
        parts.append(children_block)

    parts.append("ifdef::parent-context[:context: {parent-context}]")
    parts.append("ifndef::parent-context[:!context:]")
    parts.append("")

    return "\n".join(parts), unresolvable


def build_new_assembly_file(assembly_node, repo_path):
    """Build a new assembly file for a level-2 new section.

    Returns (content, unresolvable) tuple.
    """
    heading = clean_heading(assembly_node["heading"])
    slug = (heading_to_filename(heading) or "assembly.adoc").replace(".adoc", "")

    header_lines = [
        ":_module-type: ASSEMBLY",
        "",
        "ifdef::context[:parent-context: {context}]",
        "",
        f'[id="{slug}_{{context}}"]',
        f"= {heading}",
    ]

    body = assembly_node.get("content", "").strip()

    children_block, unresolvable = build_children_block(
        assembly_node.get("children", []),
        assembly_node["level"],
        None,
        repo_path,
    )

    parts = []
    parts.append("\n".join(header_lines))
    parts.append("")

    if body:
        parts.append(body)
        parts.append("")

    if children_block.strip():
        parts.append(children_block)

    parts.append("ifdef::parent-context[:context: {parent-context}]")
    parts.append("ifndef::parent-context[:!context:]")
    parts.append("")

    return "\n".join(parts), unresolvable


# ---------------------------------------------------------------------------
# Step 7: Find and update master.adoc
# ---------------------------------------------------------------------------

def find_master_adoc(repo_path, known_assembly_paths):
    """Find the master.adoc that includes one of the known assemblies."""
    for master in repo_path.rglob("master.adoc"):
        text = master.read_text(encoding="utf-8")
        for asm_path in known_assembly_paths:
            filename = Path(asm_path).name
            if filename in text:
                return master
    return None


def insert_assembly_in_master(master_path, new_assembly_path, after_assembly_path):
    """Insert an include directive for a new assembly in master.adoc.

    Places it after the include for after_assembly_path.
    """
    text = master_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    new_filename = Path(new_assembly_path).name
    new_include = f"include::assemblies/{new_filename}[leveloffset=+1]"

    if new_include in text:
        return text, False

    after_filename = Path(after_assembly_path).name
    insert_idx = None

    for i, line in enumerate(lines):
        if after_filename in line and "include::" in line:
            insert_idx = i + 1
            break

    if insert_idx is None:
        lines.append("")
        lines.append(new_include)
    else:
        lines.insert(insert_idx, "")
        lines.insert(insert_idx + 1, new_include)

    return "\n".join(lines) + "\n", True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.is_file():
        print(f"ERROR: Manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    repo_path = Path(args.repo_path).resolve()
    if not repo_path.is_dir():
        print(f"ERROR: Repo path not found: {repo_path}", file=sys.stderr)
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sections = manifest.get("sections", [])

    tree = build_section_tree(sections)

    result = {
        "assemblies_updated": [],
        "assemblies_created": [],
        "master_updated": None,
        "orphaned_modules": [],
        "missing_modules": [],
        "unresolvable_sections": [],
    }

    known_assembly_paths = []
    last_matched_assembly_path = None
    new_assemblies_to_insert = []

    for node in tree:
        module_path = node.get("module_path", "")
        is_assembly = module_path and "assemblies/" in module_path

        if node["status"] == "matched" and is_assembly:
            known_assembly_paths.append(module_path)
            assembly_file = repo_path / module_path
            assembly_info = parse_assembly(assembly_file)

            content, unresolvable = build_assembly_file(node, assembly_info, repo_path)
            result["unresolvable_sections"].extend(unresolvable)

            if args.dry_run:
                print(f"[DRY RUN] Would update: {module_path}", file=sys.stderr)
                print(f"  Children: {len(node.get('children', []))}", file=sys.stderr)
                for child in node.get("children", []):
                    inc_path, _ = resolve_include_path(child, repo_path)
                    inline = should_inline(child, assembly_info)
                    if inc_path is None:
                        tag = "UNRESOLVABLE"
                    elif inline:
                        tag = "INLINE"
                    else:
                        tag = "INCLUDE"
                    print(f"    [{tag}] {child['heading']}", file=sys.stderr)
                    for gc in child.get("children", []):
                        gc_path, _ = resolve_include_path(gc, repo_path)
                        gc_inline = should_inline(gc, assembly_info)
                        if gc_path is None:
                            gc_tag = "UNRESOLVABLE"
                        elif gc_inline:
                            gc_tag = "INLINE"
                        else:
                            gc_tag = "INCLUDE"
                        print(f"      [{gc_tag}] {gc['heading']}", file=sys.stderr)
            else:
                assembly_file.write_text(content, encoding="utf-8")
                print(f"Updated: {module_path}", file=sys.stderr)

            result["assemblies_updated"].append(module_path)
            last_matched_assembly_path = module_path

        elif node["status"] == "new" and node.get("children"):
            slug = heading_to_filename(
                clean_heading(node["heading"]),
                id_fragment=node.get("id_fragment"),
            )
            if slug is None:
                result["unresolvable_sections"].append(node.get("heading", ""))
                continue
            new_path = f"assemblies/{slug}"
            assembly_file = repo_path / new_path

            content, unresolvable = build_new_assembly_file(node, repo_path)
            result["unresolvable_sections"].extend(unresolvable)

            if args.dry_run:
                print(f"[DRY RUN] Would create: {new_path}", file=sys.stderr)
                for child in node.get("children", []):
                    inc_path, _ = resolve_include_path(child, repo_path)
                    tag = "UNRESOLVABLE" if inc_path is None else "INCLUDE"
                    print(f"    [{tag}] {child['heading']}", file=sys.stderr)
            else:
                assembly_file.write_text(content, encoding="utf-8")
                print(f"Created: {new_path}", file=sys.stderr)

            result["assemblies_created"].append(new_path)
            new_assemblies_to_insert.append({
                "new_path": new_path,
                "after_path": last_matched_assembly_path,
            })

    if new_assemblies_to_insert and known_assembly_paths:
        master = find_master_adoc(repo_path, known_assembly_paths)
        if master:
            master_rel = str(master.relative_to(repo_path))
            for item in new_assemblies_to_insert:
                after = item["after_path"] or known_assembly_paths[-1]
                if args.dry_run:
                    print(
                        f"[DRY RUN] Would insert {item['new_path']} "
                        f"in {master_rel} after {after}",
                        file=sys.stderr,
                    )
                else:
                    new_text, changed = insert_assembly_in_master(
                        master, item["new_path"], after
                    )
                    if changed:
                        master.write_text(new_text, encoding="utf-8")
                        print(
                            f"Updated master.adoc: {master_rel}",
                            file=sys.stderr,
                        )

            result["master_updated"] = master_rel

    for node in tree:
        for child in node.get("children", []):
            inc_path, exists = resolve_include_path(child, repo_path)
            if inc_path and not exists:
                result["missing_modules"].append(inc_path)
            for gc in child.get("children", []):
                gc_path, gc_exists = resolve_include_path(gc, repo_path)
                if gc_path and not gc_exists:
                    result["missing_modules"].append(gc_path)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
