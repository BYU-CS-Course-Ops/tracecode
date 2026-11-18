from __future__ import annotations

import html
import json
import webbrowser
from pathlib import Path
from typing import Any


_TEMPLATE = Path(__file__).with_name("trace_viewer.html")
_DATA_MARKER = "__TRACE_RECORDING_JSON__"


def write_html_view(
    recording: list[dict[str, Any]],
    output_path: str | Path,
    auto_open: bool = False,
    *,
    panel_title: str | None = None,
    panel_script: str | None = None,
    runs: dict[str, list[dict[str, Any]]] | None = None,
) -> Path:
    """Write a standalone HTML viewer, optionally with an embedded custom panel."""
    if (panel_title is None) != (panel_script is None):
        raise ValueError("panel_title and panel_script must be provided together")
    source_records = [record for record in recording if record.get("event") == "source"]
    if len(source_records) != 1:
        raise ValueError("Recording must contain exactly one source record")

    source_record = source_records[0]
    snapshots = [record for record in recording if record.get("event") != "source"]

    def run_data(name, run_recording):
        source = next((item for item in run_recording if item.get("event") == "source"), None)
        if source is None:
            raise ValueError(f"Run {name!r} has no source record")
        return {
            "name": name,
            "filename": Path(source["filename"]).name,
            "source": source["source"],
            "recording": [item for item in run_recording if item.get("event") != "source"],
        }

    run_payloads = [run_data(name, run) for name, run in (runs or {}).items()]
    has_console = any(
        snapshot.get("console")
        for run in (run_payloads or [{"recording": snapshots}])
        for snapshot in run["recording"]
    )
    output_path = Path(output_path)
    view_data = {
        "filename": Path(source_record["filename"]).name,
        "source": source_record["source"],
        "recording": snapshots,
    }
    if run_payloads:
        view_data["runs"] = run_payloads
    payload = json.dumps(
        view_data,
        ensure_ascii=False,
        allow_nan=False,
    )
    safe_payload = (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    template = _TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        _DATA_MARKER: safe_payload,
        "__TRACE_PANEL_TITLE__": "" if panel_title is None else html.escape(panel_title),
        "__TRACE_PANEL_SCRIPT__": "" if panel_script is None else panel_script,
        "__TRACE_PANEL_HIDDEN__": "hidden" if panel_title is None else "",
        "__TRACE_CONSOLE_HIDDEN__": "" if has_console else "hidden",
    }
    for marker, replacement in replacements.items():
        if marker not in template:
            raise RuntimeError(f"Expected {marker} marker in {_TEMPLATE}")
        template = template.replace(marker, replacement)

    output_path.write_text(template, encoding="utf-8")
    if auto_open:
        webbrowser.open(output_path.resolve().as_uri())
    return output_path
