# Standalone code intelligence and project boundaries — SmartSort 1.2.9

Implemented on 2026-11-19 following the filename-only fix_click.sh tester example
and the requirement to preserve complete project folders.

## Change

Filename/type-only previews now group recognized standalone code by a fixed
language vocabulary: Code/Shell, Code/Python, Code/JavaScript and analogous
folders for other supported suffixes. Unknown semantic confidence remains
honest; the tester now explicitly says file type recognized, content confidence
UNKNOWN rather than presenting zero percent as if the file type were unknown.

Real source metadata classifications in Projects/Source add the extracted
language, e.g. Projects/Source/Shell/fix_click.sh. Explicitly named project
hierarchies, configured user rules and academic/other semantic routes keep
precedence. Unsupported/failed extraction retains a useful Code/language fallback.
No source code is executed and arbitrary language metadata cannot become a path.
The classifier's domain confidence weights were not inflated for extensions.

Project protection now also recognizes requirements.txt, setup.py/setup.cfg,
__init__.py, Makefile/Dockerfile and other common build/package manifests.
Selecting an internal src/assets folder or an internal file in the tester no
longer bypasses its detected enclosing project. Parent checks are bounded at
12 ancestors and stop at home/system/common collection roots. Detection remains
heuristic; .smartsort-ignore explicitly protects any custom project layout.

## Verification

- Full suite: **1,681 passed, 1 existing skip**, natural exit 0.
- No Python threads, running QThreads, active QTimers or child processes remained.
- Twenty-four new cases cover filename language groups, real Shell/Python/JS/C++
  parsing, unavailable extraction, cross-workflow destination parity, project
  manifests/internal subfolders, untrusted language values and tester labels.
- Focused code + bundle + GUI checks: 115 passed.
- The older Makefile integration fixture expected four project files to be moved
  separately. It now requires an empty plan, unchanged file bytes and paths, and
  no newly created nested project directory, matching the user's preservation
  requirement. The complete rerun passed.
- Live check in `/home/websrp/Downloads/.SmartSort-Code-QA-1795066390721136992`: two loose source files moved by folder execution
  and two by automatic monitoring; three complete projects with nine inventoried
  files remained byte-identical; a selected internal project subfolder produced
  an empty preview; no project files generated processing callbacks.
- Visually inspected the exact fix_click.sh / 5MB example in both themes.
  Screenshots are in build/validation/code-intelligence/code-tester-dark.png and
  code-tester-light.png. Destination is Code/Shell/fix_click.sh with clear
  filename-only analysis scope and unknown content confidence.
- Extracted package/system-Python smoke verifies code language previews and real
  source routing plus enclosing project protection. Existing transfer, cache,
  duplication, recursion and tester checks also pass.

Package: build/deb/smartsort_1.2.9_all.deb (13,676,668 bytes).
SHA-256: e01e20c169f573e83d88a06912c3c9d94bd712932c34880759912928d51a74e3.
Evidence: build/validation/code-intelligence/ and build/validation/version-1.2.9/.

Install and restart SmartSort. Use Existing file for actual content/code metadata;
filename-only testing cannot infer what a script does. Tests used generated data
and did not alter personal project trees. This package has not been installed
automatically and cannot reconstruct files separated by an older release.

```sh
sudo apt install /home/websrp/SmartSort/build/deb/smartsort_1.2.9_all.deb
```
