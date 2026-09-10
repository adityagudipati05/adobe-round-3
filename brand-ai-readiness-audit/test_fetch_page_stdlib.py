"""
test_fetch_page_stdlib.py — stdlib-only unit tests for the crawl-render-audit
fetch layer (skills/crawl-render-audit/scripts/fetch_page.py).

Covers two regressions found by manual review:

  Bug 1 — _is_bot_blocked() computed a header signal and threw it away, and
          hard-excluded every HTTP 200 response from ever being flagged. Real
          WAF/CDN JS-challenge pages (Cloudflare "Checking your browser",
          Akamai, Sucuri) are routinely served with status 200.

  Bug 2 — _extract_internal_links() returned list(set(...)), so page-discovery
          order depended on per-process string hash randomization. Which subset
          of pages gets crawled (discovered links > max_pages) could differ
          run-to-run for identical content.

No network access: requests.Response is faked with unittest.mock.

Run from brand-ai-readiness-audit/:
    python test_fetch_page_stdlib.py
"""

import json
import os
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FP_DIR = os.path.join(_HERE, "skills", "crawl-render-audit", "scripts")
if _FP_DIR not in sys.path:
    sys.path.insert(0, _FP_DIR)

import fetch_page as fp  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402


class _FakeResponse:
    """Minimal stand-in for requests.Response for _is_bot_blocked()."""

    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.url = "https://example.com/"


# ── Bug 1: _is_bot_blocked ────────────────────────────────────────────────────

CHALLENGE_BODY = (
    "<html><head><title>Just a moment...</title></head><body>"
    "<h1>Checking your browser before accessing example.com</h1>"
    "<p>This process is automatic. Your browser will redirect shortly.</p>"
    "</body></html>"
)

ORDINARY_BODY = (
    "<html><head><title>Acme Corp</title></head><body>"
    "<h1>Acme Corp</h1><p>We build accounting software for small teams. "
    "Founded 2011, trusted by thousands of businesses worldwide.</p>"
    "</body></html>"
)

# Ordinary marketing copy that talks around bot-protection without matching the
# BOT_BLOCK_BODY_RE pattern set. NOTE: the regex intentionally matches the bare
# token "captcha", so this sanity check deliberately avoids that literal — the
# point is that thematically-adjacent prose must NOT be treated as a challenge.
MARKETING_BODY = (
    "<html><head><title>ShieldKit</title></head><body>"
    "<h1>Stop automated sign-up abuse</h1>"
    "<p>ShieldKit helps product teams reduce fake accounts and spam without "
    "annoying real users. No puzzles, no friction.</p>"
    "</body></html>"
)


class TestIsBotBlocked(unittest.TestCase):

    def test_200_with_checking_your_browser_body_is_blocked(self):
        """HTTP 200 + 'checking your browser before accessing' body → True."""
        resp = _FakeResponse(status_code=200, text=CHALLENGE_BODY)
        self.assertTrue(
            fp._is_bot_blocked(resp),
            "A 200-status Cloudflare 'Checking your browser' page must be "
            "flagged as bot-blocked",
        )

    def test_200_with_cf_mitigated_header_and_challenge_body_is_blocked(self):
        """HTTP 200 + cf-mitigated header + JS-challenge body → True."""
        resp = _FakeResponse(
            status_code=200,
            text=CHALLENGE_BODY,
            headers={"cf-mitigated": "challenge", "content-type": "text/html"},
        )
        self.assertTrue(fp._is_bot_blocked(resp))

    def test_200_with_cf_mitigated_header_but_ordinary_body_is_not_blocked(self):
        """HTTP 200 + cf-mitigated header + ordinary body → False.

        A bot-block signature header on its own must never trigger a false
        positive ("header alone is not enough").
        """
        resp = _FakeResponse(
            status_code=200,
            text=ORDINARY_BODY,
            headers={"cf-mitigated": "challenge"},
        )
        self.assertFalse(fp._is_bot_blocked(resp))

    def test_200_ordinary_marketing_page_is_not_blocked(self):
        """HTTP 200 + ordinary marketing copy → False (regex not over-eager)."""
        resp = _FakeResponse(status_code=200, text=MARKETING_BODY, headers={})
        self.assertFalse(fp._is_bot_blocked(resp))

    def test_403_still_blocked_no_regression(self):
        """Sanity: a plain 403 is still treated as a bot-block."""
        resp = _FakeResponse(status_code=403, text="Access denied")
        self.assertTrue(fp._is_bot_blocked(resp))


# ── Bug 2: _extract_internal_links order stability ────────────────────────────

_LINK_HTML = """<html><body>
  <a href="/zebra">z</a>
  <a href="/alpha">a</a>
  <a href="/mango">m</a>
  <a href="/delta">d</a>
  <a href="/beta">b</a>
  <a href="/alpha">alpha again (dup)</a>
  <a href="https://external.example.org/x">external</a>
  <a href="#section">fragment only</a>
  <a href="mailto:hi@example.com">mail</a>
</body></html>"""

_BASE_URL = "https://example.com/"

_EXPECTED_LINKS = [
    "https://example.com/zebra",
    "https://example.com/alpha",
    "https://example.com/mango",
    "https://example.com/delta",
    "https://example.com/beta",
]


class TestExtractInternalLinksOrder(unittest.TestCase):

    def test_in_process_order_is_dom_order_and_stable(self):
        soup1 = BeautifulSoup(_LINK_HTML, "html.parser")
        soup2 = BeautifulSoup(_LINK_HTML, "html.parser")
        first = fp._extract_internal_links(soup1, _BASE_URL)
        second = fp._extract_internal_links(soup2, _BASE_URL)

        self.assertEqual(first, _EXPECTED_LINKS,
                         "links must be returned in first-seen DOM order, "
                         "de-duplicated")
        self.assertEqual(first, second,
                         "repeated calls in the same process must be identical")

    def test_order_is_stable_across_hash_seeds(self):
        """
        Run the extractor in fresh subprocesses with different PYTHONHASHSEED
        values. A set-based implementation would (often) reorder; the fixed
        implementation must produce byte-identical output every time.
        """
        child = (
            "import json, sys, os;"
            "sys.path.insert(0, os.environ['FP_DIR']);"
            "import fetch_page as fp;"
            "from bs4 import BeautifulSoup;"
            "html = os.environ['LINK_HTML'];"
            "soup = BeautifulSoup(html, 'html.parser');"
            "print(json.dumps(fp._extract_internal_links(soup, 'https://example.com/')))"
        )
        env_base = dict(os.environ, FP_DIR=_FP_DIR, LINK_HTML=_LINK_HTML,
                        PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

        outputs = []
        for seed in ("0", "1", "42", "1000"):
            env = dict(env_base, PYTHONHASHSEED=seed)
            res = subprocess.run(
                [sys.executable, "-c", child],
                capture_output=True, text=True, env=env, cwd=_HERE,
            )
            self.assertEqual(res.returncode, 0,
                             f"child failed (seed={seed}): {res.stderr}")
            outputs.append(res.stdout.strip())

        for out in outputs:
            self.assertEqual(json.loads(out), _EXPECTED_LINKS)
        self.assertEqual(len(set(outputs)), 1,
                         f"output varied across hash seeds: {outputs}")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
