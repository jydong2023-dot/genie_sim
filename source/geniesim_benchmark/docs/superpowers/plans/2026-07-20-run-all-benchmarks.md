# Run All Benchmarks Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide one executable container-side Bash script that runs every packaged G1 and G2 benchmark once with the configured policy, result output, and recording enabled.

**Architecture:** Add a repository-root launcher that delegates to the existing `geniesim benchmark batch` command for `g1op` and `g2op`. When invoked as root, it re-executes itself as the container's `isaac-sim` user so all output is owned by UID/GID 1000.

**Tech Stack:** Bash, GNU `runuser`, Genie Sim CLI, Isaac Sim Python launcher.

---

### Task 1: Add the container launcher

**Files:**
- Create: `run_all_benchmarks.bash`

- [x] **Step 1: Create the script**

Add strict unset-variable and pipeline handling, configurable `POLICY_ENDPOINT`, automatic root-to-UID-1000 re-execution, the Isaac Sim NumPy library path, and sequential `g1op`/`g2op` batch calls. Each call must set one episode, one instance, vector mode off, recording on, and must not enable preview.

- [x] **Step 2: Make it executable**

Run:

```bash
chmod +x run_all_benchmarks.bash
```

- [x] **Step 3: Validate syntax and command contract**

Run:

```bash
bash -n run_all_benchmarks.bash
rg -n 'benchmark batch|g1op g2op|benchmark.record=true|benchmark.num_episode|benchmark.num_instances|benchmark.enable_vec' run_all_benchmarks.bash
```

Expected: `bash -n` exits 0 and all required batch flags are present.

- [x] **Step 4: Check formatting and scope**

Run:

```bash
git diff --check -- run_all_benchmarks.bash
git status --short -- run_all_benchmarks.bash
```

Expected: no whitespace errors and only the new launcher is reported for this scope.

No commit is created because this checkout is on `main` with unrelated user-owned changes and the user requested a directly runnable workspace file.
