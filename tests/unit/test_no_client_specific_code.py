"""Sprint 7 acceptance criterion, corpus/12: 'no client-specific code exists
anywhere in the repository. Every difference between companies is a row in
a configuration table.' A structural sweep over src/ and web/ (the actual
application code) -- synthetic/ and tests/ are explicitly exempt, since the
synthetic reference companies (the fictional 'Brightleaf' consumer brand,
'Synthetic Manufacturer Co') are test fixtures, not client data, and it is
correct for the generator that INVENTS them to know their names.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APPLICATION_DIRS = [REPO_ROOT / "src", REPO_ROOT / "web" / "app", REPO_ROOT / "web" / "lib"]
APPLICATION_FILE_SUFFIXES = {".py", ".ts", ".tsx"}

# Names that would only appear in application code if a real or synthetic
# company had been special-cased there instead of driven from config/data.
FORBIDDEN_NAME_FRAGMENTS = [
    "brightleaf", "synthetic manufacturer co", "synthetic consumer",
]

# Patterns that are themselves evidence of a per-company branch, regardless
# of which name is used -- "if company_name ==", "if tenant.name ==", etc.
FORBIDDEN_CODE_PATTERNS = [
    "if company ==", "if company_name ==", "if tenant_name ==", 'if tenant.name ==',
]


def _application_files():
    for d in APPLICATION_DIRS:
        if not d.exists():
            continue
        for path in d.rglob("*"):
            if path.is_file() and path.suffix in APPLICATION_FILE_SUFFIXES:
                if "node_modules" in path.parts or ".next" in path.parts:
                    continue
                yield path


def test_no_synthetic_company_names_in_application_code():
    offenders = []
    for path in _application_files():
        text = path.read_text(errors="ignore").lower()
        for fragment in FORBIDDEN_NAME_FRAGMENTS:
            if fragment in text:
                offenders.append((str(path.relative_to(REPO_ROOT)), fragment))
    assert offenders == [], (
        f"application code references a specific company name -- every difference between "
        f"companies must be a row in a configuration table, not a code branch: {offenders}"
    )


def test_no_per_company_branching_patterns_in_application_code():
    offenders = []
    for path in _application_files():
        text = path.read_text(errors="ignore")
        for pattern in FORBIDDEN_CODE_PATTERNS:
            if pattern in text:
                offenders.append((str(path.relative_to(REPO_ROOT)), pattern))
    assert offenders == [], f"found per-company code branches: {offenders}"


def test_profile_is_always_a_parameter_not_a_hardcoded_branch():
    """profile ('manufacturing' | 'consumer') is the one legitimate
    per-company AXIS this system has (corpus/02 section 3) -- it must
    always arrive as a caller-supplied value (a query param, a config
    field), never as a hardcoded default baked into application logic that
    silently assumes one profile. This spot-checks the route layer, where
    a hardcoded assumption would be most consequential."""
    routes_dir = REPO_ROOT / "src" / "api" / "routes"
    offenders = []
    for path in routes_dir.glob("*.py"):
        text = path.read_text()
        if 'profile: str = "manufacturing"' in text or 'profile: str = "consumer"' in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"a route defaults 'profile' instead of requiring the caller to pass it: {offenders}"
