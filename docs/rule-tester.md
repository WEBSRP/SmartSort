# Rule Tester and Content intelligence

Rule Tester previews routing without moving, copying or removing the selected
file. It follows the saved sorting mode shown at the top of the page. Use Change
mode to open Settings, choose Rules first or Content intelligence, and save.

## Test a real file

Choose **Existing file — content analysis**, browse to a file, then click
**Test sorting**. The same bounded analysis used for an automatic download
predicts its full destination. Results show the rule or intelligence decision,
rule priority when applicable, classification confidence, and supporting reasons.
Analysis runs in a background worker so the window remains usable.

Rules first preserves matching saved rules and runs intelligence for unmatched
files. Content intelligence bypasses saved routing rules. Browser-origin,
deep-extraction and filename-cleanup settings are honored. Known-type fallback
and app/project bundle protection behave as in download analysis. Unsupported or
unreadable files produce the existing fallback/error behavior, without execution.

## Test a hypothetical filename

Choose **Filename and size**. Enter the name and size; the optional extension
fills in a missing suffix and never overrides an extension already in the name.
The tester evaluates rules and filename/type intelligence. It does not invent a
real file or claim to read document contents, metadata or browser history. Select
an existing file when those signals matter.

## Scope

Confidence describes the semantic classification, not a probability. A recognized
file type can give a useful destination with UNKNOWN semantic confidence.

The tester predicts routing; it does not perform a duplicate hash comparison,
collision resolution, large-video approval or transfer. It also does not batch
cluster sibling files. Use Organize folder for a reviewed recursive batch preview.
Real-file analysis may use the application's private metadata cache; source and
destination file contents remain untouched.

Changing inputs, saved routing settings or rules invalidates the result. Queued
results for an older request are discarded. Theme changes do not invalidate an
otherwise current analysis.

## Loose code and complete projects (1.2.9)

Standalone source files now receive fixed language folders. A filename-only
`fix_click.sh` test yields `Code/Shell/fix_click.sh`; Python, JavaScript,
TypeScript, C/C++, Java, Rust, Go and other recognized suffixes have analogous
folders. This identifies a source type without claiming to know the script's
purpose. File-type-only tester results say the type is recognized while content
confidence remains UNKNOWN. Use Existing file to inspect actual code metadata.

When actual source metadata classifies a loose file as `Projects/Source`, its
language is appended, e.g. `Projects/Source/Python/helper.py`. Explicitly named
project hierarchies, custom rules and strong academic/other semantic routes
retain precedence. Language folder names come from a fixed vocabulary; arbitrary
metadata strings cannot become path components. No source code is executed.

Projects remain intact. Common Python/build/package markers now include
requirements.txt, setup.py/setup.cfg, __init__.py, Makefile, Dockerfile and the
previous project manifests. Selecting a project's src/assets subfolder or
selecting an internal file in the tester does not bypass a detected enclosing
project boundary. Parent detection is bounded and stops at home, system and
common collection roots. Recognition remains heuristic: put an empty
`.smartsort-ignore` in any custom project that lacks a recognized structure.

Home-based tests also apply the saved Linux desktop-folder preference, so their
absolute destinations match automatic download routing. See
[desktop destination folders](desktop-folders.md).

### Preview a file's purpose

In Content intelligence mode, try `leetcode_two_sum.png` or
`forest_wallpaper.jpg`. With desktop defaults enabled, the preview sends them
to `Pictures/Coding_Challenges` and `Pictures/Wallpapers` respectively. A
numbered image with no useful clues goes directly in Pictures. SmartSort uses
local evidence such as filenames, available document text and download origin.
It does not read text from image pixels.

To teach a preference, open **Rules**, add a filename condition and destination,
and select **Use this rule in Content intelligence**. Save it and try a matching
filename in **Rule Tester**. New rules in the editor have this option selected
by default. Existing rules can be enabled individually. Recognized project and
application folders stay protected even when an internal file matches a rule.
