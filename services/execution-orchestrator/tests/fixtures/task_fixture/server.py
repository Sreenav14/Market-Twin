"""Task fixture app (doc 29 section 9): a small served application the
task-skill pipeline learns, verifies, and reuses skills against.

Surfaces, each present for a named pipeline purpose:

- ``/`` home with a search box (text entry) and ``/search`` results
  whose count and first title are assertable;
- ``/agents``: a seeded list plus a "New agent" form (text entry,
  selection, submission) whose outcome -- the created item present in
  the list under its given name -- is browser-checkable. Created items
  persist in server memory; a delete-by-name form on the list page is
  the compensating cleanup, and ``/__reset`` restores the seed state;
- ``/login`` + ``/account``: a credential gate (key-referenced values
  only; the fixture's own credentials are fixture truth, not product
  data) for the ``authenticated`` prerequisite;
- ``?variant=broken``: Create appears to succeed (identical
  confirmation page) but the item never reaches the list -- a broken
  outcome on an unchanged-looking page;
- ``?variant=moved``: the Create submit control is renamed and
  relocated -- a locator-shaped change for divergence handling.

Agent rows render as generic divs and the confirmation page never
echoes the created name, so a page's distilled element identity is
stable across different created names: the outcome lives in the
assertions (the name present as page text), not in the state hash.
"""

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import parse_qs, urlsplit

SEED_AGENTS = [{"name": "Fixture Agent Alpha", "model": "Fixture Model A"}]
MODELS = ("Fixture Model A", "Fixture Model B")
FIXTURE_USERNAME = "fixture-user"
FIXTURE_PASSWORD = "fixture-pass"
SEARCH_CORPUS = (
    "Getting started with agents",
    "Billing and plans",
    "Agent run history",
    "Search relevance tuning",
)


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{title}</title></head><body>{body}</body></html>"
    )


def _nav() -> str:
    return (
        '<nav><a href="/">Home</a> <a href="/agents">Agents</a> '
        '<a href="/search">Search</a> <a href="/account">Account</a></nav>'
    )


class TaskFixtureServer(ThreadingHTTPServer):
    def __init__(self, port: int = 0) -> None:
        self.lock = Lock()
        self.agents: list[dict[str, str]] = [dict(item) for item in SEED_AGENTS]
        self.sessions: set[str] = set()
        # A deployment-wide variant (set via /__variant): the app
        # "regressed" for every visitor, which is how verification
        # and reuse tests meet the broken/moved variants -- a
        # compiled definition navigates with its own recorded URLs,
        # so a per-URL variant could never reach it.
        self.default_variant = ""
        super().__init__(("127.0.0.1", port), TaskFixtureHandler)

    def reset(self) -> None:
        with self.lock:
            self.agents = [dict(item) for item in SEED_AGENTS]
            self.sessions = set()
            self.default_variant = ""


class TaskFixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    # -- plumbing ---------------------------------------------------
    def respond(self, status: int, content: str, content_type: str,
                headers: dict[str, str] | None = None) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def redirect(self, location: str, headers: dict[str, str] | None = None) -> None:
        self.respond(303, "", "text/plain", {"Location": location, **(headers or {})})

    def form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        parsed = parse_qs(raw)
        return {key: values[0] for key, values in parsed.items() if values}

    def session_token(self) -> str | None:
        cookie = self.headers.get("Cookie") or ""
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "fixture_session" and value in self.server.sessions:
                return value
        return None

    # -- routes -----------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        split = urlsplit(self.path)
        path = split.path
        query = parse_qs(split.query)
        variant = (query.get("variant") or [self.server.default_variant])[0]
        if path == "/__state":
            with self.server.lock:
                agents = [dict(item) for item in self.server.agents]
            self.respond(200, json.dumps({"agents": agents}), "application/json")
            return
        if path == "/__reset":
            self.server.reset()
            self.redirect("/agents")
            return
        if path == "/":
            self.respond(200, _page("Task Fixture Home", _nav() + """
<h1>Task Fixture Home</h1>
<form method="get" action="/search">
  <label for="q">Search the fixture</label>
  <input id="q" name="q" type="text">
  <button type="submit">Search</button>
</form>
"""), "text/html; charset=utf-8")
            return
        if path == "/search":
            term = (query.get("q") or [""])[0]
            results = [
                title for title in SEARCH_CORPUS
                if term.casefold() in title.casefold()
            ]
            rows = "".join(
                f'<div class="result-row"><span class="result-title">{title}</span></div>'
                for title in results
            )
            self.respond(200, _page("Search results", _nav() + f"""
<h1>Search results</h1>
<p id="result-count">{len(results)} results</p>
{rows}
"""), "text/html; charset=utf-8")
            return
        if path == "/agents":
            suffix = f"?variant={variant}" if variant else ""
            with self.server.lock:
                agents = [dict(item) for item in self.server.agents]
            rows = "".join(
                '<div class="agent-row">'
                f'<span class="agent-name">{item["name"]}</span> '
                f'<span class="agent-model">{item["model"]}</span></div>'
                for item in agents
            )
            self.respond(200, _page("Agents", _nav() + f"""
<h1>Agents</h1>
<a href="/agents/new{suffix}">New agent</a>
{rows}
<form method="post" action="/agents/delete">
  <label for="delete-name">Agent name to delete</label>
  <input id="delete-name" name="name" type="text">
  <button type="submit">Delete agent</button>
</form>
<a href="/__reset">Reset fixture data</a>
"""), "text/html; charset=utf-8")
            return
        if path == "/agents/new":
            moved = variant == "moved"
            button = (
                '<button type="submit">Add agent</button>'
                if moved else '<button type="submit">Create agent</button>'
            )
            fields = """
  <label for="agent-name">Agent name</label>
  <input id="agent-name" name="name" type="text">
  <label for="agent-model">Model</label>
  <select id="agent-model" name="model">
    <option>Fixture Model A</option>
    <option>Fixture Model B</option>
  </select>
"""
            ordered = (button + fields) if moved else (fields + button)
            self.respond(200, _page("New agent", _nav() + f"""
<h1>New agent</h1>
<form method="post" action="/agents/create">
  <input type="hidden" name="variant" value="{variant}">
{ordered}
</form>
<a href="/agents">Back to agents</a>
"""), "text/html; charset=utf-8")
            return
        if path == "/agents/created":
            self.respond(200, _page("Agent created", _nav() + """
<h1>Agent created</h1>
<p>Your agent is ready.</p>
<a href="/agents">View agents</a>
"""), "text/html; charset=utf-8")
            return
        if path == "/login":
            error = (
                '<p id="login-error">Invalid username or password.</p>'
                if (query.get("error") or [""])[0] else ""
            )
            self.respond(200, _page("Sign in", _nav() + f"""
<h1>Sign in</h1>
{error}
<form method="post" action="/login">
  <label for="username">Username</label>
  <input id="username" name="username" type="text">
  <label for="password">Password</label>
  <input id="password" name="password" type="password">
  <button type="submit">Sign in</button>
</form>
"""), "text/html; charset=utf-8")
            return
        if path == "/account":
            if self.session_token() is None:
                self.redirect("/login")
                return
            self.respond(200, _page("Account", _nav() + """
<h1>Account</h1>
<p>Signed in as fixture-user</p>
<a href="/logout">Sign out</a>
"""), "text/html; charset=utf-8")
            return
        if path == "/logout":
            token = self.session_token()
            if token is not None:
                with self.server.lock:
                    self.server.sessions.discard(token)
            self.redirect("/", {"Set-Cookie": "fixture_session=; Path=/; Max-Age=0"})
            return
        self.respond(404, "Fixture route not found.", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/__reset":
            self.server.reset()
            self.respond(200, "{}", "application/json")
            return
        if path == "/__variant":
            data = self.form()
            with self.server.lock:
                self.server.default_variant = data.get("variant") or ""
            self.respond(200, "{}", "application/json")
            return
        if path == "/agents/create":
            data = self.form()
            if data.get("variant") != "broken":
                name = (data.get("name") or "").strip()
                model = data.get("model") or MODELS[0]
                if name:
                    with self.server.lock:
                        self.server.agents.append(
                            {"name": name, "model": model}
                        )
            self.redirect("/agents/created")
            return
        if path == "/agents/delete":
            data = self.form()
            name = (data.get("name") or "").strip()
            with self.server.lock:
                self.server.agents = [
                    item for item in self.server.agents if item["name"] != name
                ]
            self.redirect("/agents")
            return
        if path == "/login":
            data = self.form()
            if (
                data.get("username") == FIXTURE_USERNAME
                and data.get("password") == FIXTURE_PASSWORD
            ):
                token = secrets.token_hex(16)
                with self.server.lock:
                    self.server.sessions.add(token)
                self.redirect(
                    "/account",
                    {"Set-Cookie": f"fixture_session={token}; Path=/"},
                )
                return
            self.redirect("/login?error=1")
            return
        self.respond(404, "Fixture route not found.", "text/plain")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    with TaskFixtureServer(args.port) as server:
        print(
            json.dumps({"origin": f"http://127.0.0.1:{server.server_port}"}),
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
