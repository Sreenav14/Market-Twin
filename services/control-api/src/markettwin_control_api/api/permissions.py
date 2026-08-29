"""Shared authorization rules for the Control API."""


WORKSPACE_WRITE_ROLES = frozenset(
    {
        "owner",
        "admin",
        "member",
    }
)

TARGET_AUTHORIZATION_ROLES = frozenset(
    {
        "owner",
        "admin",
    }
)