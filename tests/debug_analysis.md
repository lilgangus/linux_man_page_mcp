# Debug Analysis: Binary Failure Investigation

## Overview
This document details the complete debugging process for investigating a failing binary that reports incorrect errno values.

## Initial Setup and Exploration

### Step 1: Environment Assessment
**Command:** `pwd && ls -la`
**Resource:** Shell execution
**Purpose:** Understand current directory structure and available files
**Findings:**
- Located in `/Users/charlestang/Documents/CodingProjects/linux_man_page_mcp/tests`
- Found target script `run_ab_probe.sh` and multiple related binaries
- Identified source files: `shadow_router.cpp`, `dispatch_router.cpp`, etc.

### Step 2: Script Analysis
**Command:** Read `run_ab_probe.sh`
**Resource:** File system read
**Content:**
```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${BASE_DIR}/run_shadow_probe.sh"
```
**Finding:** Script delegates to `run_shadow_probe.sh`

**Command:** Read `run_shadow_probe.sh`
**Resource:** File system read
**Content:**
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
**Finding:** Script compiles and runs `shadow_router.cpp`

## Failure Reproduction

### Step 3: Execute Failing Binary
**Command:** `./run_ab_probe.sh`
**Resource:** Shell execution with compilation and binary execution
**Output:**
```
[build] compile shadow target...
[run] launch shadow target...
boot:shadow-route
fault:Broken pipe
[done] code: 2
```
**Exit Code:** 2
**Key Observation:** Program reports "Broken pipe" error

## Source Code Analysis

### Step 4: Examine Main Source Code
**Command:** Read `shadow_router.cpp`
**Resource:** File system read (137 lines)
**Key Components Identified:**
1. Signal handling with `alarm_edge()` function
2. Hash function `mix64()` for pseudo-random number generation
3. Timer setup function `arm()` 
4. Four syscall wrapper functions: `s11()`, `s13()`, `s17()`, `s19()`
5. **Critical:** `normalize()` function that transforms errno values
6. Main execution flow in `route()` function

**Key Code Sections:**
- `s19()` calls `pause()` syscall
- `normalize()` function uses complex transformation logic
- Atlas of errno values: `{EINTR, EAGAIN, EINVAL, EBUSY, EDOM, EPERM, ENOLCK, ETIMEDOUT, EPIPE}`

## Debugging Tool Assessment

### Step 5: Check Available Debugging Tools
**Command:** `strace -e trace=poll,select,nanosleep,pause,sigaction,setitimer ./shadow_runner 2>&1`
**Resource:** Attempted system call tracing
**Result:** `strace` not available on macOS

**Command:** `which dtruss dtrace lldb gdb`
**Resource:** Tool availability check
**Findings:**
- `dtruss` available at `/usr/bin/dtruss`
- `dtrace` available at `/usr/sbin/dtrace`
- `lldb` available
- `gdb` not found

**Command:** `sudo dtruss -f -t poll,select,nanosleep,pause,sigaction,setitimer ./shadow_runner 2>&1`
**Resource:** Attempted system call tracing with dtruss
**Result:** Failed due to password requirement in non-interactive environment

## Custom Debugging Implementation

### Step 6: Create Errno Constants Reference
**Command:** Read `errno_check.cpp`
**Resource:** File system read
**Content:**
```cpp
#include <cerrno>
#include <iostream>
int main() {
    std::cout << "EINTR=" << EINTR << std::endl;
    std::cout << "EPIPE=" << EPIPE << std::endl;
    return 0;
}
```

**Command:** `./errno_check`
**Resource:** Binary execution
**Output:**
```
EINTR=4
EPIPE=32
```
**Finding:** EINTR=4, EPIPE=32 on this system

### Step 7: Create Debug Version of Source
**Command:** Write `debug_shadow.cpp`
**Resource:** File system write (modified version of original with debug output)
**Modifications:**
- Added debug output in each syscall function
- Added debug output in `normalize()` function to show transformation
- Preserved original logic while adding observability

**Command:** Compile and execute debug version
**Resource:** Compilation and execution
**Output:**
```
boot:shadow-route
DEBUG: s19 calling pause(), mark=0
DEBUG: s19 pause() returned -1, errno=4 (Interrupted system call), mark=1
DEBUG: normalize() input rc=-4, original errno=4 (Interrupted system call)
DEBUG: normalize() transformed errno=32 (Broken pipe)
fault:Broken pipe
```

**Critical Discovery:**
- `pause()` syscall correctly returns errno=4 (EINTR)
- `normalize()` function transforms errno 4 → 32 (EINTR → EPIPE)
- The alarm signal fires, setting `mark=1`

## Transformation Analysis

### Step 8: Analyze Transformation Logic
**Command:** Write `analyze_transform.cpp`
**Resource:** File system write (isolated transformation analysis)
**Purpose:** Understand the exact transformation mechanism

**Command:** Execute transformation analysis
**Resource:** Binary execution
**Output:**
```
Atlas contents:
  [0] = 4 (Interrupted system call)
  [1] = 35 (Resource temporarily unavailable)
  [2] = 22 (Invalid argument)
  [3] = 16 (Resource busy)
  [4] = 33 (Numerical argument out of domain)
  [5] = 1 (Operation not permitted)
  [6] = 77 (No locks available)
  [7] = 60 (Operation timed out)
  [8] = 32 (Broken pipe)

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

**Analysis Results:**
- Atlas contains 9 errno values
- Transformation uses hash functions with seed and mark values
- EINTR (index 0) gets transformed to EPIPE (index 8)
- Process is deterministic but complex

## Reversibility Testing

### Step 9: Test Transformation Reversibility
**Command:** Write `test_reversibility.cpp`
**Resource:** File system write (comprehensive reversibility test)
**Purpose:** Determine if transformation can be reversed

**Command:** Execute reversibility test
**Resource:** Binary execution
**Output:**
```
Testing transformation reversibility:

With mark=0:
  4 -> 33
  35 -> 60
  22 -> 35
  16 -> 1
  33 -> 33
  1 -> 22
  77 -> 60
  60 -> 33
  32 -> 16

With mark=1:
  4 -> 32
  35 -> 1
  22 -> 22
  16 -> 33
  33 -> 32
  1 -> 60
  77 -> 1
  60 -> 32
  32 -> 16

Checking for collisions:
Mark=0:
  COLLISION: 33 <- 4 33 60 
  COLLISION: 60 <- 35 77 
Mark=1:
  COLLISION: 1 <- 35 77 
  COLLISION: 32 <- 4 33 60 
```

**Critical Finding:**
- **Transformation is NOT reversible**
- Multiple original errno values map to the same transformed value
- With mark=1: EINTR(4), EDOM(33), and ETIMEDOUT(60) all transform to EPIPE(32)

## Solution Implementation

### Step 10: Create Fixed Version
**Command:** Write `fixed_shadow.cpp`
**Resource:** File system write (corrected version)
**Modification:** Replace `normalize()` function to preserve original errno:
```cpp
int normalize(int rc, std::uint64_t seed) {
    if (rc >= 0) return rc;
    return rc;  // Preserve original errno instead of transforming
}
```

**Command:** Compile and test fixed version
**Resource:** Compilation and execution
**Output:**
```
boot:shadow-route
fault:Interrupted system call
```
**Result:** Now correctly reports EINTR instead of EPIPE

## Execution Flow Analysis

### Detailed Syscall Sequence:
1. `arm(20000U)` - Sets up SIGALRM signal handler and 20ms timer
2. `s11()` - Calls `poll()` with invalid fd, times out normally
3. `s13()` - Calls `select()` with empty fd_set, times out normally  
4. `s17()` - Calls `nanosleep()` for 900μs, completes normally
5. `s19()` - Calls `pause()`, gets interrupted by SIGALRM after 20ms
   - `pause()` returns -1, sets errno=4 (EINTR)
   - Signal handler increments `mark` from 0 to 1
   - `normalize()` transforms errno 4→32 using mark=1

### Root Cause:
The `normalize()` function intentionally obfuscates errno values through a deterministic but irreversible transformation, making it impossible to determine the actual syscall failure reason.

## Summary

**Total Steps:** 10 major investigation steps
**Files Created:** 5 debug/analysis files
**Key Resources Used:**
- File system reads: 4 files
- Shell executions: 8 commands
- Binary compilations: 5 programs
- Custom code analysis: 3 specialized test programs

**Final Diagnosis:**
- Original syscall: `pause()` correctly fails with EINTR
- Bug: `normalize()` function transforms EINTR→EPIPE  
- Impact: Debugging impossible due to errno obfuscation
- Solution: Remove transformation to preserve original errno values