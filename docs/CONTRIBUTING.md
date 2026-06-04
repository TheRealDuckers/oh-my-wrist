# Contributing

Contributions are more than welcome. Please contribute!

`oh-my-wrist` currently supports Claude Code and OpenCode, but the project is designed to accept integrations with other AI coding tools. New provider integrations, Garmin/watch improvements, platform fixes, tests, and documentation updates are all welcome.

## Before you start

- For large changes or new provider integrations, open an issue first so we can agree on scope and avoid duplicate work.
- Keep changes small and focused. Separate documentation, cleanup, and behavior changes where possible.
- Prefer extending existing abstractions over adding provider-specific branches in shared code.

## Adding another tool integration

The core daemon is provider-agnostic. A new tool should be adapted into the existing `CanonicalEvent` / `CanonicalIpcMessage` pipeline instead of inventing a separate wire format.

Typical steps:

1. Add the provider name to the `Provider` literal in `src/ohm/provider_types.py`.
2. Add or extend tool intent mappings in `TOOL_INTENT` if the new tool uses different names for shell, edit, read, web, todo, permission, or agent actions.
3. Create `src/ohm/adapters/<provider>_adapter.py` that converts the tool-specific payload into `CanonicalEvent`.
4. Add a hook, plugin, or relay entry point that sends newline-delimited `CanonicalIpcMessage` JSON to the existing IPC socket / named pipe.
5. Update CLI/install support in `src/ohm/main.py` and `src/ohm/install.py` only if the integration needs automatic setup, status checks, or uninstall support.
6. If the provider needs a dedicated stats screen on the watch, add a stats characteristic in `src/ohm/protocol.py`, register it in `src/ohm/ble_daemon.py`, and mirror it in `garmin/source/BleManager.mc` and the Garmin stats/delegate code.

For many integrations, most work should be isolated to the adapter, relay/plugin, installer, and tests. The history encoder, session engine, alert routing, and watch rendering should continue to operate on canonical events.

## Good practices

- Keep hook/relay paths fast and quiet. Claude hooks must not block the tool for long, and provider hooks should not print noisy errors to the user's terminal.
- Preserve the canonical contract: shared code should usually branch on `CanonicalEvent.tool_intent`, not raw provider-specific tool names.
- Sanitize provider output before display. Strip ANSI/control sequences, avoid leaking secrets, and keep labels concise.
- Respect the BLE wire limits. HISTORY frames are byte-limited, and UTF-8 must remain valid; use the existing encoder/truncation helpers.
- Keep icon IDs append-only in `src/ohm/icons.py` and mirror any new IDs in `garmin/source/IconCatalog.mc`. Never renumber existing icons.
- Preserve provider isolation in `MultiProviderSessionState`; events from one provider must not reset or mutate another provider's stats.
- Avoid changing BLE UUIDs, frame layout, or alert constants unless the change is necessary and documented.
- Add clear documentation for new setup steps, permissions, or platform-specific limitations.

## Testing

Run the Python checks before opening a pull request:

```bash
uv venv
uv pip install -e ".[dev]"
uv run ruff check .
uv run pytest
```

Or with pip:

```bash
pip install -e ".[dev]"
ruff check .
pytest tests/
```

For a new provider integration, add targeted tests for:

- The adapter: representative raw provider payloads become the expected `CanonicalEvent` values.
- Tool intent mapping: provider tool names classify correctly through `CanonicalEvent.tool_intent`.
- IPC/schema behavior: emitted messages are valid `CanonicalIpcMessage` payloads.
- Session state: provider stats are isolated from Claude/OpenCode and any other providers.
- History encoding: labels/icons/flags render correctly and stay within frame limits.
- Installer/CLI behavior, if the integration adds install, uninstall, or status commands.

Useful focused commands:

```bash
pytest tests/test_provider_types.py
pytest tests/test_history_encoder.py
pytest tests/test_session_state.py
pytest tests/test_end_to_end_normalization.py
pytest -k "adapter or provider"
```

The test suite mocks BLE, so most changes do not require a Bluetooth adapter or Garmin watch. For watch-side behavior, use the Connect IQ simulator and the scripts under `garmin/` or `tools/simulate_ui.py` with a running daemon.

## Pull request checklist

- [ ] The change is focused and documented.
- [ ] New provider payloads are normalized to `CanonicalEvent`.
- [ ] Provider-specific behavior is contained in adapters, relays/plugins, installer code, or display-only labels.
- [ ] Existing Claude Code and OpenCode behavior remains unchanged.
- [ ] `ruff check .` passes.
- [ ] `pytest` passes, or any skipped checks are explained.
