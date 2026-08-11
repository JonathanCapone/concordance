"""External data providers, keyless first.

A public artifact must not depend on its author's API keys, and a contributor
must be able to add a source without writing Python. So a provider is a JSON
file, and the machinery here loads it, fetches it politely, caches it, and can
freeze it into a snapshot the public instance serves.

Three tiers, and the rule attached to each is enforced rather than documented:

    0  keyless          everything core runs on these alone; the public demo
                        uses ONLY these
    1  free, user key   optional enrichment, never required for any feature
    2  paid, user key   never required, ever

The lucky fact that makes tier 0 sufficient: Canadian government open data is
almost entirely keyless. ECCC, StatCan, the Water Survey and open.canada.ca all
answer without credentials.

Degradation is explicit. A provider that is not configured says so, by name,
rather than returning an empty result that renders as an empty map and looks
like "there is no data here".
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

USER_AGENT = "ground-truth/0.1 (open research; see repository)"


class ProviderError(RuntimeError):
    pass


class NeedsCredential(ProviderError):
    """Raised for a tier 1/2 provider with no key supplied.

    A distinct type so callers can tell "you have not configured this" apart
    from "this is broken", and say the right thing to the user.
    """


@dataclass
class Provider:
    name: str
    title: str
    tier: int
    endpoint: str
    publisher: str = ""
    licence: str = ""
    licence_url: str = ""
    auth_mode: str = "none"          # none | header | query
    auth_name: str = ""              # header or query-param name
    env_var: str = ""                # where the user's key is read from
    params: dict[str, str] = field(default_factory=dict)
    rate_limit_seconds: float = 1.0
    notes: str = ""
    verified_at: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Provider":
        auth = d.get("auth") or {}
        return cls(
            name=d["name"],
            title=d.get("title", d["name"]),
            tier=int(d.get("tier", 0)),
            endpoint=d["endpoint"],
            publisher=d.get("publisher", ""),
            licence=d.get("licence", ""),
            licence_url=d.get("licence_url", ""),
            auth_mode=auth.get("mode", "none"),
            auth_name=auth.get("name", ""),
            env_var=auth.get("env_var", ""),
            params=dict(d.get("params") or {}),
            rate_limit_seconds=float(d.get("rate_limit_seconds", 1.0)),
            notes=d.get("notes", ""),
            verified_at=d.get("verified_at", ""),
        )

    @property
    def keyless(self) -> bool:
        return self.tier == 0 and self.auth_mode == "none"

    def validate(self) -> list[str]:
        """Structural problems with the declaration itself."""
        out: list[str] = []
        if self.tier == 0 and self.auth_mode != "none":
            out.append(
                f"{self.name}: declared tier 0 but requires {self.auth_mode} auth; "
                "tier 0 means keyless"
            )
        if self.tier > 0 and not self.env_var:
            out.append(f"{self.name}: tier {self.tier} but no env_var to read a key from")
        if not self.endpoint.startswith("https://"):
            out.append(f"{self.name}: endpoint is not https")
        if self.licence == "":
            out.append(f"{self.name}: no licence recorded — required before redistributing data")
        return out


@dataclass
class Registry:
    providers: dict[str, Provider] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, directory: str | Path = "data/providers") -> "Registry":
        reg = cls()
        d = Path(directory)
        if not d.exists():
            return reg
        for path in sorted(d.glob("*.json")):
            try:
                p = Provider.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:  # noqa: BLE001
                reg.problems.append(f"{path.name}: unreadable ({exc})")
                continue
            reg.problems.extend(p.validate())
            reg.providers[p.name] = p
        return reg

    def tier0(self) -> list[Provider]:
        return [p for p in self.providers.values() if p.keyless]

    def status(self, env: dict[str, str] | None = None) -> list[dict[str, Any]]:
        """What is usable right now, and what a user would have to do.

        The `needs` string is meant to be shown in the interface. An unconfigured
        layer must say "needs a free ECCC key" rather than silently rendering
        nothing, which reads as "there is no data here".
        """
        import os

        env = env if env is not None else dict(os.environ)
        out = []
        for p in sorted(self.providers.values(), key=lambda x: (x.tier, x.name)):
            if p.keyless:
                out.append({"name": p.name, "tier": 0, "usable": True, "needs": None})
            else:
                have = bool(env.get(p.env_var))
                out.append({
                    "name": p.name,
                    "tier": p.tier,
                    "usable": have,
                    "needs": None if have else (
                        f"set {p.env_var} to use {p.title}"
                        + (" (free account)" if p.tier == 1 else " (paid account)")
                    ),
                })
        return out


class Fetcher:
    """Polite, cached HTTP for provider endpoints."""

    def __init__(self, cache_dir: str | Path = "data/cache/providers") -> None:
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self._last_call: dict[str, float] = {}

    def _cache_path(self, provider: Provider, params: dict[str, str]) -> Path:
        import hashlib

        key = provider.name + "?" + urllib.parse.urlencode(sorted(params.items()))
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache / f"{provider.name}_{digest}.json"

    def fetch(
        self,
        provider: Provider,
        params: dict[str, str] | None = None,
        *,
        env: dict[str, str] | None = None,
        force: bool = False,
        timeout: float = 90.0,
    ) -> Any:
        import os

        env = env if env is not None else dict(os.environ)
        merged = {**provider.params, **(params or {})}
        path = self._cache_path(provider, merged)
        if path.exists() and not force:
            return json.loads(path.read_text(encoding="utf-8"))

        headers = {"User-Agent": USER_AGENT}
        if provider.auth_mode != "none":
            key = env.get(provider.env_var, "")
            if not key:
                raise NeedsCredential(
                    f"{provider.title} needs a key in {provider.env_var}. "
                    "This project never requires one: every core feature runs on "
                    "tier-0 keyless sources."
                )
            if provider.auth_mode == "header":
                headers[provider.auth_name] = key
            else:
                merged[provider.auth_name] = key

        # Be a good citizen: these are public services funded by taxpayers, not
        # a CDN, and a tight loop over them is rude regardless of robots.txt.
        elapsed = time.time() - self._last_call.get(provider.name, 0.0)
        if elapsed < provider.rate_limit_seconds:
            time.sleep(provider.rate_limit_seconds - elapsed)

        url = provider.endpoint
        if merged:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(merged)

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"{provider.name}: HTTP {exc.code} from {provider.endpoint}") from exc
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"{provider.name}: {exc}") from exc
        finally:
            self._last_call[provider.name] = time.time()

        data = json.loads(body.decode("utf-8", "replace"))
        path.write_text(json.dumps(data), encoding="utf-8")
        return data


def freeze_snapshot(
    registry: Registry,
    fetcher: Fetcher,
    out_path: str | Path = "data/snapshots/tier0.json",
    *,
    requests: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Capture tier-0 responses into one versioned file for the public instance.

    The demo serves this rather than calling live services: nobody's API gets
    hammered by conference traffic, no key is ever needed, the result is
    reproducible, and it works with the wifi off.
    """
    requests = requests or {}
    snapshot: dict[str, Any] = {"providers": {}, "errors": {}}
    for p in registry.tier0():
        try:
            snapshot["providers"][p.name] = {
                "title": p.title,
                "publisher": p.publisher,
                "licence": p.licence,
                "endpoint": p.endpoint,
                "data": fetcher.fetch(p, requests.get(p.name)),
            }
        except ProviderError as exc:
            snapshot["errors"][p.name] = str(exc)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot), encoding="utf-8")
    return snapshot
