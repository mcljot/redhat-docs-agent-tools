"""Regression tests for workflow default identity and variant structure."""

import re
from pathlib import Path

DEFAULTS_DIR = Path(__file__).resolve().parent.parent / "defaults"


def _workflow_name(path):
    text = path.read_text()
    match = re.search(r"^  name: (.+)$", text, re.MULTILINE)
    assert match, f"Could not find workflow.name in {path}"
    return match.group(1).strip()


def _step_names(path):
    text = path.read_text()
    return re.findall(r"^    - name: ([A-Za-z0-9-]+)$", text, re.MULTILINE)


def test_code_evidence_workflow_has_unique_identity():
    """The code-evidence workflow must not reuse the plain workflow name."""
    default_name = _workflow_name(DEFAULTS_DIR / "docs-workflow.yaml")
    code_evidence_name = _workflow_name(DEFAULTS_DIR / "docs-workflow-code-evidence.yaml")

    assert default_name == "docs-workflow"
    assert code_evidence_name == "docs-workflow-code-evidence"
    assert code_evidence_name != default_name


def test_code_evidence_workflow_keeps_code_grounding_steps():
    """The code-evidence workflow should continue to include its extra steps."""
    step_names = _step_names(DEFAULTS_DIR / "docs-workflow-code-evidence.yaml")

    assert "scope-req-audit" in step_names
    assert "code-evidence" in step_names


def test_default_workflow_includes_scope_req_audit_not_code_evidence():
    """Default workflow has scope-req-audit (conditional) but not code-evidence."""
    path = DEFAULTS_DIR / "docs-workflow.yaml"
    text = path.read_text()
    step_names = _step_names(path)

    assert "scope-req-audit" in step_names
    assert "code-evidence" not in step_names

    assert "when: has_source_repo" in text


def test_default_is_strict_subset_of_code_evidence_variant():
    """Default workflow steps are a strict subset of the code-evidence variant."""
    default_steps = set(_step_names(DEFAULTS_DIR / "docs-workflow.yaml"))
    ce_steps = set(_step_names(DEFAULTS_DIR / "docs-workflow-code-evidence.yaml"))

    assert default_steps < ce_steps
    assert ce_steps - default_steps == {"code-evidence"}
