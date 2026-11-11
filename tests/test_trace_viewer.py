import json
import re

from tracecode import write_html_view


def test_writes_standalone_viewer_with_safely_embedded_recording(tmp_path):
    source = 'print("</script>")\n# </textarea>\n# café\u2028'
    snapshot = {
        "event": "line",
        "filename": "student.py",
        "lineno": 1,
        "function": "run",
        "qualified_function": "run",
        "locals": {"value": {"type": "str", "data": "</script>"}},
    }
    recording = [
        {"event": "source", "filename": "/tmp/student.py", "source": source},
        snapshot,
    ]
    output_path = tmp_path / "trace.html"

    result = write_html_view(recording, output_path)

    html = result.read_text(encoding="utf-8")
    embedded_json = re.search(
        r'<script id="trace-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    ).group(1)
    payload = json.loads(embedded_json)

    assert result == output_path
    assert payload == {"filename": "student.py", "source": source, "recording": [snapshot]}
    assert "</script>" not in embedded_json
    assert "</textarea>" not in html
    assert "Previous" in html and "Next" in html
    assert "textContent = line" in html
    assert 'id="frames"' in html and "className = 'frame-card'" in html
    assert "snapshot.callers" in html and "variable-card" in html
    assert "frame.call_return" in html and "return-notice" in html
    assert html.index("card.appendChild(variable)") < html.index("card.appendChild(notice)")
    assert "displayType(value)" in html and "variable.append(label, type, renderedValue)" in html
    assert "inline.length <= 20" in html
    assert ".source-line.call-site" in html and "caller.lineno" in html
    assert "frame.locals" in html and "frame.globals" not in html
    assert "overflow: auto" in html
    assert "<script src=" not in html
