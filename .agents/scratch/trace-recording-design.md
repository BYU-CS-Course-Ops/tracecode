# Trace recording design

## Goal

Record a run of a small, single-module student program so the UI can step forward and backward through saved execution snapshots. The recorder owns execution history; Bit supplies its state; the UI decides how snapshots are rendered.

## Recording

- Use Python tracing to record events from code in the target file only; ignore frames from other files.
- Record executed lines and function return and exception events. A line snapshot represents state before that line executes. A normal return event includes the returned value and its type; an exception event records the exception, not necessarily termination of the program.
- At each event, snapshot the current target-frame locals and target-module globals (module scope appears only once), excluding interpreter metadata. Include Bit world, position, and orientation through Bit's serializer. Snapshots are independent of later mutations.
- Treat the ledger as playback data: navigation selects an existing snapshot; it does not reverse or rerun execution.

## Value serialization

- Encode JSON primitives, lists, dictionaries, and tuples. Use tagged tuple values so tuples remain distinct from lists.
- Encode dictionaries as ordered key/value entry pairs, allowing non-string keys; encode keys and values using the same value format.
- `TraceRecorder` accepts per-run `(type, serializer)` pairs. Check them in supplied order and use the first `isinstance` match. Serializers return structured JSON-compatible values; register Bit's serializer here.
- Represent unsupported values as explicitly opaque, retaining the type name but not calling `str(value)`. The UI may hide opaque values. Opaque values indicate unsupported types, not serialization failures.
- Apply a maximum recursion depth and per-snapshot item limit as failsafes. Encode values that exceed either limit as opaque and continue recording.
- If a serializer or any other framework component fails, propagate the error and end the recording session; do not return a misleading or incomplete trace. Serialization details can be decided during implementation.

## Bounds

Keep the first N snapshots. At the limit, stop recording and mark the ledger truncated, but let the program continue and show its result if it terminates. Execution timeout/cancellation is a separate runner responsibility.
