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
    assert "</textarea>" not in embedded_json
    assert "Previous" in html and "Next" in html
    assert "textContent = line" in html
    assert 'id="source-fallback"' in html
    assert "#line-jump-controls" in html and "padding-right: 1rem" in html
    assert "async function enableCodeMirror()" in html
    assert "codemirror/5.65.5" in html
    assert "readOnly: true" in html and "mode: 'python'" in html
    assert "sourceFallback.hidden = true" in html
    assert 'id="frames"' in html and "className = 'frame-card'" in html
    assert 'id="event-info"' not in html and "eventInfo" not in html
    assert '.frame-heading code { font-weight: 700; }' in html
    assert '.current-frame .frame-heading { background: #fff0a6; }' in html
    assert "document.createElement('code')" in html
    assert "snapshot.callers" in html and "variable-card" in html
    assert "frames.scrollTop = frames.scrollHeight" in html
    assert 'id="console-output"' in html
    assert "snapshots[snapshotIndex].console" in html
    assert "chunk.stream === 'stdin' ? 'stdin' : 'stdout'" in html
    assert "consoleOutput.scrollTop = consoleOutput.scrollHeight" in html
    assert "background: white; color: #202124" in html
    assert "font: 1rem/1.35 ui-monospace" in html
    assert "#console-output .stdin { color: #305b91" in html
    assert "function renderException(exception)" in html
    assert "Traceback (most recent call last):" in html
    assert "exception.traceback" in html
    assert "card.appendChild(renderException(frame.exception))" in html
    assert html.index("for (const frame of exception.traceback") < html.index("notice.appendChild(summary)")
    assert "getWrapperElement().addEventListener('mousemove'" in html
    assert "codeEditor.on('mousemove'" not in html
    assert "if (event.key === 'ArrowLeft')" in html
    assert "if (event.key === 'ArrowRight')" in html
    assert "function positionLineJumpControls()" in html
    assert "requestAnimationFrame(positionLineJumpControls)" in html
    assert "codeEditor.on('scroll', positionLineJumpControls)" in html
    assert "event.target.closest?.('.CodeMirror')" not in html
    assert "frame.call_return" in html and "return-notice" in html
    assert "frame.function_call" in html and "Calling function " in html
    assert "frame.function_call.arguments" in html and "name}=${formatValue(value)}" in html
    assert "frame.input_return.typed_text" in html
    assert "The user typed " in html and "inputReturnNotice.append(inputFunction, ' returned ')" in html
    assert html.index("card.appendChild(typedNotice)") < html.index("card.appendChild(inputReturnNotice)")
    assert "frame.call_return ? ' returned ' : ' returning '" in html
    assert html.index("card.appendChild(variable)") < html.index("card.appendChild(notice)")
    assert "displayType(value)" in html and "variable.append(label, type, renderedValue)" not in html
    assert "function hasExceptionMessage(value)" in html
    assert "if (value.type !== 'opaque' || hasExceptionMessage(value))" in html
    assert "value.data.exception_message" in html
    assert "typeName.split('.')" in html
    assert "value.type === 'opaque' && !hasExceptionMessage(value) ? '' : ':'" in html
    assert "inline.length <= 30" in html
    assert "font-size: 1rem; font-weight: 700" in html
    assert "background: #f5f7fa; font-size: 1rem" in html
    assert "font: 1rem ui-monospace" in html
    assert "font: 1rem/1.35 ui-monospace" in html
    assert ".source-line.call-site" in html and "caller.lineno" in html
    assert "frame.locals" in html and "frame.globals" not in html
    assert "overflow: auto" in html
    assert "<script src=" not in html
