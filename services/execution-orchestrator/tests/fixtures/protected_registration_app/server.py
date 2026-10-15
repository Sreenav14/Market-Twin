"""Loopback-only composition of the existing login/MFA and registration fixtures."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

FIXTURES = Path(__file__).resolve().parents[1]


class ProtectedRegistrationServer(ThreadingHTTPServer):
    def __init__(self, port: int = 0) -> None:
        self.effects = 0
        self.effects_lock = Lock()
        super().__init__(("127.0.0.1", port), ProtectedRegistrationHandler)


class ProtectedRegistrationHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def respond(self, status: int, content: str, content_type: str) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/__fixture_effects":
            with self.server.effects_lock:
                count = self.server.effects
            self.respond(200, json.dumps({"registration_submissions": count}), "application/json")
            return
        if path == "/index.html":
            html = (FIXTURES / "hitl_app/index.html").read_text(encoding="utf-8")
            redirect = 'location.href = "?view=dashboard&variant=" + variant;'
            if html.count(redirect) != 1:
                raise RuntimeError("Synthetic MFA fixture redirect changed.")
            html = html.replace(
                redirect, 'location.href = "/registration.html?variant=" + variant;',
            )
        elif path in {"/", "/registration.html"}:
            registration = (FIXTURES / "deep_testing_app/index.html").read_text(encoding="utf-8")
            registration += """<script>
const identity = document.createElement('p');
identity.id = 'identity';
identity.textContent = 'Signed in as ' + sessionStorage.getItem('fixture-role');
document.body.prepend(identity);
document.getElementById('registration')?.addEventListener('submit', () => {
  if (!document.getElementById('result').hidden) {
    fetch('/__fixture_effect', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({operation: 'registration_submit'})});
  }
});
</script>"""
            # Keep the nested script markup inside the JS string until authentication succeeds.
            payload = json.dumps(registration).replace("<", "\\u003c")
            html = """<!doctype html><meta charset="utf-8"><script>
const fixtureRole = sessionStorage.getItem('fixture-role');
if (fixtureRole === 'user' || fixtureRole === 'admin') {
  const registration = PAYLOAD;
  document.write(registration);
} else {
  location.replace('/index.html?view=login');
}
</script>""".replace("PAYLOAD", payload)
        else:
            self.respond(404, "Fixture route not found.", "text/plain")
            return
        self.respond(200, html, "text/html; charset=utf-8")

    def do_POST(self) -> None:
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if urlsplit(self.path).path != "/__fixture_effect" or self.headers.get("Origin") != origin:
            self.respond(403, "Fixture effect denied.", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 128:
            self.respond(400, "Invalid fixture effect.", "text/plain")
            return
        try:
            body = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            body = None
        if body != {"operation": "registration_submit"}:
            self.respond(400, "Invalid fixture effect.", "text/plain")
            return
        with self.server.effects_lock:
            self.server.effects += 1
        self.respond(200, "{}", "application/json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    with ProtectedRegistrationServer(args.port) as server:
        print(json.dumps({"origin": f"http://127.0.0.1:{server.server_port}"}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
