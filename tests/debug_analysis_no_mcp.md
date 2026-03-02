# Debug Analysis: Binary Failure Investigation

## Overview
This document details the complete debugging process for analyzing a failing binary that reports incorrect errno values. The investigation focused on identifying errno transformation and determining reversibility.

## Step 1: Initial Environment Assessment

### Command: `pwd && ls -la`
**Purpose**: Understand the working directory and available files
**Resource Used**: Shell command execution
**Output**: Located in `/Users/charlestang/Documents/CodingProjects/linux_man_page_mcp/tests` with multiple test binaries and scripts

**Key Findings**:
- Found `run_ab_probe.sh` (target script)
- Multiple compiled binaries present: `dispatch_runner`, `errno_check`, `probe_runner`, etc.
- Source files available: `shadow_router.cpp`, `dispatch_router.cpp`, etc.

## Step 2: Script Chain Analysis

### Command: Read `run_ab_probe.sh`
**Purpose**: Understand the execution chain
**Resource Used**: File system read
**Content Analysis**:
```bash
#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${BASE_DIR}/run_shadow_probe.sh"
```

**Logic**: The script delegates to `run_shadow_probe.sh`

### Command: Read `run_shadow_probe.sh`
**Purpose**: Understand the actual test execution
**Resource Used**: File system read
**Content Analysis**:
```bash
#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_MAIN="${BASE_DIR}/shadow_router.cpp"
BIN="${BASE_DIR}/shadow_runner"

echo "[build] compile shadow target..."
g++ -std=c++17 -O2 -Wall -Wextra -pedantic "${SRC_MAIN}" -o "${BIN}"

echo "[run] launch shadow target..."
set +e
"${BIN}"
CODE=$?
set -e

echo "[done] code: ${CODE}"
exit "${CODE}"
```

**Logic**: Compiles `shadow_router.cpp` and executes the resulting binary

## Step 3: Failure Reproduction

### Command: `./run_ab_probe.sh`
**Purpose**: Reproduce the reported failure
**Resource Used**: Shell command execution, binary execution
**Output**:
```
[build] compile shadow target...
[run] launch shadow target...
boot:shadow-route
fault:Broken pipe
[done] code: 2
```

**Key Findings**:
- Exit code: 2 (failure)
- Error message: "fault:Broken pipe"
- This suggests an EPIPE errno (32)

## Step 4: Source Code Analysis

### Command: Read `shadow_router.cpp`
**Purpose**: Understand the program logic and potential errno transformation
**Resource Used**: File system read (137 lines)
**Content Analysis**:

#### Key Components Identified:
1. **Signal handling**: `alarm_edge()` function, `SIGALRM` setup
2. **Syscall functions**: `s11()` (poll), `s13()` (select), `s17()` (nanosleep), `s19()` (pause)
3. **Transformation function**: `normalize()` - suspicious errno manipulation
4. **Error atlas**: Array of 9 errno values: `EINTR, EAGAIN, EINVAL, EBUSY, EDOM, EPERM, ENOLCK, ETIMEDOUT, EPIPE`

#### Critical Logic in `normalize()`:
```cpp
int normalize(int rc, std::uint64_t seed) {
    if (rc >= 0) return rc;
    auto e = atlas();
    int x = -rc;
    std::size_t i = mix64(seed ^ static_cast<std::uint64_t>(x * 257U), e.size());
    std::size_t j = mix64((seed << 1U) ^ 0x9e3779b97f4a7c15ULL, e.size());
    // ... complex transformation logic
    return -e[q];  // Returns transformed errno
}
```

**Logic**: The function transforms original errno values using hash-based mapping

## Step 5: Debugging Tool Availability Assessment

### Command: `which strace dtrace lldb gdb`
**Purpose**: Identify available system call tracing tools
**Resource Used**: Shell command execution
**Output**: 
- `strace`: Not available (Linux tool)
- `dtruss`: Available at `/usr/bin/dtruss`
- `dtrace`: Available at `/usr/sbin/dtrace`
- `lldb`: Available
- `gdb`: Not found

### Command: `sudo dtruss -f -t poll,select,nanosleep,pause,sigaction,setitimer ./shadow_runner`
**Purpose**: Trace syscalls to see actual errno values
**Resource Used**: System call tracing (attempted)
**Result**: Failed - requires password for sudo

**Logic**: Need alternative approach since system tracing requires elevated privileges

## Step 6: Errno Constants Investigation

### Command: Read `errno_check.cpp`
**Purpose**: Understand errno constant values on this system
**Resource Used**: File system read
**Content**: Simple program printing EINTR and EPIPE values

### Command: `./errno_check`
**Purpose**: Get actual errno constant values
**Resource Used**: Binary execution
**Output**:
```
EINTR=4
EPIPE=32
```

**Key Findings**: Confirmed EINTR=4, EPIPE=32 on this system

## Step 7: Custom Debug Instrumentation

### Command: Create `debug_shadow.cpp`
**Purpose**: Add debug output to capture actual errno values before transformation
**Resource Used**: File system write (140 lines)
**Modifications Made**:
- Added debug prints in each syscall function (`s11`, `s13`, `s17`, `s19`)
- Added debug prints in `normalize()` to show input and output errno values
- Preserved original program logic

### Command: Compile and execute debug version
**Purpose**: Capture the actual errno transformation in action
**Resource Used**: Compilation + binary execution
**Output**:
```
boot:shadow-route
DEBUG: s19 calling pause(), mark=0
DEBUG: s19 pause() returned -1, errno=4 (Interrupted system call), mark=1
DEBUG: normalize() input rc=-4, original errno=4 (Interrupted system call)
DEBUG: normalize() transformed errno=32 (Broken pipe)
fault:Broken pipe
```

**Critical Findings**:
- Original syscall: `pause()` failed with `errno=4` (EINTR)
- Alarm fired, changing `mark` from 0 to 1
- `normalize()` transformed EINTR(4) → EPIPE(32)
- Program reports "Broken pipe" instead of "Interrupted system call"

## Step 8: Transformation Mechanism Analysis

### Command: Create `analyze_transform.cpp`
**Purpose**: Understand the exact transformation algorithm
**Resource Used**: File system write, isolated algorithm analysis
**Test Parameters**:
- `seed = 0x736861646f772d72ULL ^ 0x19ULL` (from s19 call)
- `x = 4` (EINTR)
- `mark = 1` (after alarm fired)

### Command: Execute transformation analysis
**Purpose**: Trace the hash-based transformation step by step
**Resource Used**: Binary execution
**Output**:
```
Atlas contents:
  [0] = 4 (Interrupted system call)    # EINTR
  [1] = 35 (Resource temporarily unavailable)  # EAGAIN
  [2] = 22 (Invalid argument)          # EINVAL
  [3] = 16 (Resource busy)             # EBUSY
  [4] = 33 (Numerical argument out of domain)  # EDOM
  [5] = 1 (Operation not permitted)    # EPERM
  [6] = 77 (No locks available)        # ENOLCK
  [7] = 60 (Operation timed out)       # ETIMEDOUT
  [8] = 32 (Broken pipe)               # EPIPE

Transformation details:
seed = 0x736861646f772d6b
x = 4 (EINTR)
mark = 1
i = 2
j = 4
op_index = 2
k = 8
q = 8
Result: 32 (Broken pipe)
```

**Key Findings**:
- Atlas index 8 contains EPIPE(32)
- Hash function maps EINTR to atlas index 8
- Transformation is deterministic but complex

## Step 9: Reversibility Testing

### Command: Create `test_reversibility.cpp`
**Purpose**: Determine if the errno transformation is reversible
**Resource Used**: File system write, comprehensive collision analysis
**Test Logic**: 
- Test all 9 atlas errno values as inputs
- Test with both mark=0 and mark=1 states
- Check for collisions (multiple inputs mapping to same output)

### Command: Execute reversibility test
**Purpose**: Analyze transformation collisions
**Resource Used**: Binary execution
**Output**:
```
Testing transformation reversibility:

With mark=0:
  4 -> 33    # EINTR -> EDOM
  35 -> 60   # EAGAIN -> ETIMEDOUT
  22 -> 35   # EINVAL -> EAGAIN
  16 -> 1    # EBUSY -> EPERM
  33 -> 33   # EDOM -> EDOM
  1 -> 22    # EPERM -> EINVAL
  77 -> 60   # ENOLCK -> ETIMEDOUT
  60 -> 33   # ETIMEDOUT -> EDOM
  32 -> 16   # EPIPE -> EBUSY

With mark=1:
  4 -> 32    # EINTR -> EPIPE
  35 -> 1    # EAGAIN -> EPERM
  22 -> 22   # EINVAL -> EINVAL
  16 -> 33   # EBUSY -> EDOM
  33 -> 32   # EDOM -> EPIPE
  1 -> 60    # EPERM -> ETIMEDOUT
  77 -> 1    # ENOLCK -> EPERM
  60 -> 32   # ETIMEDOUT -> EPIPE
  32 -> 16   # EPIPE -> EBUSY

Checking for collisions:
Mark=0:
  COLLISION: 33 <- 4 33 60    # EDOM <- EINTR, EDOM, ETIMEDOUT
  COLLISION: 60 <- 35 77      # ETIMEDOUT <- EAGAIN, ENOLCK
Mark=1:
  COLLISION: 1 <- 35 77       # EPERM <- EAGAIN, ENOLCK
  COLLISION: 32 <- 4 33 60    # EPIPE <- EINTR, EDOM, ETIMEDOUT
```

**Critical Findings**:
- **NOT REVERSIBLE**: Multiple original errno values map to the same transformed value
- With mark=1: EINTR(4), EDOM(33), and ETIMEDOUT(60) all transform to EPIPE(32)
- Information loss occurs during transformation

## Step 10: Solution Development

### Command: Create `fixed_shadow.cpp`
**Purpose**: Implement fix that preserves original errno
**Resource Used**: File system write
**Fix Applied**:
```cpp
int normalize(int rc, std::uint64_t seed) {
    if (rc >= 0) return rc;
    return rc;  // Preserve original errno instead of transforming
}
```

### Command: Test the fix
**Purpose**: Verify that original errno is preserved
**Resource Used**: Compilation + binary execution
**Output**:
```
boot:shadow-route
fault:Interrupted system call
```

**Verification**: Program now correctly reports "Interrupted system call" (EINTR) instead of "Broken pipe" (EPIPE)

## Conclusions

### Root Cause
The `normalize()` function intentionally obfuscates errno values through a deterministic but complex hash-based transformation that maps original errno values to different ones from a predefined atlas.

### Evidence Summary
1. **Syscall Analysis**: `pause()` legitimately fails with EINTR(4) when interrupted by SIGALRM
2. **Transformation Proof**: Debug output shows EINTR(4) → EPIPE(32) transformation
3. **Algorithm Analysis**: Hash function deterministically maps atlas indices
4. **Collision Detection**: Multiple original values map to same transformed value
5. **Fix Verification**: Removing transformation preserves original errno

### Reversibility Verdict
**NOT REVERSIBLE** - The transformation has collisions where multiple original errno values map to the same transformed value, causing information loss.

### Technical Details
- **Hash Function**: Uses `mix64()` with seed, original errno, and volatile mark state
- **Atlas Size**: 9 predefined errno values
- **Collision Examples**: EINTR, EDOM, ETIMEDOUT all map to EPIPE when mark=1
- **State Dependency**: Transformation result depends on timing-sensitive `mark` variable

### Minimal Correct Fix
Replace the `normalize()` function body with a simple passthrough to preserve the true original errno:

```cpp
int normalize(int rc, std::uint64_t seed) {
    if (rc >= 0) return rc;
    return rc;  // Preserve original errno
}
```

This fix ensures that debugging and error handling can rely on accurate errno values from the actual failing syscalls.