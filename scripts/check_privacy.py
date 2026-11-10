"""Fail if the project introduces auth, analytics, telemetry or third-party font loading.

Enforces the approved rules: no authentication, no user data, no analytics,
no telemetry, self-hosted fonts. Standard library only.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Dependency names that must never appear in manifests.
BANNED_DEPENDENCIES = [
    "next-auth", "@auth/", "auth0", "passport", "clerk", "firebase", "supabase",
    "fastapi-users", "python-jose", "pyjwt", "passlib", "authlib", "itsdangerous",
    "@vercel/analytics", "@vercel/speed-insights", "react-ga", "gtag", "posthog",
    "mixpanel", "segment", "amplitude", "sentry", "datadog", "logrocket", "hotjar",
    "plausible", "matomo", "opentelemetry",
]  # fmt: skip

MANIFESTS = [
    "web/package.json",
    "api/requirements.txt",
    "api/requirements-dev.txt",
    "worker/requirements.txt",
    "worker/requirements-dev.txt",
]

# Strings that must never appear in web source (third-party fonts / trackers).
BANNED_SOURCE_PATTERNS = [
    r"fonts\.googleapis\.com", r"fonts\.gstatic\.com", r"next/font/google",
    r"googletagmanager", r"google-analytics", r"<script[^>]+src=[\"']https?://",
]  # fmt: skip

SOURCE_GLOBS = ["web/app/**/*", "web/components/**/*", "web/lib/**/*", "web/next.config.ts"]


def main() -> int:
    errors: list[str] = []

    for rel in MANIFESTS:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for banned in BANNED_DEPENDENCIES:
            if banned in text:
                errors.append(f"{rel}: banned dependency pattern '{banned}'")

    for pattern in SOURCE_GLOBS:
        for path in ROOT.glob(pattern):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for banned in BANNED_SOURCE_PATTERNS:
                if re.search(banned, text):
                    errors.append(f"{path.relative_to(ROOT)}: banned pattern '{banned}'")

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    in_ports = False
    for line in compose.splitlines():
        stripped = line.strip()
        if stripped == "ports:":
            in_ports = True
            continue
        if in_ports:
            if stripped.startswith("-"):
                if "127.0.0.1:" not in stripped:
                    errors.append(f"docker-compose.yml: port not bound to 127.0.0.1: {stripped}")
            elif stripped and not stripped.startswith("#"):
                in_ports = False

    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("privacy check OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
