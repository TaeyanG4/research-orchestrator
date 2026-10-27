"""Shared, stdlib-only publication boundary for evidence and release checks."""
from __future__ import annotations

import hashlib
import base64
import binascii
import os
import re

# No leading word boundary: source fragments such as Path(rX:/...) are paths too.
HOST_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/]+|(?<![\w/\\])\\\\[^\\\s]+\\|/(?:home|Users|tmp|private|mnt|workspace)/|~[\\/])"
    r"[^\s\"'<>`|;,\]\[){}]*", re.I)
SESSION_ID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|\btoolu_[A-Za-z0-9]+", re.I)
INTERNAL = re.compile(
    r'"(?:session_id|thread_id|available_skills|installed_skills|installed_plugins|plugins_inventory|rate_limits)"\s*:'
    r'|"type"\s*:\s*"(?:thread\.(?:started|resumed)|turn\.(?:started|completed|failed)|item\.(?:started|completed))"'
    r'|<available_skills>|"(?:five_hour|seven_day)"\s*:'
    r'|^(?:installed (?:skills|plugins)|account utili[sz]ation)\s*:', re.I | re.M)
# Captured host output in tests/fixtures/, examples/ and eval files may keep the
# *shape* of a native identifier, but only with an obviously synthetic value.
NATIVE_ID_FIELD = re.compile(
    r"(?<![a-z])(?:thread|session|conversation|turn|request)[ _-]?id(?![a-z])(?:\\?[\"'])?\s*[:=]\s*(?:\\?[\"'])?"
    r"(?P<value>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{32})(?![0-9a-f-])", re.I)
# Allow-list: all-zero UUIDs with a version/variant nibble and a counter of at
# most four hex digits (00000000-0000-7000-8000-000000000001), plus the
# documented sequential placeholder.
SYNTHETIC_ID = re.compile(
    r"0{8}-0{4}-[0-9a-f]0{3}-[0-9a-f]0{3}-0{8}[0-9a-f]{4}|0{28}[0-9a-f]{4}"
    r"|01234567-89ab-cdef-0123-456789abcdef|0123456789abcdef0123456789abcdef", re.I)
RAW_MEMBER = re.compile(r"(?:^|/)(?:[^/]*(?:transcript|events)[^/]*\.(?:md|jsonl|json|txt)|stderr\.txt|review\.html)$", re.I)
URL = re.compile(r"\b(?:https?|wss?|ftp|ssh|git|plugin|app)://[^\s\"'<>`]+", re.I)
BASE64_TOKEN = re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{40,}={0,2}(?![A-Za-z0-9+/_=-])")


def decode_base64_text(token: str) -> str | None:
    """Inspect textual captures, including PowerShell's UTF-16-LE streams."""
    try:
        raw = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
    except (ValueError, binascii.Error):
        return None
    # Hex digests also match the token alphabet. Arbitrary binary interpreted as
    # UTF-16 can look like printable CJK, so require a BOM or a text NUL pattern.
    utf16 = raw.startswith(b'\xff\xfe') or (len(raw) % 2 == 0 and
        sum(byte == 0 for byte in raw[1::2]) >= max(2, len(raw) // 8))
    encodings = ('utf-16-le', 'utf-8-sig') if utf16 else ('utf-8-sig',)
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
        except UnicodeError:
            continue
        if text and all(char.isprintable() or ord(char) < 32 or char == '\ufeff' for char in text):
            return text
    return None


def expanded_text(text: str) -> str:
    """Add decoded views before scanning; each layer is smaller than its input."""
    decoded = [value for match in BASE64_TOKEN.finditer(text)
               if (value := decode_base64_text(match[0])) is not None]
    return '\n'.join([text, *(expanded_text(value) for value in decoded)])


def private_terms() -> tuple[str, ...]:
    """Detect this host's account names without embedding them in the package."""
    values = [os.environ.get("USERNAME", ""), os.environ.get("USER", "")]
    for key in ("USERPROFILE", "HOME"):
        home = os.environ.get(key, "").replace("\\", "/").rstrip("/")
        if home and re.search(r"/(?:Users|home)/", home, re.I):
            values.append(home.rsplit("/", 1)[-1])
    return tuple(value for value in set(values) if len(value) > 3 and value.lower() not in {"root", "user", "runner"})


def sanitize_text(value: str, terms: tuple[str, ...] = ()) -> str:
    # Encoded captures are execution internals, not useful published prose.
    value = BASE64_TOKEN.sub(lambda match: '<withheld encoded text>'
                            if decode_base64_text(match[0]) is not None else match[0], value)
    def replace(match):
        normalized = re.sub(r"[\\/]+", "/", match[0]).casefold()
        return "<host-path-" + hashlib.sha256(normalized.encode()).hexdigest()[:12] + ">"
    urls = []
    def save_url(match):
        urls.append(match[0])
        return f"<public-url-{len(urls) - 1}>"
    value = URL.sub(save_url, value)
    value = HOST_PATH.sub(replace, value)
    value = SESSION_ID.sub("<withheld-id>", value)
    for term in (*private_terms(), *terms):
        if term:
            value = re.sub(re.escape(term), "<private-host>", value, flags=re.I)
    # Embedded log fragments in grading prose are not required to reconstruct scores.
    value = "\n".join("<withheld internal metadata>" if INTERNAL.search(line) else line
                      for line in value.split("\n"))
    for index, url in enumerate(urls):
        value = value.replace(f"<public-url-{index}>", url)
    return value


def native_identifiers(text: str) -> list[str]:
    """Return non-synthetic values of native identifier fields (thread/session/request ids)."""
    return [match["value"] for match in NATIVE_ID_FIELD.finditer(text)
            if not SYNTHETIC_ID.fullmatch(match["value"])]


def violations(text: str, *, terms: tuple[str, ...] = ()) -> list[str]:
    checks = [("absolute host path", HOST_PATH), ("native session/tool identifier", SESSION_ID),
              ("internal session event or inventory", INTERNAL)]
    found = [label for label, pattern in checks if pattern.search(URL.sub("<url>", text))]
    if any(term and re.search(re.escape(term), text, re.I) for term in (*private_terms(), *terms)):
        found.append("private account name")
    return found
