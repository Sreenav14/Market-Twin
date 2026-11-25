"""Generality lint (doc 24 section 2.1, W4-P5-01): the harness is
target-blind. No product source file may name a target site — no host
literals, and no branching on a hostname — because a rule that knows
one site's name is a rule that silently stops working on every other
site. The only hostnames allowed in the tree name PROVIDER classes
(captcha networks, identity providers, the model API): infrastructure
every target shares, never a target itself. Each such literal carries
exactly one allowlist entry below, with its justification.

Scanned trees (doc 24 section 13.1): the orchestrator's workflow,
slop, browser and models packages plus its top-level modules, the
control-api knowledge package and its app_maps / test_run API
modules, and the shared package. Tests and fixtures are excluded —
they may name all the fake sites they like.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR_PACKAGE = (
    REPO_ROOT
    / "services/execution-orchestrator/src/markettwin_execution_orchestrator"
)
CONTROL_API_PACKAGE = (
    REPO_ROOT / "services/control-api/src/markettwin_control_api"
)
SHARED_PACKAGE = REPO_ROOT / "packages/shared-python/src/markettwin_shared"

# (path relative to the repo root, literal) -> why this provider-class
# hostname may appear in product code. One entry per literal; the
# justification names the provider class, never a target.
ALLOWLIST: dict[tuple[str, str], str] = {
    # browser/policy.py — captcha provider networks the browser guard
    # must recognise on ANY target (the guard loads them; a target
    # never sends data to them under the browser-freedom rules).
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/policy.py", "www.google.com"): "captcha provider host (reCAPTCHA network)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/policy.py", "www.recaptcha.net"): "captcha provider host (reCAPTCHA network)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/policy.py", "www.gstatic.com"): "captcha provider asset host (reCAPTCHA network)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/policy.py", "hcaptcha.com"): "captcha provider host (hCaptcha network)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/policy.py", "challenges.cloudflare.com"): "captcha provider host (Cloudflare Turnstile)",
    # browser/offsite.py — identity-provider hosts a login wall may
    # legitimately redirect to on ANY target (SSO is a provider class).
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "accounts.google.com"): "identity provider host (Google SSO)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "login.microsoftonline.com"): "identity provider host (Microsoft SSO)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "login.microsoft.com"): "identity provider host (Microsoft SSO)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "login.live.com"): "identity provider host (Microsoft SSO)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "appleid.apple.com"): "identity provider host (Apple SSO)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "account.apple.com"): "identity provider host (Apple SSO)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "challenges.cloudflare.com"): "captcha provider host (Cloudflare Turnstile)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "recaptcha.net"): "captcha provider suffix (reCAPTCHA network)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "www.recaptcha.net"): "captcha provider host (reCAPTCHA network)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "www.google.com"): "captcha provider host (reCAPTCHA network)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "www.gstatic.com"): "captcha provider asset host (reCAPTCHA network)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "okta.com"): "identity provider suffix (Okta SSO)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "oktapreview.com"): "identity provider suffix (Okta preview SSO)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "auth0.com"): "identity provider suffix (Auth0 SSO)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/offsite.py", "hcaptcha.com"): "captcha provider suffix (hCaptcha network)",
    # browser/auth_verifier.py — the captcha anchor endpoints an
    # identity check may be served from, on any target.
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/auth_verifier.py", "www.google.com"): "captcha provider host (reCAPTCHA anchor)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/auth_verifier.py", "www.recaptcha.net"): "captcha provider host (reCAPTCHA anchor)",
    # browser/discovery_checkpoint.py — bot-wall provider hosts whose
    # presence classifies a checkpoint, on any target.
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/discovery_checkpoint.py", "captcha-delivery.com"): "bot-wall provider host (DataDome delivery)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/discovery_checkpoint.py", "datadome.co"): "bot-wall provider host (DataDome)",
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/discovery_checkpoint.py", "challenges.cloudflare.com"): "captcha provider host (Cloudflare Turnstile)",
    # models/decisions_client.py — the run's own model endpoint:
    # provider infrastructure, called by the harness, never a target.
    ("services/execution-orchestrator/src/markettwin_execution_orchestrator/models/decisions_client.py", "api.openai.com"): "model provider host (OpenAI API endpoint)",
}

_HOST_RE = re.compile(
    r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+"
    r"(com|net|org|io|co|dev|app|ai|cloud|test|example|local|invalid)$",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://([^/:?#]+)", re.IGNORECASE)


def _literal_host(value: str) -> str | None:
    """The hostname a string literal names, if it names one."""

    candidate = value.strip().lstrip(".")
    if _HOST_RE.match(candidate):
        return candidate.lower()
    match = _URL_RE.match(candidate)
    if match and _HOST_RE.match(match.group(1)):
        return match.group(1).lower()
    return None


def _is_host_expression(node: ast.AST) -> bool:
    """A hostname/netloc/host access, or a urlsplit/urlparse call."""

    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr in {
            "hostname", "netloc", "host",
        }:
            return True
        if isinstance(child, ast.Call):
            func = child.func
            name = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute)
                else ""
            )
            if name in {"urlsplit", "urlparse"}:
                return True
        if isinstance(child, ast.Name) and "host" in child.id.lower():
            return True
    return False


def scan_file(path: Path, *, relative: str) -> list[str]:
    """All generality violations in one source file."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    except SyntaxError:
        return [f"{relative}: unparseable source"]
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            host = _literal_host(node.value)
            if host is not None and (relative, host) not in ALLOWLIST:
                violations.append(
                    f"{relative}:{node.lineno}: host literal {host!r} "
                    "is not allowlisted"
                )
        if isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            literal_hosts: list[str] = []
            for side in sides:
                values: list[ast.AST] = (
                    list(side.elts)
                    if isinstance(side, (ast.Set, ast.List, ast.Tuple))
                    else [side]
                )
                for value in values:
                    if isinstance(value, ast.Constant) and isinstance(
                        value.value, str
                    ):
                        host = _literal_host(value.value)
                        if host is not None:
                            literal_hosts.append(host)
            if literal_hosts and any(
                _is_host_expression(side) for side in sides
            ):
                for host in literal_hosts:
                    if (relative, host) not in ALLOWLIST:
                        violations.append(
                            f"{relative}:{node.lineno}: host-keyed "
                            f"branching on {host!r}"
                        )
    return violations


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for sub in ("workflow", "slop", "browser", "models"):
        files.extend((ORCHESTRATOR_PACKAGE / sub).rglob("*.py"))
    files.extend(ORCHESTRATOR_PACKAGE.glob("*.py"))
    files.extend((CONTROL_API_PACKAGE / "knowledge").rglob("*.py"))
    files.append(CONTROL_API_PACKAGE / "api" / "app_maps.py")
    files.append(CONTROL_API_PACKAGE / "api" / "test_run.py")
    files.extend(SHARED_PACKAGE.rglob("*.py"))
    return sorted(
        {path for path in files if "__pycache__" not in path.parts}
    )


def test_no_target_hosts_in_product_trees() -> None:
    """T-P5-G1: zero unallowlisted host literals or host-keyed
    branches in the scanned product trees."""

    violations: list[str] = []
    for path in _scanned_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        violations.extend(scan_file(path, relative=relative))
    assert violations == []


def test_allowlist_entries_carry_justifications() -> None:
    for (relative, literal), justification in ALLOWLIST.items():
        assert justification.strip(), (relative, literal)
        assert literal == literal.lower() and " " not in literal


def test_lint_catches_planted_violations(tmp_path: Path) -> None:
    """T-P5-G2: the lint is not vacuous — a planted host literal and
    a planted host-keyed branch in a synthetic module are both caught,
    and an allowlisted literal in its own file passes."""

    planted = tmp_path / "planted_module.py"
    planted.write_text(
        'TARGET = "shop.example-store.com"\n'
        "\n"
        "def route(hostname: str) -> str:\n"
        '    if hostname == "shop.example-store.com":\n'
        '        return "special"\n'
        '    return "normal"\n',
        encoding="utf-8",
    )
    violations = scan_file(planted, relative="planted_module.py")
    assert any("host literal" in v for v in violations)
    assert any("host-keyed branching" in v for v in violations)

    allowed = tmp_path / "policy.py"
    allowed.write_text('CAPTCHA = "www.google.com"\n', encoding="utf-8")
    relative = (
        "services/execution-orchestrator/src/"
        "markettwin_execution_orchestrator/browser/policy.py"
    )
    assert scan_file(allowed, relative=relative) == []
