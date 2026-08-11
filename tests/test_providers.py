"""Tests for the provider layer.

The invariant that matters: this project must be fully usable by someone who has
no API keys and never obtains any. Tier 0 is not a convenience, it is a promise,
and these tests are what stop it eroding one convenient exception at a time.

Nothing here touches the network. Fetch behaviour is exercised against the cache
and against fake credentials, so the suite stays fast and works offline.
"""

from __future__ import annotations

import json

import pytest

from groundtruth.providers import (
    Fetcher,
    NeedsCredential,
    Provider,
    Registry,
)


def _decl(**over):
    d = {
        "name": "x", "title": "X", "tier": 0,
        "endpoint": "https://example.test/api",
        "licence": "Open Government Licence - Canada",
        "auth": {"mode": "none"},
    }
    d.update(over)
    return d


# -- the tier promise --------------------------------------------------------

def test_tier0_declaring_auth_is_a_declaration_error():
    """Tier 0 means keyless. A tier-0 provider that needs a key is the exact
    erosion this check exists to catch."""
    p = Provider.from_dict(_decl(auth={"mode": "header", "name": "K", "env_var": "K"}))
    problems = p.validate()
    assert any("tier 0 means keyless" in x for x in problems)


def test_keyed_provider_must_say_where_the_key_comes_from():
    p = Provider.from_dict(_decl(tier=1, auth={"mode": "header", "name": "K"}))
    assert any("no env_var" in x for x in p.validate())


def test_provider_without_a_licence_is_flagged():
    """Redistributing data without recording its licence is not acceptable."""
    p = Provider.from_dict(_decl(licence=""))
    assert any("licence" in x for x in p.validate())


def test_plain_http_endpoint_is_rejected():
    p = Provider.from_dict(_decl(endpoint="http://example.test/api"))
    assert any("not https" in x for x in p.validate())


# -- the shipped registry ----------------------------------------------------

def test_shipped_providers_are_all_declared_correctly():
    reg = Registry.load("data/providers")
    assert reg.providers, "no providers found"
    assert reg.problems == [], f"declaration problems: {reg.problems}"


def test_every_core_source_is_keyless():
    """If this fails, someone has made a real feature depend on a credential."""
    reg = Registry.load("data/providers")
    core = [p for p in reg.providers.values() if not p.name.startswith("example")]
    assert core, "no non-example providers"
    assert all(p.keyless for p in core), (
        "these are not keyless: "
        + ", ".join(p.name for p in core if not p.keyless)
    )


# -- degradation is explicit -------------------------------------------------

def test_unconfigured_provider_says_what_to_do():
    """An unconfigured layer must not render as an empty map, which reads to a
    user as 'there is no data here'."""
    reg = Registry.load("data/providers")
    status = {s["name"]: s for s in reg.status(env={})}
    ex = status.get("example-tier1-source")
    assert ex is not None and not ex["usable"]
    assert "EXAMPLE_API_KEY" in ex["needs"]


def test_keyless_providers_are_usable_with_no_environment_at_all():
    reg = Registry.load("data/providers")
    for s in reg.status(env={}):
        if s["tier"] == 0:
            assert s["usable"] and s["needs"] is None


def test_missing_credential_raises_a_distinct_error(tmp_path):
    """Callers must be able to tell 'you have not configured this' apart from
    'this is broken', because the user-facing message differs."""
    p = Provider.from_dict(
        _decl(tier=1, auth={"mode": "header", "name": "K", "env_var": "ABSENT_KEY"})
    )
    f = Fetcher(cache_dir=tmp_path)
    with pytest.raises(NeedsCredential) as exc:
        f.fetch(p, env={})
    assert "ABSENT_KEY" in str(exc.value)
    assert "never requires one" in str(exc.value)


# -- caching -----------------------------------------------------------------

def test_cache_is_served_without_network(tmp_path):
    p = Provider.from_dict(_decl())
    f = Fetcher(cache_dir=tmp_path)
    path = f._cache_path(p, p.params)
    path.write_text(json.dumps({"hello": "cached"}), encoding="utf-8")
    assert f.fetch(p)["hello"] == "cached"


def test_different_params_cache_separately(tmp_path):
    p = Provider.from_dict(_decl())
    f = Fetcher(cache_dir=tmp_path)
    a = f._cache_path(p, {"limit": "10"})
    b = f._cache_path(p, {"limit": "20"})
    assert a != b, "a differing query must not read another query's cache"
