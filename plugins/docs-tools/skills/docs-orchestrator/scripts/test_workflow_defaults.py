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
