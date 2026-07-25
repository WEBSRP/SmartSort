# Contributing to SmartSort

Thank you for your interest in contributing to SmartSort! We welcome community contributions to help improve this file organizer.

## How to Contribute

### 1. Report Bugs or Request Features
Please search existing issues before submitting a new bug report or feature request. Use the appropriate template in the [.github/ISSUE_TEMPLATE/](file:///home/websrp/SmartSort/.github/ISSUE_TEMPLATE) folder.

### 2. Development Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/smartsort-org/SmartSort.git
   cd SmartSort
   ```
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

### 3. Running Tests
We use pytest for testing. Ensure all tests pass before submitting a pull request:
```bash
python3 -m pytest tests/
```

### 4. Code Hygiene & Formatting
- Follow PEP 8 style guidelines.
- centralize all file paths using [AppPaths](file:///home/websrp/SmartSort/src/utils/paths.py).
- Do not commit generated packages or caches.

### 5. Submit a Pull Request
1. Fork the repository and create your branch from `main`.
2. Commit your changes with clear, descriptive commit messages.
3. Fill out the pull request template inside [.github/pull_request_template.md](file:///home/websrp/SmartSort/.github/pull_request_template.md).
4. Ensure the GitHub Actions CI workflow passes.
