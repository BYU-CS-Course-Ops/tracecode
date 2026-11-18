import json
import re
from pathlib import Path

from tracecode import write_html_view


def test_console_is_hidden_without_recorded_io_and_shown_with_stdout(tmp_path):
    source = {"event": "source", "filename": "student.py", "source": ""}
    no_output = write_html_view([source], tmp_path / "silent.html").read_text()
    with_output = write_html_view(
        [source, {"event": "line", "console": [{"stream": "stdout", "text": "hi\\n"}]}],
        tmp_path / "output.html",
    ).read_text()

    assert 'id="console-heading" hidden' in no_output
    assert 'id="console-output" role="log" aria-label="Console transcript" hidden' in no_output
    assert 'id="console-heading" hidden' not in with_output
    assert 'id="console-output" role="log" aria-label="Console transcript" hidden' not in with_output


def test_console_is_visible_for_stdin_and_stays_visible_across_all_runs(tmp_path):
    source = {"event": "source", "filename": "student.py", "source": ""}
    runs = {
        "Quiet": [source, {"event": "line", "locals": {}}],
        "Input": [
            source,
            {"event": "line", "console": [{"stream": "stdin", "text": "answer\\n"}]},
        ],
    }
    html = write_html_view(
        runs["Quiet"], tmp_path / "stdin.html", runs=runs
    ).read_text()

    assert 'id="console-heading" hidden' not in html
    assert 'id="console-output" role="log" aria-label="Console transcript" hidden' not in html
    assert "consoleOutput.hidden" not in html


def test_viewer_renders_custom_module_call_frame_without_locals():
    template = Path(__file__).parents[1] / "tracecode" / "trace_viewer.html"
    html = template.read_text(encoding="utf-8")

    assert "if (frame.module_call || frame.module_return)" in html
    assert "functionName.textContent = 'Module'" in html
    assert "notice.append(calledFunction, '()')" in html
    assert "if (frame.module_complete)" in html
    assert "notice.textContent = frame.completion" in html
    assert "`${returned.qualified_function}()`" in html
    assert "const isNoneReturn = returned.value.type === 'NoneType'" in html
    assert "isNoneReturn ? ' returning'" in html
    assert "if (!isNoneReturn)" in html


def test_writes_multi_run_viewer_with_run_switcher(tmp_path):
    source = {"event": "source", "filename": "student.py", "source": "pass\\n"}
    runs = {
        "World A": [source, {"event": "line", "lineno": 1, "locals": {}, "run_status": "correct"}],
        "World B": [source, {"event": "return", "lineno": 1, "locals": {}, "run_status": "incorrect"}],
        "Empty": [source, {"event": "line", "lineno": 1, "locals": {}, "run_status": None}],
    }
    output = write_html_view(
        runs["World A"], tmp_path / "runs.html", runs=runs, start_at_end=True
    )
    html = output.read_text(encoding="utf-8")
    payload = json.loads(re.search(
        r'<script id="trace-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    ).group(1))

    assert [run["name"] for run in payload["runs"]] == ["World A", "World B", "Empty"]
    assert [run["status"] for run in payload["runs"]] == ["correct", "incorrect", None]
    assert payload["start_at_end"] is True
    assert "run.recording.length - 1" in html
    assert 'id="run-tabs"' in html
    assert "function selectRun(runIndex)" in html
    assert "currentRun.recording" in html
    assert "world-correct" in html and "world-incorrect" in html
    assert "#run-tabs button.world-correct::after" in html
    assert "#run-tabs button.world-incorrect::after" in html
    assert "border-radius: inherit" in html
    assert "border-color: #28a745" in html
    assert "border-color: #dc3545" in html
    assert "box-shadow" not in html
    assert "button.classList.toggle('world-correct', run.status === 'correct')" in html


def test_writes_standalone_viewer_with_optional_custom_panel(tmp_path):
    recording = [
        {"event": "source", "filename": "student.py", "source": "pass\\n"},
        {"event": "line", "lineno": 1, "locals": {}},
    ]
    output = write_html_view(
        recording,
        tmp_path / "panel.html",
        panel_title="Bit world <state>",
        panel_script="window.renderTracecodePanel = function () {};",
    )
    html = output.read_text(encoding="utf-8")

    assert "Bit world &lt;state&gt;" in html
    assert 'id="custom-panel"' in html
    assert "window.renderTracecodePanel = function () {};" in html
    assert "renderTracecodePanel(customPanel, snapshot, index, snapshots)" in html
    assert "if (value.display === true) return value.data;" in html
    assert html.index('id="custom-panel"') < html.index('id="frames"')


def test_custom_panel_arguments_must_be_paired(tmp_path):
    recording = [{"event": "source", "filename": "student.py", "source": ""}]

    try:
        write_html_view(recording, tmp_path / "invalid.html", panel_title="Panel")
    except ValueError as error:
        assert "provided together" in str(error)
    else:
        raise AssertionError("Expected ValueError for incomplete custom panel options")


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
    assert "Beginning" in html and "Previous" in html
    assert "Next" in html and "End" in html
    assert html.index('id="beginning"') < html.index('id="previous"')
    assert html.index('id="previous"') < html.index('id="next"') < html.index('id="end"')
    assert "textContent = line" in html
    assert 'id="source-fallback"' in html
    assert "#line-jump-controls" in html and "padding-right: 1rem" in html
    assert "async function enableCodeMirror()" in html
    assert "codemirror/5.65.5" in html
    assert "addon/runmode/runmode.min.js" in html
    assert "CodeMirror.runMode(text, 'python', element)" in html
    assert "querySelectorAll('.return-notice code')" in html
    assert "CodeMirror.runMode(valueText, 'python', renderedValue)" not in html
    assert "renderCallStack(snapshots[index])" in html
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
    assert "if (event.key === 'ArrowUp')" in html
    assert "if (event.key === 'ArrowDown')" in html
    assert "if (event.key === 'ArrowLeft')" in html
    assert "if (event.key === 'ArrowRight')" in html
    assert "beginningButton.addEventListener('click'" in html
    assert "endButton.addEventListener('click'" in html
    assert "function positionLineJumpControls()" in html
    assert "requestAnimationFrame(positionLineJumpControls)" in html
    assert "codeEditor.on('scroll', positionLineJumpControls)" in html
    assert "event.target.closest?.('.CodeMirror')" not in html
    assert "frame.call_return" in html and "return-notice" in html
    assert "frame.function_call" in html and "Calling function " in html
    assert "frame.function_call.arguments" in html and "name}=${formatValue(value)}" in html
    assert "frame.function_call.positional_arguments" in html
    assert "for (const value of frame.function_call.positional_arguments || [])" in html
    assert "notice.append('Function ')" in html
    assert "frame.input_return.typed_text" in html
    assert "The user typed " in html
    assert "inputReturnNotice" not in html
    assert "frame.call_return ? ' returned ' : ' returning '" in html
    assert "frame.exit.script} exited with exit code ${frame.exit.code}" in html
    assert html.index("card.appendChild(variable)") < html.rindex("card.appendChild(notice)")
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
