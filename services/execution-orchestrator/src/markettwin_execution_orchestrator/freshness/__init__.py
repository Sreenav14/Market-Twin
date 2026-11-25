"""Freshness preflight (Phase 4, doc 23).

Keeps application maps honest between verdict runs: a tiered sweep
re-checks a map version's fingerprints, and reconcile mints a
successor version from what the sweep proved — never an in-place
edit, never a model call.
"""
