"""Quality gate judges for docs-orchestrator pipeline.

Runs doc_quality and intent_alignment judges against writing output,
cross-references intent gaps against scope-req-audit evidence status.

Usage:
    python3 quality_gate.py --ticket PROJ-123 --base-path /path/to/workspace
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DOC_QUALITY_PROMPT = """\
You are evaluating AI-generated AsciiDoc documentation for a Red Hat product feature.

Score the documentation on a 1-5 scale:
1 - Unusable: major errors, fabricated content, or missing critical sections
2 - Poor: significant gaps in coverage or accuracy
3 - Acceptable: covers the basics correctly but lacks depth or polish
4 - Good: comprehensive, accurate, well-structured, minor issues only
5 - Excellent: production-ready quality, matches what a senior tech writer would produce

Consider: technical accuracy, completeness relative to the JIRA ticket scope,
modular documentation structure (concept/procedure/reference separation),
and absence of fabricated commands, flags, or API details.

## Documentation to evaluate

{doc_content}
"""

INTENT_ALIGNMENT_PROMPT = """\
You are evaluating whether AI-generated documentation fulfills the intent
of the original JIRA ticket that requested it.

## JIRA ticket intent

{ticket_context}

## Documentation produced

{doc_content}

## Scoring criteria

Score on a 1-5 scale based on how well the documentation fulfills the ticket's intent:

1 - Off-target: documentation covers unrelated topics or misunderstands the request
2 - Partially relevant: touches on the right area but misses the core ask
3 - Addresses the intent: covers the main topic but misses key acceptance criteria or scope items
4 - Strong alignment: covers the intent well, addresses most acceptance criteria, correct audience
5 - Full alignment: directly addresses the ticket intent, covers all acceptance criteria, \
matches the target audience, stays within scope

Consider:
- **Scope match**: does the output address what the ticket asked for, not more, not less?
- **Acceptance criteria coverage**: are the specific deliverables listed in the ticket addressed?
- **Audience alignment**: does the content match the target audience (admin vs developer vs data scientist)?
- **Focus**: does the output stay on-topic or wander into areas outside the ticket's scope?
"""

INTENT_SYSTEM = (
    "You are a documentation quality judge. "
    'Respond with JSON: {"score": <1-5>, "rationale": "<explanation>", '
    '"missed_items": [{"ac_item": "<text>", "severity": "missing|incomplete"}]}'
)

DOC_QUALITY_SYSTEM = (
    "You are a documentation quality judge. "
    'Respond with JSON: {"score": <1-5>, "rationale": "<explanation>"}'
)

PASS_THRESHOLD_INTENT = 4


def read_doc_content(base_path):
    """Read AsciiDoc/Markdown files listed in writing/step-result.json."""
    sidecar = Path(base_path) / "writing" / "step-result.json"
    if not sidecar.exists():
        print(f"ERROR: {sidecar} not found", file=sys.stderr)
        sys.exit(1)

    data = json.loads(sidecar.read_text())
    files = data.get("files", [])
    if not files:
        print("ERROR: No files listed in writing/step-result.json", file=sys.stderr)
        sys.exit(1)

    parts = []
    for fpath in files:
        p = Path(fpath)
        if p.exists() and p.suffix in (".adoc", ".md"):
            parts.append(f"### {p.name}\n\n{p.read_text()}")
    return "\n\n".join(parts)


def read_ticket_context(base_path):
    """Read requirements/discovery.json and format as ticket context."""
    discovery = Path(base_path) / "requirements" / "discovery.json"
    if not discovery.exists():
        print(f"WARNING: {discovery} not found, using minimal context", file=sys.stderr)
        return "(No ticket context available)"

    data = json.loads(discovery.read_text())
    lines = [f"**Ticket**: {data.get('ticket_summary', 'Unknown')}"]

    reqs = data.get("requirements", [])
    if reqs:
        lines.append("\n**Requirements / Acceptance Criteria**:\n")
        for r in reqs:
            rid = r.get("id", "?")
            title = r.get("title", "")
            summary = r.get("one_line_summary", "")
            lines.append(f"- {rid}: {title} — {summary}")

    return "\n".join(lines)


def read_evidence_status(base_path):
    """Read scope-req-audit/evidence-status.json if available."""
    evidence = Path(base_path) / "scope-req-audit" / "evidence-status.json"
    if not evidence.exists():
        evidence = Path(base_path) / "validate" / "evidence-status.json"
    if not evidence.exists():
        return None
    return json.loads(evidence.read_text())


def call_judge(prompt, system_msg, model=None):
    """Call the Anthropic API to score documentation."""
    import anthropic

    if os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID"):
        client = anthropic.AnthropicVertex(
            project_id=os.environ["ANTHROPIC_VERTEX_PROJECT_ID"],
            region=os.environ.get("CLOUD_ML_REGION", "us-east5"),
        )
    elif os.environ.get("GOOGLE_CLOUD_PROJECT"):
        client = anthropic.AnthropicVertex(
            project_id=os.environ["GOOGLE_CLOUD_PROJECT"],
            region=os.environ.get("CLOUD_ML_REGION", "us-east5"),
        )
    else:
        client = anthropic.Anthropic()

    model = model or os.environ.get("QUALITY_GATE_MODEL", "claude-sonnet-4-6")

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system_msg,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    try:
        data = json.loads(text)
        return data
    except json.JSONDecodeError:
        score_match = re.search(r'"score"\s*:\s*(\d)', text)
        score = int(score_match.group(1)) if score_match else 3
        return {"score": score, "rationale": text[:500]}


def classify_gaps(missed_items, evidence_status):
    """Cross-reference missed AC items against evidence status."""
    gaps = []
    req_statuses = {}
    if evidence_status:
        for req in evidence_status.get("requirements", []):
            req_statuses[req.get("id", "")] = req
            title_lower = req.get("title", "").lower()
            req_statuses[title_lower] = req

    for item in missed_items:
        ac_text = item.get("ac_item", "")
        severity = item.get("severity", "missing")
        ac_lower = ac_text.lower()

        ev_status = "unknown"
        action = "investigate"

        for key, req in req_statuses.items():
            if isinstance(key, str) and (ac_lower in key or key in ac_lower):
                ev_status = req.get("status", "unknown")
                break

        if ev_status == "absent":
            action = "document_as_unsupported"
        elif ev_status == "partial":
            action = "expand_with_evidence"
        elif ev_status == "grounded":
            action = "add_missing_section"

        gaps.append({
            "ac_item": ac_text,
            "judge": "intent_alignment",
            "evidence_status": ev_status,
            "action": action,
        })

    return gaps


def write_results(output_dir, ticket, doc_quality_result, intent_result, gaps, iteration):
    """Write step-result.json and judge-results.md."""
    output_dir.mkdir(parents=True, exist_ok=True)

    dq_score = doc_quality_result.get("score", 0)
    ia_score = intent_result.get("score", 0)
    passed = ia_score >= PASS_THRESHOLD_INTENT

    sidecar = {
        "schema_version": 1,
        "step": "quality-gate",
        "ticket": ticket,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "doc_quality": dq_score,
        "intent_alignment": ia_score,
        "passed": passed,
        "iteration": iteration,
        "gaps": gaps,
        "rationales": {
            "doc_quality": doc_quality_result.get("rationale", ""),
            "intent_alignment": intent_result.get("rationale", ""),
        },
    }
    (output_dir / "step-result.json").write_text(json.dumps(sidecar, indent=2))

    md_lines = [
        f"# Quality Gate Results — {ticket}\n",
        f"**doc_quality**: {dq_score}/5",
        f"**intent_alignment**: {ia_score}/5",
        f"**passed**: {passed}",
        f"**iteration**: {iteration}\n",
        "## Doc Quality Rationale\n",
        doc_quality_result.get("rationale", "(none)"),
        "\n## Intent Alignment Rationale\n",
        intent_result.get("rationale", "(none)"),
    ]

    if gaps:
        md_lines.append("\n## Identified Gaps\n")
        for g in gaps:
            md_lines.append(
                f"- **{g['ac_item']}** — evidence: {g['evidence_status']}, "
                f"action: {g['action']}"
            )

    (output_dir / "judge-results.md").write_text("\n".join(md_lines))

    return sidecar


def main():
    parser = argparse.ArgumentParser(description="Quality gate judges")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--base-path", required=True)
    parser.add_argument("--iteration", type=int, default=1)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    base_path = Path(args.base_path)
    output_dir = base_path / "quality-gate"

    doc_content = read_doc_content(base_path)
    ticket_context = read_ticket_context(base_path)
    evidence_status = read_evidence_status(base_path)

    dq_prompt = DOC_QUALITY_PROMPT.format(doc_content=doc_content)
    ia_prompt = INTENT_ALIGNMENT_PROMPT.format(
        ticket_context=ticket_context, doc_content=doc_content,
    )

    print(f"Running doc_quality judge...", file=sys.stderr)
    dq_result = call_judge(dq_prompt, DOC_QUALITY_SYSTEM, args.model)

    print(f"Running intent_alignment judge...", file=sys.stderr)
    ia_result = call_judge(ia_prompt, INTENT_SYSTEM, args.model)

    missed_items = ia_result.get("missed_items", [])
    gaps = classify_gaps(missed_items, evidence_status)

    sidecar = write_results(
        output_dir, args.ticket, dq_result, ia_result, gaps, args.iteration,
    )

    json.dump(sidecar, sys.stdout, indent=2)
    print(file=sys.stdout)


if __name__ == "__main__":
    main()
