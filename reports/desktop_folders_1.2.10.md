# Existing desktop destination folders — SmartSort 1.2.10

Implemented 2026-11-19 after the user confirmed use of their Linux desktop defaults.

## Change

Home-based download routes and both tester inputs now use desktop Pictures, Videos, Music and Documents locations. Images/Media image routes collapse into Pictures; audio routes use Music. College, Work, Code, Projects and Cybersecurity retain their semantic hierarchies inside Documents. Archives, Applications, Others and generic Media use category folders inside Downloads. Recognized standard prefixes in saved rules also map to desktop locations; unrelated custom rules retain their own paths.

Settings includes a saved use_desktop_folders preference, default true, with read-only detected location summaries. Explicit custom destination bases are respected. Folder-batch planning retains its selected root and does not silently acquire external destinations. Existing files in former category folders have not been migrated automatically.

The parser reads bounded user-dirs.dirs data without running shell text. Mapped roots can be localized, symlinked or outside Home. Planner routing selects the approved root before checking containment, allowing a legitimate desktop symlink while rejecting escapes below that root. Transfers snapshot the mapping and revalidate it before copying or removing sources. Classified domain labels remain semantic; mapped proposal relative paths are relative to the chosen destination root.

## Validation

- **Full suite: 1,704 passed, 1 existing skip in 64.91 seconds**, natural exit 0.
- Teardown inventory had no Python threads, running QThreads, active QTimers or child processes.
- Twenty-three new cases cover filename and real-file destinations, semantic images, academic/work content, standard rule prefixes, custom roots/rules, opt-out, localized/external folders, symlink safety, changed mappings during duplicate hashing, reviewed batch containment, non-executing parsing and GUI preference persistence.
- Focused desktop-folder + GUI suite: 96 passed.
- Real samples were sorted into the actual desktop folders listed below; every byte/hash check passed. A repeated image copy produced DUPLICATE, removed only the test source and retained the native Pictures destination. Existing personal files/settings were not changed.
- Extracted system-Python package smoke verifies desktop routing, external desktop symlink transfer, source-byte preservation and Documents/Code/Shell previews, in addition to prior-release checks. Production-source parity, ownership, executable modes, desktop entry and shared-icon checks passed.

## Live sample destinations

- PICTURES: `/home/websrp/Pictures/SmartSort-QA-1795083897127718906-image.png`
- VIDEOS: `/home/websrp/Videos/SmartSort-QA-1795083897127718906-video.mp4`
- MUSIC: `/home/websrp/Music/SmartSort-QA-1795083897127718906-audio.wav`
- DOCUMENTS: `/home/websrp/Documents/Work/Invoices/SmartSort-QA-1795083897127718906-invoice.md`

Test source folder: `/home/websrp/Downloads/.SmartSort-Desktop-QA-1795083897127718906`. Generated sample files remain available for inspection.

Package: `build/deb/smartsort_1.2.10_all.deb` (13,678,144 bytes).
SHA-256: `519b8e4434168f02b4214d10ccb77d443009055f7790bc5e1edccadde82eff27`.

Evidence: `build/validation/desktop-folders/` and `build/validation/version-1.2.10/`.

Install and fully restart SmartSort to load the new package. It has been built and checked, not installed automatically.

```sh
sudo apt install /home/websrp/SmartSort/build/deb/smartsort_1.2.10_all.deb
```

Reference: [freedesktop.org XDG user directories](https://wiki.freedesktop.org/www/Software/xdg-user-dirs/).
