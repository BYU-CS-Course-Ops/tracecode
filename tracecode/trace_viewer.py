from __future__ import annotations

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
) -> Path:
    """Write a standalone HTML viewer for a source record and its trace snapshots."""
    source_records = [record for record in recording if record.get("event") == "source"]
    if len(source_records) != 1:
        raise ValueError("Recording must contain exactly one source record")

    source_record = source_records[0]
    snapshots = [record for record in recording if record.get("event") != "source"]
    output_path = Path(output_path)
    payload = json.dumps(
        {
            "filename": Path(source_record["filename"]).name,
            "source": source_record["source"],
            "recording": snapshots,
        },
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
    if template.count(_DATA_MARKER) != 1:
        raise RuntimeError(f"Expected one recording-data marker in {_TEMPLATE}")

    output_path.write_text(template.replace(_DATA_MARKER, safe_payload), encoding="utf-8")
    if auto_open:
        webbrowser.open(output_path.resolve().as_uri())
    return output_path
