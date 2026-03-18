# Shared Prompt (Use In Both A/B Arms)

Debug this failing binary and keep the answer concise.

Run:

- `./tests/run_ab_probe.sh`

Requirements:

- Use any reference/debug tools available in your environment.
- Verify whether the reported `fault:<errno>` can actually come from the syscalls in the execution path.
- Decide whether the surfaced errno is original or transformed.
- State whether the transform is reversible for recovering original errno.
- If proposing a fix, only give the fix that preserves true original errno.

Output format (max 6 bullets total):

1. Observed failure
2. Evidence
3. Root cause
4. Reversibility verdict
5. Minimal correct fix
