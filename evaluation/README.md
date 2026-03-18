# Evaluation: MCP-Aided Debugging A/B Test

Does giving an LLM access to structured man-page lookups improve its ability to diagnose a tricky systems bug? This directory contains the protocol, test case, and results of a controlled A/B experiment to find out.

## The Test Case

[`shadow_router.cpp`](shadow_router.cpp) is a C++ program that sets up a SIGALRM timer, runs a sequence of syscalls (`poll`, `select`, `nanosleep`, `pause`), and deliberately **transforms the errno** returned by the failing syscall through a hash-based `normalize()` function.

The program reports `fault:Broken pipe` (EPIPE), but the actual failure is `pause()` being interrupted by the alarm — which produces EINTR, not EPIPE. The transformation is **lossy** (multiple errnos map to the same output), so it cannot be reversed.

This is designed to test whether an LLM can:
1. Recognize that the reported errno is impossible for the syscalls in the code path
2. Identify the `normalize()` function as the source of obfuscation
3. Prove the mismatch using authoritative errno-to-syscall documentation
4. Determine that the transformation is irreversible

## A/B Protocol

| | Arm A (No MCP) | Arm B (MCP Enabled) |
|---|---|---|
| **Tools** | Code reading + shell only | Code reading + shell + `lookup_error_code` |
| **Prompt** | [Shared prompt](ab_shared_prompt.md) | Same shared prompt |
| **Model** | Same model/settings | Same model/settings |

Both arms receive the same prompt asking them to debug the binary and produce a 5-bullet diagnosis. The key difference: Arm B can call `lookup_error_code("EPIPE")` and `lookup_error_code("EINTR")` to get authoritative lists of which syscalls can return each errno.

Full protocol: [`ab_protocol.md`](ab_protocol.md) | Scoring rubric: [`ab_scoring.md`](ab_scoring.md)

## How to Reproduce

```bash
# Compile and run the test binary
./run_shadow_probe.sh

# Expected output:
# [build] compile shadow target...
# [run] launch shadow target...
# boot:shadow-route
# fault:Broken pipe
# [done] code: 2
```

## Results

The Arm B (MCP-enabled) analysis identified the errno mismatch faster and with authoritative evidence — `lookup_error_code("EPIPE")` returned only `write`/`send`/`sendmsg`/`sendto`, none of which appear in the code, immediately proving the reported errno is fabricated.

Without MCP tools, the model had to build instrumented debug binaries and run multiple manual experiments to reach the same conclusion.

| Criterion | Arm A (No MCP) | Arm B (MCP) |
|---|---|---|
| Identified errno as transformed | Yes | Yes |
| Proved errno impossible for code path | Via manual instrumentation | Via `lookup_error_code` |
| Authoritative evidence | No (used custom test programs) | Yes (man-page index lookup) |
| Steps to root cause | ~10 | ~7 |

Full analysis: [with MCP](debug_analysis_mcp.md) | [without MCP](debug_analysis_no_mcp.md) | [comparison report (PDF)](debugging_comparison_report.pdf)

## File Index

| File | Description |
|------|-------------|
| `shadow_router.cpp` | Test program with deliberate errno obfuscation |
| `run_shadow_probe.sh` | Build and run the test binary |
| `run_ab_probe.sh` | Wrapper script (calls `run_shadow_probe.sh`) |
| `ab_protocol.md` | Experiment protocol (arms, controls, success criteria) |
| `ab_shared_prompt.md` | Exact prompt used in both arms |
| `ab_scoring.md` | Scoring rubric (0-10 scale, mandatory gates) |
| `debug_analysis_mcp.md` | Full Arm B analysis (with MCP tools) |
| `debug_analysis_no_mcp.md` | Full Arm A analysis (without MCP tools) |
| `debug_analysis.md` | Additional analysis notes |
| `notes.md` | Prompt development notes |
| `debugging_comparison_report.pdf` | Side-by-side comparison report |
| `MCPDebug*.png` | Screenshots from MCP-enabled run |
| `noMCPdebug*.png` | Screenshots from no-MCP run |
