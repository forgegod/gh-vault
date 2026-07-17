from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .store import StoreError


@dataclass(frozen=True)
class TokenMetadata:
    scopes: tuple[str, ...]
    expires_at: str | None


def inspect_token(token: str) -> TokenMetadata:
    request = Request(
        "https://api.github.com/user",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            scopes = tuple(scope.strip() for scope in response.headers.get("X-OAuth-Scopes", "").split(",") if scope.strip())
            return TokenMetadata(scopes, response.headers.get("GitHub-Authentication-Token-Expiration"))
    except HTTPError as exc:
        raise StoreError(f"cannot inspect GitHub token: GitHub returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise StoreError("cannot inspect GitHub token: GitHub API is unavailable") from exc
