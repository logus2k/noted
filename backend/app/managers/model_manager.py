"""ModelManager — runtime CRUD for the local-model fleet hosted by
llama-vision (the llama-server router).

Concerns: per-slot active selection (chat / embed / rerank), load/unload
control via llama-server's /models/load + /unload endpoints, friendly-
name persistence, and surfacing per-model metadata (file size, context,
quantization, state) to the frontend.

NOT concerned with Anthropic backends — those stay in LLMRouter. This
manager only sees the local llama-vision fleet. The chat-active
selection here feeds LLMRouter via `model_manager.active("chat")`
when the user hasn't picked a Claude model.

Persistence: a single JSON file under noted's data/ volume so it
survives container rebuilds. Models themselves are NOT defined here —
they're declared in `agent_server/llama-router-models.ini` (admin-only).
This file only carries what the user can change: which model is active
per slot, and the user-given friendly names.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

LLAMA_SERVER_URL = os.environ.get("LLAMA_SERVER_URL", "http://llama-vision:8500")
REGISTRY_PATH = Path(os.environ.get(
    "MODEL_REGISTRY_PATH",
    "/app/data/model_registry.json",
))

# How long to wait for an async load to complete before raising.
LOAD_TIMEOUT_S = float(os.environ.get("MODEL_LOAD_TIMEOUT_S", "60"))
# How long to wait for an unload (much faster).
UNLOAD_TIMEOUT_S = float(os.environ.get("MODEL_UNLOAD_TIMEOUT_S", "10"))

# Slots the UI exposes. Order matters for the panel layout.
SLOTS = ("chat", "embed", "rerank")

# Synthetic id reported by the router for unconfigured slots; we filter it.
_ROUTER_PLACEHOLDER_ID = "default"


def _classify_slot(args: list[str], preset: str) -> str:
    """Infer slot type from llama-server args/preset.

    pooling=cls + embedding => embed
    pooling=rank + embedding => rerank
    otherwise => chat
    """
    text = " ".join(args).lower() + "\n" + (preset or "").lower()
    if "embedding" in text or "embeddings" in text:
        if re.search(r"pooling\s*[= ]\s*rank", text):
            return "rerank"
        return "embed"
    return "chat"


def _extract_arg(args: list[str], flag: str) -> Optional[str]:
    """Pull the value following a CLI flag (e.g. --model /path)."""
    try:
        idx = args.index(flag)
    except ValueError:
        return None
    return args[idx + 1] if idx + 1 < len(args) else None


_QUANT_RE = re.compile(r"(Q\d_[A-Z0-9_]+|F16|F32|BF16|IQ\d_[A-Z0-9_]+)", re.IGNORECASE)


def _quantization(model_path: Optional[str]) -> Optional[str]:
    if not model_path:
        return None
    m = _QUANT_RE.search(os.path.basename(model_path))
    return m.group(1) if m else None


def _file_size_mb(path: Optional[str]) -> Optional[float]:
    if not path:
        return None
    try:
        # llama-vision sees these paths inside the container; from
        # noted's filesystem they may not exist. The frontend only
        # needs an estimate so we silently skip if absent.
        return round(os.path.getsize(path) / (1024 * 1024), 1)
    except OSError:
        return None


class ModelManager:
    """Singleton-ish helper. Initialise once at app startup."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._http = httpx.Client(
            base_url=LLAMA_SERVER_URL,
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
        )
        self._registry = self._load_registry()
        # Cache file-size + quantization per model_path so we don't
        # stat the disk on every /api/models call. Keyed by model_path.
        self._meta_cache: dict[str, dict] = {}

    # ── Registry persistence ──────────────────────────────────────

    def _load_registry(self) -> dict:
        default = {"active": {s: None for s in SLOTS}, "aliases": {}}
        if not REGISTRY_PATH.exists():
            return default
        try:
            data = json.loads(REGISTRY_PATH.read_text())
            # Defensive: ensure shape
            data.setdefault("active", {})
            data.setdefault("aliases", {})
            for s in SLOTS:
                data["active"].setdefault(s, None)
            return data
        except Exception as e:
            logger.warning("model registry unreadable (%s); using defaults", e)
            return default

    def _save_registry(self) -> None:
        try:
            REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = REGISTRY_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._registry, indent=2))
            tmp.replace(REGISTRY_PATH)
        except Exception as e:
            logger.exception("failed to persist model registry: %s", e)

    # ── llama-vision IO ───────────────────────────────────────────

    def _list_router_models(self) -> list[dict]:
        r = self._http.get("/v1/models")
        r.raise_for_status()
        out = []
        for m in r.json().get("data", []):
            mid = m.get("id")
            if not mid or mid == _ROUTER_PLACEHOLDER_ID:
                continue
            out.append(m)
        return out

    def _get_state(self, model_id: str) -> str:
        for m in self._list_router_models():
            if m.get("id") == model_id:
                return (m.get("status") or {}).get("value", "unknown")
        return "missing"

    def _wait_for_state(self, model_id: str, target: str, timeout_s: float) -> str:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            s = self._get_state(model_id)
            if s == target:
                return s
            if s in ("failed", "missing"):
                return s
            time.sleep(0.2)
        return self._get_state(model_id)

    # ── Public API ────────────────────────────────────────────────

    def _effective_active(self, models: list[dict]) -> dict[str, Optional[str]]:
        """Return active per slot, falling back to the first loaded
        baseline model of that slot type when the user hasn't set one
        explicitly. The fallback is in-memory only — set_active is the
        only operation that persists a choice. This lets the UI show
        "currently effective" baseline without forcing an explicit pick."""
        out: dict[str, Optional[str]] = {}
        for slot in SLOTS:
            chosen = self._registry["active"].get(slot)
            if chosen:
                out[slot] = chosen
                continue
            # Fallback: pick the first loaded baseline matching this slot
            fallback = next(
                (m["id"] for m in models
                 if m["slot_type"] == slot
                 and m.get("is_baseline")
                 and m.get("state") == "loaded"),
                None,
            )
            out[slot] = fallback
        return out

    def list_models(self) -> dict:
        """Return per-model objects + active mapping + aliases.

        Structure matches the contract documented in
        documents/performance/phase_12_models_crud_plan.md."""
        with self._lock:
            router_models = self._list_router_models()
            models = []
            for m in router_models:
                args = (m.get("status") or {}).get("args") or []
                preset = (m.get("status") or {}).get("preset") or ""
                model_path = _extract_arg(args, "--model")
                ctx_size = _extract_arg(args, "--ctx-size") or _extract_arg(args, "-c")
                mmproj = _extract_arg(args, "--mmproj")
                slot = _classify_slot(args, preset)

                # Cache file metadata per path
                cache = self._meta_cache.get(model_path or "") or {}
                if model_path and not cache:
                    cache = {
                        "file_size_mb": _file_size_mb(model_path),
                        "quantization": _quantization(model_path),
                    }
                    self._meta_cache[model_path] = cache

                vram_estimate_mb = None
                if cache.get("file_size_mb") is not None:
                    # Rough: weight bytes + ~10% overhead. Mmproj added if present.
                    vram_estimate_mb = round(cache["file_size_mb"] * 1.1, 1)
                    if mmproj:
                        proj_size = _file_size_mb(mmproj)
                        if proj_size:
                            vram_estimate_mb = round(vram_estimate_mb + proj_size * 1.1, 1)

                is_baseline = "load-on-startup = true" in preset
                state = (m.get("status") or {}).get("value", "unknown")

                mid = m["id"]
                models.append({
                    "id": mid,
                    "friendly_name": self._registry["aliases"].get(mid, mid),
                    "slot_type": slot,
                    "model_path": model_path,
                    "n_ctx": int(ctx_size) if ctx_size and ctx_size.isdigit() else None,
                    "quantization": cache.get("quantization"),
                    "mmproj_path": mmproj,
                    "file_size_mb": cache.get("file_size_mb"),
                    "vram_estimate_mb": vram_estimate_mb,
                    "is_baseline": is_baseline,
                    "state": state,
                })
            active = self._effective_active(models)
            return {
                "models": models,
                "active": active,
                "active_explicit": dict(self._registry["active"]),  # raw user choices (None = default to baseline)
                "aliases": dict(self._registry["aliases"]),
            }

    def health(self) -> dict:
        """Lightweight: just the active mapping + per-slot state. For
        status-bar polling. Falls back to baseline when no explicit
        choice is set, mirroring list_models()."""
        with self._lock:
            # Need a brief metadata pass to know which baseline matches
            # each slot. Cheap (1 HTTP call to llama-vision /v1/models).
            router_models = self._list_router_models()
            slim_models = []
            for m in router_models:
                args = (m.get("status") or {}).get("args") or []
                preset = (m.get("status") or {}).get("preset") or ""
                slim_models.append({
                    "id": m["id"],
                    "slot_type": _classify_slot(args, preset),
                    "is_baseline": "load-on-startup = true" in preset,
                    "state": (m.get("status") or {}).get("value", "unknown"),
                })
            active = self._effective_active(slim_models)
            states: dict[str, str] = {}
            for slot, mid in active.items():
                states[slot] = self._get_state(mid) if mid else "unset"
            return {
                "active": active,
                "active_explicit": dict(self._registry["active"]),
                "states": states,
            }

    def load(self, model_id: str) -> dict:
        """Tell the router to load `model_id`. Blocks until loaded or
        timeout. Returns {state: "...", elapsed_s: ...}."""
        with self._lock:
            t0 = time.time()
            try:
                r = self._http.post("/models/load", json={"model": model_id})
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                # Already loaded is fine
                if e.response.status_code == 400 and "already running" in e.response.text:
                    return {"state": "loaded", "elapsed_s": 0.0, "noop": True}
                raise
            state = self._wait_for_state(model_id, "loaded", LOAD_TIMEOUT_S)
            elapsed = round(time.time() - t0, 2)
            return {"state": state, "elapsed_s": elapsed}

    def unload(self, model_id: str) -> dict:
        """Tell the router to unload `model_id`. Refuses if `model_id`
        is the active model for any slot — caller must switch active
        first. Refuses for baseline models (load-on-startup = true)."""
        with self._lock:
            # Find the model entry to check baseline
            for m in self._list_router_models():
                if m.get("id") == model_id:
                    preset = (m.get("status") or {}).get("preset") or ""
                    if "load-on-startup = true" in preset:
                        raise PermissionError(
                            f"{model_id} is a baseline model (load-on-startup); "
                            "edit llama-router-models.ini to change."
                        )
                    break
            else:
                raise LookupError(f"{model_id} not in router")

            for slot, active_id in self._registry["active"].items():
                if active_id == model_id:
                    raise PermissionError(
                        f"{model_id} is currently the active {slot} model; "
                        "switch active first before unloading."
                    )

            t0 = time.time()
            r = self._http.post("/models/unload", json={"model": model_id})
            r.raise_for_status()
            state = self._wait_for_state(model_id, "unloaded", UNLOAD_TIMEOUT_S)
            return {"state": state, "elapsed_s": round(time.time() - t0, 2)}

    def set_active(self, slot: str, model_id: str) -> dict:
        """Set `model_id` as the active model for `slot`. Validates that
        model exists, slot type matches, and auto-loads if not loaded."""
        if slot not in SLOTS:
            raise ValueError(f"unknown slot {slot!r}; use one of {SLOTS}")
        with self._lock:
            # Validate model exists + slot type
            target = None
            for m in self._list_router_models():
                if m.get("id") == model_id:
                    target = m
                    break
            if not target:
                raise LookupError(f"model {model_id!r} not in router")
            args = (target.get("status") or {}).get("args") or []
            preset = (target.get("status") or {}).get("preset") or ""
            inferred = _classify_slot(args, preset)
            if inferred != slot:
                raise ValueError(
                    f"model {model_id!r} is a {inferred} model, not {slot}"
                )
            # Auto-load if not loaded
            state = (target.get("status") or {}).get("value")
            if state != "loaded":
                self.load(model_id)  # blocking
            self._registry["active"][slot] = model_id
            self._save_registry()
            return {"slot": slot, "active": model_id}

    def set_friendly_name(self, model_id: str, friendly_name: Optional[str]) -> dict:
        """Update the user-visible name. Empty/None clears the alias
        (UI falls back to model id)."""
        with self._lock:
            if not friendly_name:
                self._registry["aliases"].pop(model_id, None)
            else:
                self._registry["aliases"][model_id] = friendly_name.strip()
            self._save_registry()
            return {"id": model_id,
                    "friendly_name": self._registry["aliases"].get(model_id, model_id)}

    def get_active(self, slot: str) -> Optional[str]:
        """Return the active model id for `slot`, or None if unset."""
        with self._lock:
            return self._registry["active"].get(slot)

    def close(self) -> None:
        try:
            self._http.close()
        except Exception:
            pass


# Singleton for the FastAPI app to import.
_singleton: Optional[ModelManager] = None
_singleton_lock = threading.Lock()


def get_model_manager() -> ModelManager:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = ModelManager()
    return _singleton
