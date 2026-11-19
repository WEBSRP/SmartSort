# Content intelligence file-type fallback — SmartSort 1.2.4

Implemented and verified on 2026-11-19. The user screenshot showed 1.2.3 with Content intelligence enabled and recognized installers/text going to Others.

## Cause and change

The classifier deliberately gives extension-only hints low semantic confidence. The planner then routed every unknown semantic classification to Others, even when its file format was recognized. Only extraction failures previously used type-based routing. Consequently a successful but uninformative extraction could sort less usefully than a failed one.

The planner now uses a shared deterministic file-type destination when semantic evidence is insufficient or the classifier returns Others. Download and folder error fallbacks use the same helper. Known video formats route to Videos, audio to Audio, ordinary documents/text to Documents, images to Images, archives to Archives and installer formats including DEB/AppImage/APK/XAPK to Applications. Strong semantic classifications retain their hierarchy; custom rules retain precedence in Rules first mode. Classifier scores and hint weights were not inflated to manufacture semantic certainty. Fallback proposals explicitly state UNKNOWN confidence with zero score and explain the file-type fallback.

## Verification

- Full suite: **1,575 passed, 1 existing skip**, natural exit 0, in 39.36 seconds.
- Teardown inventory contained no Python threads, running QThreads, active QTimers or child processes.
- 44 new regression cases compare automatic downloads and folder previews across successful, unsupported and corrupted extraction outcomes, preserve genuinely unknown binary files in Others, preserve meaningful Invoice content classification and custom rules, and verify transferred bytes.
- Existing low-confidence planning, extraction opt-out and ambiguous ZIP tests were updated to expect useful file-type destinations while retaining UNKNOWN semantic confidence and opt-out privacy checks.
- 80 live watcher cases passed in a contained folder under Downloads, including a real one-second generated MP4 and neutral text/installer samples. Transfers retained SHA-256 checks; duplicates, collisions, partial downloads, size boundaries and approval checks passed.
- Extracted 1.2.4 package was checked with system Python for MP4, text, DEB, AppImage and XAPK fallback proposals, in addition to the existing cache/transfer/report smoke test.
- Packaged production sources match the workspace; archive ownership, executable modes, desktop entry and icon ownership checks passed.

The previous 1.2.3 matrix checked byte integrity for generic files, but lacked independent destination assertions for these Content intelligence cases. This validation adds explicit expected destinations.

## Representative live destinations

- `4739201.mp4` → `Videos/4739201.mp4` (SUCCESS)
- `common.txt` → `Documents/common.txt` (SUCCESS)
- `sample_amd64.deb` → `Applications/sample_amd64.deb` (SUCCESS)
- `sample.AppImage` → `Applications/sample.AppImage` (SUCCESS)
- `sample.xapk` → `Applications/sample.xapk` (SUCCESS)

## Artifacts and use

Samples: `/home/websrp/Downloads/SmartSort-QA-1795059498477611388`. Existing user files were not moved.

Evidence: `build/validation/type-fallback/`, `build/validation/downloads/type-fallback.json`, `build/validation/version-1.2.4/`.
Package: `build/deb/smartsort_1.2.4_all.deb` (13,671,188 bytes).
SHA-256: `662eddc62a335583891a3f81c71f8625e3766f1948095b8c4fc0a1128ba864ce`.

Install 1.2.4, then exit and relaunch SmartSort. This build has not been installed automatically; sudo previously required the user’s local password. Files already moved to Others remain in place. They can be reviewed with Organize folder after upgrading; the new-download watcher does not rescan existing files.

```sh
sudo apt install /home/websrp/SmartSort/build/deb/smartsort_1.2.4_all.deb
```
