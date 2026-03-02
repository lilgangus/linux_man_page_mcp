# A/B Protocol

Use the exact same prompt text from `ab_shared_prompt.md` in both arms.

## Arm A (No Reference MCP)

- Disable Linux reference MCP tools.
- Run the model with only local code/runtime access.
- Capture final answer text only.

## Arm B (Reference MCP Enabled)

- Enable Linux reference MCP tools.
- Use the same model family/size and same temperature/settings as Arm A.
- Capture final answer text only.

## Hold Constant

- Same prompt text
- Same repository state
- Same runtime command (`./tests/run_ab_probe.sh`)
- Same model parameters
- Same answer length cap

## Success Criterion

Arm B should outperform Arm A specifically on evidence-backed root-cause diagnosis.
