""" Authenticated domain models """

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    """Identity established by an authenticated provider."""
    
    issuer: str
    subject: str
    email: str
    normalized_email: str
    display_name: str | None