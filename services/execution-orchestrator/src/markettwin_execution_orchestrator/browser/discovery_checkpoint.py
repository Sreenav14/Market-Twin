"""Deterministic classification of sparse browser checkpoint pages."""

from urllib.parse import urlsplit


def is_discovery_checkpoint(*, text: str, scripts: list[str], controls: int) -> bool:
    text = " ".join(text.lower().split())
    if controls > 2 or len(text.split()) > 160:
        return False
    phrases = ("please enable js and disable any ad blocker", "verify you are human",
               "verifying you are human", "checking your browser", "performing security verification")
    text_signal = any(phrase in text for phrase in phrases)
    script_signal = False
    for script in scripts:
        url = urlsplit(script)
        host = (url.hostname or "").lower()
        if (any(host == domain or host.endswith("." + domain) for domain in
                ("captcha-delivery.com", "datadome.co", "challenges.cloudflare.com"))
                or "/cdn-cgi/challenge-platform/" in url.path):
            script_signal = True
    return text_signal or (script_signal and controls == 0 and len(text.split()) < 12)
