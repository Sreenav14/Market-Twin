"""Conservative finding classifications for the existing evaluation categories."""


def classify_finding(category: str, *, has_visual_evidence: bool = False) -> tuple[str, str]:
    """Return finding kind and verification method, independently of severity."""
    if category == "visual_criterion" and has_visual_evidence:
        return "observed_product_issue", "verified_visual"
    if category == "deterministic_assertion" and has_visual_evidence:
        return "observed_product_issue", "verified_deterministic"
    if category in {"policy", "execution_reliability"}:
        return "test_execution_issue", "not_applicable"
    # Agent outcomes, repeated claims, and unknown/legacy categories are unverified.
    return "not_verified", "unverified"
