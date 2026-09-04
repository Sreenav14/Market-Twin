"""Explicit browser execution errors for MarketTwin."""


class BrowserRuntimeError(RuntimeError):
    """Base class for MarketTwin browser execution failures."""


class BrowserPolicyError(BrowserRuntimeError):
    """Raised when a browser operation violates deterministic policy."""


class BrowserActionBlockedError(BrowserPolicyError):
    """Raised when an autonomous action is outside the low-risk policy."""


class TargetUrlValidationError(BrowserPolicyError):
    """Raised when a target URL is invalid or outside the allowlist."""


class HostResolutionError(BrowserPolicyError):
    """Raised when a hostname cannot be resolved safely."""


class BrowserSessionNotFoundError(BrowserRuntimeError):
    """Raised when a browser session does not exist."""


class BrowserSessionOwnershipError(BrowserRuntimeError):
    """Raised when a Journey attempts to use another Journey's browser."""


class BrowserSessionStateError(BrowserRuntimeError):
    """Raised when an operation is invalid for the current browser state."""


class BrowserActionError(BrowserRuntimeError):
    """Raised when an approved browser action cannot be completed."""


class BrowserNavigationError(BrowserActionError):
    """Raised when navigation fails after policy approval."""


class BrowserTimeoutError(BrowserActionError):
    """Raised when a browser action exceeds its bounded timeout."""


class HumanControlActiveError(BrowserSessionStateError):
    """Raised when an agent action is attempted during human control."""
