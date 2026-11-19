# Intelligent Rule Tester — SmartSort 1.2.8

Implemented and verified on 2026-11-19 at the user's request.

## Behavior

Rule Tester follows the saved sorting mode and offers two inputs:

- Filename and size: uses rule conditions, filename signals and known-type
  fallback, without creating a pretend file or claiming content extraction.
- Existing file: runs the automatic download analysis path in a background worker
  with a copied settings/rules snapshot. This honors content/origin extraction,
  filename cleanup, user-rule precedence/bypass, fallback and bundle protection.

Results show the decision, optional matched rule priority, full destination,
classification confidence and supporting evidence. The selected file is never
transferred or removed. The tester does not execute duplicate deletion,
collision resolution or approval flows. Private metadata-cache activity during
real-file analysis remains possible, as in ordinary analysis.

Inputs/routing-policy changes invalidate an earlier result and stale queued
results are discarded. A changed theme does not invalidate an otherwise current
analysis. Errors release the worker/button and display plain-text explanations.
Only one existing-file test can be active at a time. Filename tests remain fast
and synchronous. Literal rule/path text is preserved as plain text.

The optional extension now fills a missing filename suffix rather than overriding
an existing one; e.g. an MP4 filename no longer acquires the old default JPG suffix.

## Validation

- **Full suite: 1,657 passed, 1 existing skip in 43.02 seconds**, natural exit 0.
- No Python threads, running QThreads, active QTimers or child processes remained.
- 24 new cases cover mode policy, filename/type fallbacks, size boundaries,
  real content analysis, no-transfer/no-delete behavior, disabled extraction,
  protected bundles, invalid inputs, missing files, async UI recovery, changed
  inputs/settings/rules, theme changes and optional extension semantics.
- Visually inspected dark and light screenshots in
  `build/validation/rule-tester/tester-dark.png` and `tester-light.png`. The real
  existing-file Invoice sample displayed Work/Invoices with evidence and remained
  untouched. Existing page/minimum-size checks passed in the full GUI suite.
- Extracted package/system-Python checks verified read-only real-file intelligence,
  filename MP4 fallback, Rules first matching, no destination-directory creation,
  source-byte preservation and the existing prior-release smoke checks.
- Production sources match packaged contents, including `sorting_tester.py` and
  the updated main window. Archive ownership, executable modes, desktop entry,
  shared icon safety and dependency checks passed.

Evidence: `build/validation/rule-tester/` and
`build/validation/version-1.2.8/`.
Package: `build/deb/smartsort_1.2.8_all.deb` (13,675,824 bytes).
SHA-256: `cb3b1eff5d64d0d691793ab54fb51f421dd1b1bba783ab4d2bf48b0c5ae5cef6`.

## Use

Install and fully restart SmartSort. In Rule Tester, choose Existing file —
content analysis, browse to a file, and click Test sorting. Change mode opens
Settings; save Content intelligence to bypass saved routing rules. Filename/size
input remains available for hypothetical tests. This package was built and
verified, not automatically installed.

```sh
sudo apt install /home/websrp/SmartSort/build/deb/smartsort_1.2.8_all.deb
```

See `docs/rule-tester.md` for the scope of each input mode.
