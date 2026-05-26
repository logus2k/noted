"""Chunking-profile catalog + resolver for noted-graph.

This is a small twin of noted-rag's resolver (in noted-rag/app/ingest.py).
Both services keep their own copy of `chunking_profiles.json` so each can
load + validate without a runtime cross-service call. The two files MUST
stay in sync; the JSON is the single source of truth for the profile
catalog, and edits should be applied identically to both copies.

The chunkers in noted-graph (md_scanner, pdf_scanner) call
`resolve_chunking_profile(profile_id_or_none)` to get the effective
{max_tokens, min_tokens, target_tokens, overlap_tokens, id} dict and then
apply whatever of those fields their chunker honours. Docling-style
chunkers honour only `max_tokens`; markdown-style chunkers honour all
four. The catalog is the same; interpretation differs per chunker.
"""

from __future__ import annotations

import functools
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROFILES_PATH = Path(__file__).with_name("chunking_profiles.json")


@functools.lru_cache(maxsize=1)
def load_chunking_profiles() -> dict:
    """Load and validate chunking_profiles.json. Cached for process lifetime.
    Returns:
        {
          "default_profile": "<id>",
          "profiles": {"<id>": {<full profile dict>}, ...},
          "profiles_list": [<full profile dict>, ...],  # original order
        }
    If the JSON is missing, falls back to a single synthetic profile that
    matches noted-graph's historical EXTRACT_CHUNK_* defaults so existing
    behaviour is preserved when no profile is selected.
    """
    if not _PROFILES_PATH.exists():
        logger.warning(
            "%s not found; falling back to synthetic 'prose-balanced' profile",
            _PROFILES_PATH,
        )
        fallback = {
            "id": "prose-balanced",
            "name": "Balanced prose (default)",
            "description": "Module fallback (chunking_profiles.json missing).",
            "max_tokens": 800,
            "min_tokens": 200,
            "target_tokens": 600,
            "overlap_tokens": 80,
        }
        return {
            "default_profile": fallback["id"],
            "profiles": {fallback["id"]: fallback},
            "profiles_list": [fallback],
        }

    raw = json.loads(_PROFILES_PATH.read_text(encoding="utf-8"))
    profiles_list = raw.get("profiles") or []
    default_id = raw.get("default_profile")
    profiles: dict[str, dict] = {}
    seen_ids: set[str] = set()
    for p in profiles_list:
        pid = p.get("id")
        if not pid or not isinstance(pid, str):
            raise ValueError(f"profile missing string 'id': {p!r}")
        if pid in seen_ids:
            raise ValueError(f"duplicate profile id: {pid!r}")
        seen_ids.add(pid)
        for key in ("max_tokens", "min_tokens", "target_tokens", "overlap_tokens"):
            v = p.get(key)
            if not isinstance(v, int) or v < 0:
                raise ValueError(f"profile {pid!r} field {key!r} must be int>=0, got {v!r}")
        if not (p["max_tokens"] >= p["target_tokens"] >= p["min_tokens"]):
            raise ValueError(
                f"profile {pid!r} must satisfy max>=target>=min "
                f"(got max={p['max_tokens']} target={p['target_tokens']} min={p['min_tokens']})"
            )
        if not (0 <= p["overlap_tokens"] < p["target_tokens"]):
            raise ValueError(
                f"profile {pid!r} overlap must satisfy 0<=overlap<target "
                f"(got overlap={p['overlap_tokens']} target={p['target_tokens']})"
            )
        profiles[pid] = p
    if not default_id or default_id not in profiles:
        raise ValueError(
            f"default_profile {default_id!r} not found in profiles {list(profiles)}"
        )
    return {
        "default_profile": default_id,
        "profiles": profiles,
        "profiles_list": profiles_list,
    }


def resolve_chunking_profile(profile_id: str | None) -> dict:
    """Look up a profile by id (or return the default if id is None/empty).
    Raises KeyError if the id is unknown. Returns a dict containing at
    least: id, max_tokens, min_tokens, target_tokens, overlap_tokens."""
    cfg = load_chunking_profiles()
    if profile_id is None or profile_id == "":
        return cfg["profiles"][cfg["default_profile"]]
    if profile_id not in cfg["profiles"]:
        raise KeyError(
            f"unknown chunking profile {profile_id!r}; "
            f"known: {list(cfg['profiles'])}"
        )
    return cfg["profiles"][profile_id]
