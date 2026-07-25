# GitHub Actions CI Report

This report documents the design and integration of the automated Continuous Integration workflow.

---

## 1. Workflow Architecture

The CI pipeline is defined inside [.github/workflows/ci.yml](file:///home/websrp/SmartSort/.github/workflows/ci.yml) and runs on every push and pull request to `main`.

It divides execution into two parallel/dependent jobs:

### Job 1: `test`
- **Environment**: `ubuntu-latest`
- **Steps**:
  1. Checks out source code.
  2. Sets up Python 3.12.
  3. Installs graphic libraries dependencies (`libgl1-mesa-dev`, `libxkbcommon-x11-0`, `libegl1-mesa-dev`, `libdbus-1-3`) to support headless PyQt6 test suite runs.
  4. Installs Python packages.
  5. Verifies syntax compilation using `compileall`.
  6. Runs `pytest` test suites.

### Job 2: `build` (depends on `test`)
- **Environment**: `ubuntu-latest`
- **Steps**:
  1. Checks out source code.
  2. Installs Debian build packaging tools.
  3. Compiles the Debian `.deb` package.
  4. Compiles the AppImage package.
  5. Uploads the generated release binaries as downloadable build artifacts (`SmartSort-Packages`).
