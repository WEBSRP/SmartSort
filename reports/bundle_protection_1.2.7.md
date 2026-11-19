# Application/project bundle protection — SmartSort 1.2.7

Implemented 2026-11-19 in response to recursive sorting separating an app's logo
from its other files.

## Change

A shared folder guard excludes recognizable cohesive directories from both
recursive folder organization and Downloads monitoring. It recognizes app bundle
suffixes, AppRun, Electron ASAR layouts, source project manifests/Git metadata,
extracted Debian packages and portable executable/resource combinations. These
folders remain intact in place; the implementation does not move a directory as
an indivisible new operation. Ordinary nested photo/document folders continue to
sort recursively, and a loose AppImage/installer remains sortable.

An empty `.smartsort-ignore` marker protects any custom folder. Recognition uses
bounded names/metadata and optional four-byte ELF headers, without executing apps
or reading their image assets. Scan traversal prunes protected subtrees. Explicit
plan inputs, source revalidation and download processing reject protected assets;
queued watcher events are rechecked before callback. Selecting a protected root
returns an empty preview with an explanation.

Recognition is heuristic, not knowledge of every application's layout. A bundle
can only be recognized once its identifying files exist. The live queue test
covers a logo arriving before AppRun but receiving the marker before processing.
For marker-less/custom apps, create `.smartsort-ignore` first or extract into an
already marked directory. Assets previously moved by older versions are not
automatically reconstructed.

## Verification

- **Full suite: 1,633 passed, 1 existing skip in 49.52 seconds**, natural exit 0.
- No Python threads, running QThreads, active QTimers or child processes remained.
- Nineteen new cases cover ten app/project/custom bundle structures, manual plan
  bypass attempts, direct and watched downloads, unchanged loose-file sorting,
  selecting a bundle root, a marker added after review, and a queued logo event
  cancelled when the app structure becomes recognizable.
- Focused bundle + recursive suite: 30 passed.
- Live isolated Downloads check preserved three batch bundles and all nine
  inventoried internal files, sorted one loose nested batch file and one new
  nested download, and generated zero callbacks for protected bundle assets.
  A new portable app's logo and AppRun remained together. Content hashes of all
  protected batch files remained unchanged.
- The live test used `/home/websrp/Downloads/.SmartSort-Bundle-QA-1795062258725644172`. Its hidden outer folder isolates generated
  samples from an older running SmartSort's recursive watcher. Personal app files
  were not modified or repaired during this test.
- Extracted system-Python package checks verify bundled asset exclusions from
  scans/manual plans, direct download preservation and watcher exclusion, along
  with existing recursive, duplicate-removal, file-type and archive checks.

Evidence: `build/validation/bundle-guard/` and
`build/validation/version-1.2.7/`.
Package: `build/deb/smartsort_1.2.7_all.deb` (13,674,044 bytes).
SHA-256: `e0e005866acfaeed6168b5953a2ad76d2e7cff3f77528f3db77e17484a78ed32`.

Install and restart SmartSort to apply the fix. The built package has not been
installed automatically.

```sh
sudo apt install /home/websrp/SmartSort/build/deb/smartsort_1.2.7_all.deb
```
