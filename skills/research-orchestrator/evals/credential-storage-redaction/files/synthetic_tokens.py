"""Deliberately fake format probes, constructed only when the local test runs."""


def tokens():
    return ["github_pat_" + "aB9_" * 20, "ASIA" + "A1" * 8]


def secret_fragments():
    return ["PrivateBody6543210", "SplitToken9753"]


def boundary_chunks():
    pem, token = secret_fragments()
    return ["safe diagnostic\n" * 700, "-----BEGIN PRIVATE KEY-----\n",
            (pem * 9 + "\n") * 500, "-----END PRIVATE KEY-----\n",
            "github_", "pat_", token * 8000, "\n"]
