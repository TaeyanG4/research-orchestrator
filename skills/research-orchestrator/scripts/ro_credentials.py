"""Shared built-in credential recognition for publication scans and stored diagnostics.

Assignments count only with secret-shaped values: a quoted literal that is not a placeholder, or an
unquoted 20+ character token mixing letters and digits that is not an identifier chain, a call or a
snake_case constant. Code such as `password = self.config.password`, `secret = settings.SECRET` or
`password = getpass.getpass()` is not a credential.
"""

_KEY = r"(?i:\b(?:\w*_)?(?:api[_-]?key|secret|password|passwd|access[_-]?token)\b)[\"']?\s{0,16}[=:]\s{0,16}"
_PLACEHOLDER = r"(?i:x{3,}|\*{3,}|\.{3,}|changeme|change[_-]me|placeholder|example|dummy|redacted|your[_-])"

SECRET_PATTERNS = (
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
    r"\bgithub_pat_[A-Za-z0-9_]{20,}\b",
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])",
    # Quoted literal: not a template, variable or placeholder.
    _KEY + r"([\"'])(?![$%{<]|" + _PLACEHOLDER + r")[^\"'\s$%{}<>]{8,255}\1",
    # Unquoted token: letters and digits, 20+ characters, not followed by attribute access or a call.
    _KEY + r"(?![A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b|[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b)"
    r"(?=[A-Za-z0-9_+/=-]*\d)(?=[A-Za-z0-9_+/=-]*[A-Za-z])[A-Za-z0-9_+/=-]{20,255}(?![A-Za-z0-9_+/=.(\[-])",
    # Hexadecimal keys of 32+ digits, quoted or not.
    _KEY + r"[\"']?(?:[0-9a-f]{32,128}|[0-9A-F]{32,128})(?![0-9A-Za-z])",
)
