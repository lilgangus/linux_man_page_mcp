# Debug Analysis: AB Probe Failure - Complete Investigation

## Overview
This document details the complete debugging process for the failing `run_ab_probe.sh` binary, including every tool call, MCP server interaction, and logical step taken to identify the root cause.

## Initial Setup and Exploration

### Step 1: Directory Exploration
**Command**: `ls -la`
**Purpose**: Understand the test environment and available files
**Result**: Found multiple test runners and scripts, including the target `run_ab_probe.sh`

**Key Files Identified**:
- `run_ab_probe.sh` - Target script to debug
- `shadow_router.cpp` - Source code for the failing binary
- `shadow_runner` - Compiled binary
- Multiple other test runners and scripts

### Step 2: Script Analysis
**Tool**: Read file tool
**Target**: `/Users/charlestang/Documents/CodingProjects/linux_man_page_mcp/tests/run_ab_probe.sh`

**Findings**:
```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${BASE_DIR}/run_shadow_probe.sh"
```

**Analysis**: The AB probe script is a wrapper that calls `run_shadow_probe.sh`

## Failure Reproduction

### Step 3: Execute Failing Test
**Command**: `./run_ab_probe.sh`
**Result**: 
```
[build] compile shadow target...
[run] launch shadow target...
boot:shadow-route
fault:Broken pipe
[done] code: 2
```

**Key Observations**:
- Exit code: 2
- Error message: "fault:Broken pipe"
- EPIPE errno being reported

## Source Code Investigation

### Step 4: Shadow Probe Script Analysis
**Tool**: Read file tool
**Target**: `/Users/charlestang/Documents/CodingProjects/linux_man_page_mcp/tests/run_shadow_probe.sh`

**Findings**:
- Compiles `shadow_router.cpp` with g++
- Executes the resulting binary
- Returns the exit code

### Step 5: Shadow Router Source Code Analysis
**Tool**: Read file tool  
**Target**: `/Users/charlestang/Documents/CodingProjects/linux_man_page_mcp/tests/shadow_router.cpp`

**Critical Code Sections Identified**:

#### Signal Handler Setup
```cpp
extern "C" void alarm_edge(int) {
    ++mark;
}

int arm(unsigned usec) {
    struct sigaction sa {};
    sa.sa_handler = alarm_edge;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    if (sigaction(SIGALRM, &sa, nullptr) != 0) return -errno;

    struct itimerval tv {};
    tv.it_value.tv_sec = usec / 1000000U;
    tv.it_value.tv_usec = static_cast<suseconds_t>(usec % 1000000U);
    if (setitimer(ITIMER_REAL, &tv, nullptr) != 0) return -errno;
    return 1;
}
```

#### Syscall Functions
```cpp
int s11() {  // poll()
    struct pollfd pfd {};
    pfd.fd = -1;
    pfd.events = POLLIN;
    int rc = poll(&pfd, 0, 1);
    if (rc < 0) return -errno;
    return rc;
}

int s13() {  // select()
    fd_set rs;
    FD_ZERO(&rs);
    struct timeval tv {};
    tv.tv_sec = 0;
    tv.tv_usec = 180;
    int rc = select(0, &rs, nullptr, nullptr, &tv);
    if (rc < 0) return -errno;
    return rc;
}

int s17() {  // nanosleep()
    struct timespec req {};
    req.tv_sec = 0;
    req.tv_nsec = 900000;
    struct timespec rem {};
    int rc = nanosleep(&req, &rem);
    if (rc < 0) return -errno;
    return rc;
}

int s19() {  // pause()
    int rc = pause();
    if (rc < 0) return -errno;
    return rc;
}
```

#### Error Transformation Logic
```cpp
std::array<int, 9> atlas() {
    std::array<int, 9> e = {
        EINTR, EAGAIN, EINVAL, EBUSY, EDOM, EPERM, ENOLCK, ETIMEDOUT, EPIPE
    };
    return e;
}

int normalize(int rc, std::uint64_t seed) {
    if (rc >= 0) return rc;
    auto e = atlas();

    int x = -rc;
    std::size_t i = mix64(seed ^ static_cast<std::uint64_t>(x * 257U), e.size());
    std::size_t j = mix64((seed << 1U) ^ 0x9e3779b97f4a7c15ULL, e.size());

    // Complex hash-based transformation logic...
    
    return -e[q];  // Returns transformed errno
}
```

## MCP Server Verification

### Step 6: EPIPE Error Code Lookup
**Tool**: MCP Server - linux-manpages
**Function**: `lookup_error_code`
**Parameter**: `EPIPE`

**MCP Response**:
```json
{
  "name": "send", "section": "2", "page": "sendto",
  "description": "send a message on a socket"
},
{
  "name": "sendmsg", "section": "2", "page": "sendto", 
  "description": "send a message on a socket"
},
{
  "name": "sendto", "section": "2", "page": "sendto",
  "description": "send a message on a socket"
},
{
  "name": "write", "section": "2", "page": "write",
  "description": "write to a file descriptor"
}
```

**Analysis**: EPIPE is only returned by write/send operations to broken pipes/sockets, not by the syscalls used in this program.

### Step 7: EINTR Error Code Lookup
**Tool**: MCP Server - linux-manpages
**Function**: `lookup_error_code`
**Parameter**: `EINTR`

**MCP Response**: Extensive list including:
- `select` - synchronous I/O multiplexing
- `poll` - wait for some event on a file descriptor
- `nanosleep` - high-resolution sleep
- `pause` - wait for signal
- Many other interruptible syscalls

**Analysis**: EINTR is the expected errno from interruptible syscalls when interrupted by signals.

## Manual Page Verification

### Step 8-11: Syscall Error Code Verification
**Commands**: 
- `man poll | grep -A5 -B5 EPIPE`
- `man select | grep -A5 -B5 EPIPE`
- `man nanosleep | grep -A5 -B5 EPIPE`
- `man pause | grep -A5 -B5 EPIPE`

**Results**: All returned "EPIPE not found" - confirming that none of these syscalls can legitimately return EPIPE.

## Errno Value Investigation

### Step 12: Errno Constants Check
**Command**: Created and compiled test program to check errno values
```cpp
#include <cerrno>
#include <iostream>
int main() {
    std::cout << "EINTR=" << EINTR << std::endl;
    std::cout << "EPIPE=" << EPIPE << std::endl;
    return 0;
}
```

**Result**:
```
EINTR=4
EPIPE=32
```

## Root Cause Analysis

### Execution Flow Analysis
1. **Signal Setup**: `arm(20000U)` sets up SIGALRM to fire after 20ms
2. **Syscall Sequence**: Calls `s11()`, `s13()`, `s17()`, then `s19()`
3. **Expected Behavior**: `pause()` should be interrupted by SIGALRM, returning EINTR (4)
4. **Actual Behavior**: The errno gets transformed by `normalize()` function

### Transformation Logic Breakdown
The `normalize()` function:
1. Takes the original errno (likely EINTR=4)
2. Applies complex hash functions (`mix64()`)
3. Uses the result to index into the `atlas()` array
4. Returns a different errno from the array (EPIPE=32 in this case)

### Key Evidence Points
1. **Syscall Incompatibility**: None of the used syscalls (`poll`, `select`, `nanosleep`, `pause`) can return EPIPE
2. **Artificial Transformation**: The `normalize()` function deliberately transforms errno values
3. **Atlas Array**: EPIPE is included in the transformation target array
4. **Deterministic but Lossy**: The transformation is deterministic but not reversible

## Conclusions

### 1. Observed Failure
Program exits with "fault:Broken pipe" (EPIPE) and exit code 2

### 2. Evidence
- EPIPE cannot come from the syscalls in the execution path (`poll`, `select`, `nanosleep`, `pause`)
- The `normalize()` function transforms errno values using hash-based array indexing
- EPIPE (32) is present in the `atlas()` transformation array at index 8
- MCP server confirmed EPIPE only comes from write/send operations

### 3. Root Cause
The `normalize()` function artificially transforms the legitimate errno (likely EINTR=4 from interrupted `pause()`) into EPIPE=32 through its hash-based selection algorithm, masking the true system error.

### 4. Reversibility Verdict
**Not reversible** - The transformation is a many-to-one mapping that loses original errno information. Multiple input errnos can map to the same output errno.

### 5. Minimal Correct Fix
Remove the `normalize()` calls in the `route()` function to preserve original errno values:

```cpp
int route(std::uint64_t seed) {
    int a = arm(20000U);
    if (a < 0) return a;

    int rc = s11();
    if (rc < 0) return rc;  // Remove normalize() call
    rc = s13();
    if (rc < 0) return rc;  // Remove normalize() call  
    rc = s17();
    if (rc < 0) return rc;  // Remove normalize() call
    rc = s19();
    if (rc < 0) return rc;  // Remove normalize() call
    return 0;
}
```

## Tools and Methods Used

### MCP Server Integration
- **linux-manpages server**: Used for authoritative errno code lookups
- **lookup_error_code function**: Verified which syscalls can return specific errno values
- **Exhaustive verification**: Confirmed EPIPE vs EINTR syscall compatibility

### System Analysis Tools
- **File reading**: Source code analysis
- **Shell commands**: Manual page verification, errno constant checking
- **Binary execution**: Failure reproduction and observation

### Logical Deduction
- **Syscall compatibility analysis**: Cross-referenced errno codes with syscall specifications
- **Code flow tracing**: Followed execution path through signal handling and error transformation
- **Hash function analysis**: Understood the deterministic but irreversible nature of errno transformation

This investigation demonstrates the critical importance of preserving original system error codes and the dangers of arbitrary error code transformation in system-level programming.