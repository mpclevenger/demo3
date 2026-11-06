"""A small GitHub helper for the export scripts: graphql(query, variables) and rest(path, params).

Set two things before running (Windows: setx NAME "value", then open a new window):
  GITHUB_HOST   your GitHub server, e.g. github.yourcompany.com (no https://). Leave unset for github.com.
  GITHUB_TOKEN  a personal access token that can read the orgs' repos (scopes: repo, read:org).

Optional:
  GITHUB_CA_BUNDLE  path to your company's certificate file, if the server's certificate isn't trusted
                    by Python (error mentions CERTIFICATE_VERIFY_FAILED).

Uses only Python's standard library, so there is nothing to install.
"""
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = os.environ.get("GITHUB_HOST", "").strip().removeprefix("https://").removeprefix("http://").strip("/")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

if HOST and HOST != "github.com":                 # GitHub Enterprise Server
    API = f"https://{HOST}/api/v3"
    GRAPHQL_URL = f"https://{HOST}/api/graphql"
else:                                             # github.com
    API = "https://api.github.com"
    GRAPHQL_URL = "https://api.github.com/graphql"

_CA = os.environ.get("GITHUB_CA_BUNDLE", "").strip()
_SSL = ssl.create_default_context(cafile=_CA) if _CA else ssl.create_default_context()

RETRIES = 4          # tries again on busy-server errors (502/503/504) and rate limits
TIMEOUT = 120        # seconds per request
MAX_WAIT = 3900      # longest single wait for the rate limit to reset (GitHub resets it every hour)
MAX_RATE_WAITS = 5   # how many times to wait for a reset before giving up


def _send(req):
    if not TOKEN:
        sys.exit("GITHUB_TOKEN is not set. Set it (Windows: setx GITHUB_TOKEN \"your-token\") and open a new window.")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "trust-repo-export")
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL) as r:
                return json.loads(r.read().decode("utf-8") or "null"), r.headers
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            limited = e.code in (403, 429) and ("rate limit" in body.lower() or e.headers.get("Retry-After"))
            if (e.code in (502, 503, 504) or limited) and attempt < RETRIES:
                if limited and not e.headers.get("Retry-After"):
                    _wait_for_reset(e.headers, "GitHub's hourly API allowance is used up")
                    continue
                wait = int(e.headers.get("Retry-After") or 0) or 10 * attempt
                print(f"GitHub said {e.code}; trying again in {wait}s ({attempt}/{RETRIES - 1})", file=sys.stderr)
                time.sleep(wait)
                continue
            if e.code == 401:
                sys.exit("GitHub refused the token (401). Check GITHUB_TOKEN is right and not expired.")
            sys.exit(f"GitHub error {e.code} for {req.full_url}: {body}")
        except urllib.error.URLError as e:
            if attempt < RETRIES:
                time.sleep(5 * attempt)
                continue
            sys.exit(f"Couldn't reach {req.full_url}: {e.reason}. Check GITHUB_HOST, the network/VPN, "
                     "or set GITHUB_CA_BUNDLE if it mentions a certificate.")


def _wait_for_reset(headers, why):
    """Sleep until GitHub's rate limit resets (X-RateLimit-Reset, seconds since 1970), then carry on."""
    try:
        reset = int(headers.get("X-RateLimit-Reset") or 0)
    except (TypeError, ValueError):
        reset = 0
    wait = max(reset - int(time.time()), 0) + 5 if reset else 60
    wait = min(wait, MAX_WAIT)
    until = time.strftime("%H:%M", time.localtime(time.time() + wait))
    print(f"{why}: waiting {wait // 60} min {wait % 60} s, until about {until}, then carrying on "
          "(leave this window open)", file=sys.stderr)
    time.sleep(wait)


def graphql(query, variables=None):
    """Run a GraphQL query; returns its "data" part. Waits and tries again when the rate limit is used up;
    stops with GitHub's message for any other error."""
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    for _ in range(MAX_RATE_WAITS + 1):
        req = urllib.request.Request(GRAPHQL_URL, method="POST", data=body)
        req.add_header("Content-Type", "application/json")
        out, headers = _send(req)
        errors = out.get("errors") or []
        limited = any(e.get("type") == "RATE_LIMITED" or "rate limit" in str(e.get("message", "")).lower()
                      for e in errors)
        if limited:
            _wait_for_reset(headers, "GitHub's hourly API allowance is used up")
            continue
        if errors:
            msgs = "; ".join(e.get("message", str(e)) for e in errors)
            if not out.get("data"):
                sys.exit(f"GitHub GraphQL error: {msgs}")
            print(f"GitHub GraphQL warning (some fields missing): {msgs}", file=sys.stderr)
        return out["data"]
    sys.exit("GitHub's rate limit was still used up after waiting several times. Try again later.")


def rest(path, params=None, all_pages=False):
    """GET a REST path such as "/orgs/my-org/repos". With all_pages=True, follows every page and returns one list."""
    url = path if path.startswith("http") else API + "/" + path.lstrip("/")
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    items = []
    while url:
        data, headers = _send(urllib.request.Request(url))
        if not all_pages:
            return data
        items += data if isinstance(data, list) else [data]
        url = None
        for part in (headers.get("Link") or "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip(" <>")
    return items


if __name__ == "__main__":       # quick check:  python github_client.py
    me = graphql("query { viewer { login } }")["viewer"]["login"]
    print(f"Connected to {GRAPHQL_URL} as {me}")
