"""ECharts option builders for the in-chat chart tool.

This module is the deterministic half of the charts pipeline:
    user request → chart_designer LLM → ChartIntent JSON → THIS MODULE
                                                          → ECharts option dict
                                                          → SSE event to chat

The LLM half is in `agent_server/data/agents/chart_designer.agent.json` +
`agent_server/data/prompts/chart_designer_system_prompt.txt`. This module
NEVER touches data values that came from the LLM beyond intent fields
(chart_type, column names, agg). Actual data values come from the
resolved data source (project file, prior tool result) — the LLM cannot
fabricate numbers into the chart.

Public entrypoint: `build_chart_option(intent, project_root)` returns
`{ok: bool, option: dict | None, title: str, error: str | None}`.

Supported chart types (CHART-2 v1): bar, line, area, pie, scatter,
histogram, box. Heatmap deferred to v2 (matrix-shaped data needs more
careful handling). Adding a new chart type = one entry in `_BUILDERS`.

See documents/backlog/product_backlog.md sections CHART-2..7.
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

logger = logging.getLogger(__name__)


# ── Schema constants ─────────────────────────────────────────────────────


_VALID_CHART_TYPES = {
    "bar", "line", "area", "pie", "scatter",
    "histogram", "box", "heatmap",
}
_VALID_AGGS = {"sum", "mean", "median", "min", "max", "count", None}
_VALID_DATA_KINDS = {"inline", "project_file", "prior_result"}

# Soft cap before we down-sample. Charts past ~5k points become noise
# anyway; ECharts can handle more but it slows rendering and the visual
# value drops.
_SAMPLE_THRESHOLD = 5000

# Per-type column requirements: {chart_type: required_intent_fields}
# `inline` data source skips column validation since the values arrive
# pre-shaped with x/y keys.
_REQUIRED_FIELDS = {
    "bar":       {"x", "y"},
    "line":      {"x", "y"},
    "area":      {"x", "y"},
    "scatter":   {"x", "y"},
    "histogram": {"y"},
    "box":       {"y"},
    "pie":       {"category", "value"},
    "heatmap":   {"x", "y", "value"},
}


# ── Intent validation ────────────────────────────────────────────────────


def validate_intent(intent: dict) -> tuple[bool, str | None]:
    """Cheap structural validation. Returns (ok, error)."""
    if not isinstance(intent, dict):
        return False, "intent must be a JSON object"

    chart_type = intent.get("chart_type")
    if chart_type not in _VALID_CHART_TYPES:
        return False, f"chart_type must be one of {sorted(_VALID_CHART_TYPES)}; got {chart_type!r}"

    ds = intent.get("data_source") or {}
    kind = ds.get("kind")
    if kind not in _VALID_DATA_KINDS:
        return False, f"data_source.kind must be one of {sorted(_VALID_DATA_KINDS)}; got {kind!r}"

    if kind == "inline":
        values = ds.get("values")
        if not isinstance(values, list) or not values:
            return False, "data_source.values must be a non-empty list for kind='inline'"
    elif kind == "project_file":
        if not ds.get("project_id") or not ds.get("path"):
            return False, "data_source.project_id and data_source.path are required for kind='project_file'"
    elif kind == "prior_result":
        if not ds.get("result_id"):
            return False, "data_source.result_id required for kind='prior_result'"

    agg = intent.get("agg")
    if agg not in _VALID_AGGS:
        return False, f"agg must be one of {sorted(a for a in _VALID_AGGS if a is not None) + ['null']}; got {agg!r}"

    return True, None


# ── Data source resolution ───────────────────────────────────────────────


def _safe_join(root: str, rel: str) -> str | None:
    """Join `rel` onto `root` and reject anything that escapes the root.
    Returns the absolute path, or None on rejection."""
    abs_root = os.path.realpath(root)
    abs_path = os.path.realpath(os.path.join(abs_root, rel))
    if not abs_path.startswith(abs_root + os.sep) and abs_path != abs_root:
        return None
    return abs_path


def _resolve_project_file(intent_ds: dict, projects_root: str):
    """Load a project-relative CSV / Parquet / JSON file into a pandas
    DataFrame. Returns (df, error_str). df is None on error."""
    import pandas as pd

    project_id = intent_ds.get("project_id") or ""
    rel = intent_ds.get("path") or ""
    if not project_id or not rel:
        return None, "data_source.project_id and data_source.path required"

    project_root = os.path.join(projects_root, project_id)
    if not os.path.isdir(project_root):
        return None, f"unknown project: {project_id!r}"

    abs_path = _safe_join(project_root, rel)
    if abs_path is None:
        return None, f"path escapes project root: {rel!r}"
    if not os.path.isfile(abs_path):
        return None, f"file not found in project {project_id!r}: {rel!r}"

    ext = os.path.splitext(abs_path)[1].lower()
    try:
        if ext == ".csv":
            df = pd.read_csv(abs_path)
        elif ext in (".tsv",):
            df = pd.read_csv(abs_path, sep="\t")
        elif ext in (".parquet", ".pq"):
            df = pd.read_parquet(abs_path)
        elif ext == ".json":
            df = pd.read_json(abs_path)
        elif ext == ".jsonl":
            df = pd.read_json(abs_path, lines=True)
        else:
            return None, f"unsupported file extension: {ext!r} (CSV/TSV/Parquet/JSON/JSONL)"
    except Exception as e:
        return None, f"failed to read {rel}: {type(e).__name__}: {e}"
    return df, None


def _resolve_inline(intent_ds: dict):
    """Inline data: convert list-of-dicts into a pandas DataFrame."""
    import pandas as pd
    values = intent_ds.get("values") or []
    try:
        df = pd.DataFrame(values)
    except Exception as e:
        return None, f"inline values not tabular: {type(e).__name__}: {e}"
    if df.empty:
        return None, "inline values produced an empty table"
    return df, None


def resolve_data(intent: dict, projects_root: str):
    """Dispatch on data_source.kind. Returns (df, error_str)."""
    ds = intent.get("data_source") or {}
    kind = ds.get("kind")
    if kind == "inline":
        return _resolve_inline(ds)
    if kind == "project_file":
        return _resolve_project_file(ds, projects_root)
    if kind == "prior_result":
        return None, "data_source kind='prior_result' is not yet implemented"
    return None, f"unknown data_source.kind: {kind!r}"


# ── Aggregation + sampling ───────────────────────────────────────────────


def _validate_columns(df, *cols: str | None) -> str | None:
    """Returns an error string if any non-None column name is missing."""
    missing = [c for c in cols if c and c not in df.columns]
    if missing:
        return f"column(s) not in dataset: {missing}; available: {list(df.columns)}"
    return None


def _apply_agg(df, x: str, y: str, agg: str | None, series: str | None = None):
    """Group `df` by `x` (and optionally `series`) and aggregate `y`.
    Returns the reshaped DataFrame; if agg is None and there are no
    duplicate x values, returns df unchanged."""
    if agg is None:
        return df
    group_cols = [x] + ([series] if series else [])
    grouped = df.groupby(group_cols, dropna=False, sort=False)
    if agg == "count":
        out = grouped[y].count().reset_index()
    else:
        out = grouped[y].agg(agg).reset_index()
    return out


def _maybe_sample(df, threshold: int = _SAMPLE_THRESHOLD):
    """Down-sample to a manageable size for chart rendering."""
    if len(df) <= threshold:
        return df, False
    sampled = df.sample(n=threshold, random_state=42).sort_index()
    return sampled, True


def _maybe_top_n(df, value_col: str, limit: int | None):
    """Truncate to top-N rows by value_col descending."""
    if limit is None or limit <= 0 or len(df) <= limit:
        return df
    return df.nlargest(limit, value_col)


# ── Per-chart-type ECharts builders ──────────────────────────────────────


def _build_bar(intent: dict, df) -> tuple[dict | None, str | None]:
    x, y, agg, series, limit = intent.get("x"), intent.get("y"), intent.get("agg"), intent.get("series"), intent.get("limit")
    err = _validate_columns(df, x, y, series)
    if err:
        return None, err
    df = _apply_agg(df, x, y, agg, series)
    df = _maybe_top_n(df, y, limit)
    if series:
        # Multi-series: pivot wide, one column per series value.
        pivoted = df.pivot(index=x, columns=series, values=y).fillna(0)
        x_vals = pivoted.index.astype(str).tolist()
        ser_list = []
        for col in pivoted.columns:
            ser_list.append({"name": str(col), "type": "bar", "data": _to_jsonable_list(pivoted[col].tolist())})
    else:
        x_vals = df[x].astype(str).tolist()
        ser_list = [{"type": "bar", "data": _to_jsonable_list(df[y].tolist())}]
    return _wrap_axis_chart(intent, x_vals, ser_list), None


def _build_line(intent: dict, df, area: bool = False) -> tuple[dict | None, str | None]:
    x, y, agg, series, limit = intent.get("x"), intent.get("y"), intent.get("agg"), intent.get("series"), intent.get("limit")
    err = _validate_columns(df, x, y, series)
    if err:
        return None, err
    df = _apply_agg(df, x, y, agg, series)
    df = _maybe_top_n(df, y, limit)
    if series:
        pivoted = df.pivot(index=x, columns=series, values=y).fillna(0)
        x_vals = pivoted.index.astype(str).tolist()
        ser_list = []
        for col in pivoted.columns:
            s = {"name": str(col), "type": "line", "data": _to_jsonable_list(pivoted[col].tolist())}
            if area:
                s["areaStyle"] = {}
            ser_list.append(s)
    else:
        x_vals = df[x].astype(str).tolist()
        s = {"type": "line", "data": _to_jsonable_list(df[y].tolist())}
        if area:
            s["areaStyle"] = {}
        ser_list = [s]
    return _wrap_axis_chart(intent, x_vals, ser_list), None


def _build_area(intent: dict, df) -> tuple[dict | None, str | None]:
    return _build_line(intent, df, area=True)


def _build_scatter(intent: dict, df) -> tuple[dict | None, str | None]:
    x, y, series, label = intent.get("x"), intent.get("y"), intent.get("series"), intent.get("label")
    err = _validate_columns(df, x, y, series)
    if err:
        return None, err
    # Resolve label column: explicit intent.label > inline `name`/`label` keys > none.
    label_col = label
    if not label_col:
        for candidate in ("label", "name"):
            if candidate in df.columns:
                label_col = candidate
                break
    if label_col and label_col not in df.columns:
        return None, f"label column not in dataset: {label_col!r}; available: {list(df.columns)}"
    show_labels = bool(label_col)
    df, sampled = _maybe_sample(df)

    if len(df) > 0:
        if not any(_is_finite(v) for v in df[x].head(5)):
            sx = df[x].iloc[0]
            return None, (
                f"scatter requires numeric x; column {x!r} has non-numeric values "
                f"(e.g. {sx!r}). Use chart_type 'bar' instead for categorical x with numeric y."
            )
        if not any(_is_finite(v) for v in df[y].head(5)):
            sy = df[y].iloc[0]
            return None, (
                f"scatter requires numeric y; column {y!r} has non-numeric values (e.g. {sy!r})."
            )

    def _label_style():
        # Per-point label config for ECharts: small text above each marker.
        # `formatter: "{b}"` pulls from the data point's `name` field.
        return {
            "show": True,
            "formatter": "{b}",
            "position": "top",
            "fontSize": 11,
        }

    def _make_pt(a, b, lbl=None):
        if show_labels and lbl is not None:
            return {"name": str(lbl), "value": [float(a), float(b)]}
        return [float(a), float(b)]

    if series:
        ser_list = []
        for grp_val, grp in df.groupby(series, sort=False):
            if show_labels:
                pts = [_make_pt(a, b, c) for a, b, c in zip(grp[x], grp[y], grp[label_col]) if _is_finite(a) and _is_finite(b)]
            else:
                pts = [_make_pt(a, b) for a, b in zip(grp[x], grp[y]) if _is_finite(a) and _is_finite(b)]
            ser = {"name": str(grp_val), "type": "scatter", "data": pts}
            if show_labels:
                ser["label"] = _label_style()
            ser_list.append(ser)
    else:
        if show_labels:
            pts = [_make_pt(a, b, c) for a, b, c in zip(df[x], df[y], df[label_col]) if _is_finite(a) and _is_finite(b)]
        else:
            pts = [_make_pt(a, b) for a, b in zip(df[x], df[y]) if _is_finite(a) and _is_finite(b)]
        ser = {"type": "scatter", "data": pts}
        if show_labels:
            ser["label"] = _label_style()
        ser_list = [ser]
    option = _wrap_value_axis_chart(intent, ser_list)
    if sampled:
        option["title"] = {**option.get("title", {}), "subtext": f"Down-sampled to {_SAMPLE_THRESHOLD} points"}
    return option, None


def _build_pie(intent: dict, df) -> tuple[dict | None, str | None]:
    cat, val, limit = intent.get("category"), intent.get("value"), intent.get("limit")
    err = _validate_columns(df, cat, val)
    if err:
        return None, err
    # Pie typically wants pre-aggregated rows; if there are multiple
    # rows per category, sum them.
    df = df.groupby(cat, sort=False)[val].sum().reset_index()
    df = _maybe_top_n(df, val, limit)
    data = [{"name": str(c), "value": _to_jsonable_scalar(v)} for c, v in zip(df[cat], df[val])]
    return {
        "title": {"text": intent.get("title", ""), "left": "center"},
        "tooltip": {"trigger": "item"},
        "legend": {"orient": "vertical", "left": "left"},
        "series": [{
            "type": "pie",
            "radius": "60%",
            "data": data,
            "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowOffsetX": 0, "shadowColor": "rgba(0, 0, 0, 0.5)"}},
        }],
    }, None


def _build_histogram(intent: dict, df) -> tuple[dict | None, str | None]:
    y = intent.get("y")
    err = _validate_columns(df, y)
    if err:
        return None, err
    import numpy as np
    series_data = df[y].dropna()
    try:
        nums = series_data.astype(float).values
    except Exception:
        return None, f"column {y!r} is not numeric"
    if len(nums) == 0:
        return None, "no numeric values to bin"
    n_bins = min(50, max(10, int(math.sqrt(len(nums)))))
    counts, edges = np.histogram(nums, bins=n_bins)
    x_vals = [f"{edges[i]:.3g}–{edges[i+1]:.3g}" for i in range(len(counts))]
    ser_list = [{"type": "bar", "data": _to_jsonable_list(counts.tolist()), "barCategoryGap": "0%"}]
    return _wrap_axis_chart(intent, x_vals, ser_list), None


def _build_box(intent: dict, df) -> tuple[dict | None, str | None]:
    y, series = intent.get("y"), intent.get("series")
    err = _validate_columns(df, y, series)
    if err:
        return None, err
    if series:
        groups = list(df.groupby(series, sort=False))
        x_vals = [str(g[0]) for g in groups]
        box_data = [_box_stats(g[1][y]) for g in groups]
    else:
        x_vals = [y]
        box_data = [_box_stats(df[y])]
    if any(b is None for b in box_data):
        return None, f"column {y!r} has insufficient numeric values for a box plot"
    return {
        "title": {"text": intent.get("title", ""), "left": "center"},
        "tooltip": {"trigger": "item"},
        "xAxis": {"type": "category", "data": x_vals, "name": intent.get("x_label") or ""},
        "yAxis": {"type": "value", "name": intent.get("y_label") or y},
        "series": [{"type": "boxplot", "data": box_data}],
    }, None


def _box_stats(series):
    """ECharts boxplot data shape: [min, Q1, median, Q3, max]."""
    s = series.dropna()
    if len(s) < 1:
        return None
    try:
        s = s.astype(float)
    except Exception:
        return None
    return [
        float(s.min()),
        float(s.quantile(0.25)),
        float(s.median()),
        float(s.quantile(0.75)),
        float(s.max()),
    ]


def _build_heatmap(intent: dict, df) -> tuple[dict | None, str | None]:
    x, y, val = intent.get("x"), intent.get("y"), intent.get("value")
    err = _validate_columns(df, x, y, val)
    if err:
        return None, err
    df_agg = df.groupby([x, y], sort=False)[val].sum().reset_index()
    x_vals = sorted(df_agg[x].astype(str).unique().tolist())
    y_vals = sorted(df_agg[y].astype(str).unique().tolist())
    x_index = {v: i for i, v in enumerate(x_vals)}
    y_index = {v: i for i, v in enumerate(y_vals)}
    data = []
    vmin, vmax = float("inf"), float("-inf")
    for xv, yv, v in zip(df_agg[x].astype(str), df_agg[y].astype(str), df_agg[val]):
        try:
            vf = float(v)
        except Exception:
            continue
        data.append([x_index[xv], y_index[yv], vf])
        vmin = min(vmin, vf)
        vmax = max(vmax, vf)
    if not data:
        return None, "no numeric values for heatmap"
    return {
        "title": {"text": intent.get("title", ""), "left": "center"},
        "tooltip": {"position": "top"},
        "xAxis": {"type": "category", "data": x_vals, "name": intent.get("x_label") or x},
        "yAxis": {"type": "category", "data": y_vals, "name": intent.get("y_label") or y},
        "visualMap": {"min": vmin, "max": vmax, "calculable": True, "orient": "horizontal", "left": "center", "bottom": 10},
        "series": [{"type": "heatmap", "data": data}],
    }, None


_BUILDERS = {
    "bar":       _build_bar,
    "line":      _build_line,
    "area":      _build_area,
    "scatter":   _build_scatter,
    "pie":       _build_pie,
    "histogram": _build_histogram,
    "box":       _build_box,
    "heatmap":   _build_heatmap,
}


# ── Helpers ──────────────────────────────────────────────────────────────


def _is_finite(v) -> bool:
    try:
        f = float(v)
        return not (math.isnan(f) or math.isinf(f))
    except Exception:
        return False


def _to_jsonable_scalar(v):
    """Convert numpy / pandas scalar to native python."""
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


def _to_jsonable_list(values: list) -> list:
    """Coerce numpy / pandas values to JSON-serialisable scalars."""
    out = []
    for v in values:
        if hasattr(v, "item"):
            try:
                v = v.item()
            except Exception:
                pass
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            v = None
        out.append(v)
    return out


def _wrap_axis_chart(intent: dict, x_vals: list, ser_list: list) -> dict:
    """Common wrapper for category-x charts (bar, line, area, histogram)."""
    return {
        "title": {"text": intent.get("title", ""), "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 30, "show": len(ser_list) > 1},
        "xAxis": {"type": "category", "data": x_vals, "name": intent.get("x_label") or ""},
        "yAxis": {"type": "value", "name": intent.get("y_label") or ""},
        "series": ser_list,
    }


def _wrap_value_axis_chart(intent: dict, ser_list: list) -> dict:
    """Common wrapper for value-x charts (scatter)."""
    return {
        "title": {"text": intent.get("title", ""), "left": "center"},
        "tooltip": {"trigger": "item"},
        "legend": {"top": 30, "show": len(ser_list) > 1},
        "xAxis": {"type": "value", "name": intent.get("x_label") or ""},
        "yAxis": {"type": "value", "name": intent.get("y_label") or ""},
        "series": ser_list,
    }


# ── Public API ───────────────────────────────────────────────────────────


def build_chart_option(intent: dict, projects_root: str) -> dict:
    """End-to-end: validate intent → resolve data → run per-type builder.

    Returns:
      {
        "ok": bool,
        "option": dict | None,        # the ECharts option, ready for setOption()
        "title": str,                  # echo of intent.title for the SSE event
        "chart_type": str,             # echo of intent.chart_type
        "error": str | None,           # human-readable error if ok is False
      }
    """
    ok, err = validate_intent(intent)
    if not ok:
        return {"ok": False, "option": None, "title": "", "chart_type": "", "error": err}

    df, err = resolve_data(intent, projects_root)
    if err or df is None:
        return {"ok": False, "option": None, "title": intent.get("title", ""), "chart_type": intent.get("chart_type", ""), "error": err}

    chart_type = intent["chart_type"]
    builder = _BUILDERS.get(chart_type)
    if builder is None:
        return {"ok": False, "option": None, "title": intent.get("title", ""), "chart_type": chart_type, "error": f"chart type {chart_type!r} not implemented"}

    try:
        option, err = builder(intent, df)
    except Exception as e:
        logger.exception("chart builder %s crashed", chart_type)
        return {"ok": False, "option": None, "title": intent.get("title", ""), "chart_type": chart_type, "error": f"builder crashed: {type(e).__name__}: {e}"}
    if err:
        return {"ok": False, "option": None, "title": intent.get("title", ""), "chart_type": chart_type, "error": err}
    return {"ok": True, "option": option, "title": intent.get("title", ""), "chart_type": chart_type, "error": None}
