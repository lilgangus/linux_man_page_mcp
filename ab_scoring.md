# A/B Scoring (Root-Cause Difficulty)

Score each answer 0-10. Mark as fail if any mandatory gate is missing.

## Mandatory Gates (all required to pass)

- Mentions observed runtime failure (`fault:Broken pipe` and non-zero exit).
- Identifies surfaced errno as transformed/misleading, not trusted as original.
- Explains transform non-reversibility (lossy bucket/hash style mapping).
- Provides minimal correct fix for truth-preserving behavior (`return rc` directly on error).
- Includes authoritative function-to-errno evidence from reference tooling.

If the last gate is missing, classify as:

- Technical diagnosis: possibly correct
- Benchmark result: fail/incomplete

## Suggested Score Bands

- 0-2: Wrong or shallow diagnosis.
- 3-5: Partially correct but misses transform or reversibility.
- 6-8: Correct diagnosis and fix, weak/no authoritative evidence.
- 9-10: Correct diagnosis, reversibility argument, and authoritative errno evidence.

## Why This Distinguishes A/B

- The case surfaces a believable but transformed errno.
- Smaller/no-reference runs often stop at surface symptoms.
- Reference-enabled runs can prove mismatch between surfaced errno and syscall path.
