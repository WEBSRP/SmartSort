# Phase 09: Normalized Signal Processing & Feature Extraction

## Objective
Implement `src/core/file_intelligence/signals.py` (`SignalExtractor`, `LexicalTokenizer`) to extract, tokenize, normalize, and weigh evidence signals from `FileContext` metadata, producing a standardized `SignalSet` with domain affinity vectors.

## Why This Phase Exists
Raw text, filenames, and metadata attributes vary widely in syntax and noise. The Signal Extractor normalizes these heterogeneous inputs into structured, weighted features that power deterministic clustering and multi-signal classification.

## Inputs
- `FileContext` populated with metadata and origin info.

## Outputs
- `src/core/file_intelligence/signals.py` (`SignalExtractor`, `LexicalTokenizer`).
- Tests in `tests/test_file_intelligence/test_signals.py`.

## Files To Create
- `src/core/file_intelligence/signals.py`
- `tests/test_file_intelligence/test_signals.py`

## Files To Modify
- `src/core/file_intelligence/__init__.py`: Export `SignalExtractor`, `LexicalTokenizer`.
- `src/core/file_intelligence/context.py`: Add the documented `Signal` and
  `SignalSet` models (not present in the foundation), `EXTENSION_HINT`, and
  JSON serialization for populated signal sets. Preserve `signals=None`.
- `tests/test_file_intelligence/test_context.py`: Update the enum's expected
  member set/count for the new extension-hint channel.

## Existing Components To Reuse
- `src/core/file_intelligence/context.py`: Populates `SignalSet`, `Signal`, `SignalType`.

## APIs / Interfaces
```python
# src/core/file_intelligence/signals.py
class LexicalTokenizer:
    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Decomposes camelCase, snake_case, alphanumeric strings into clean tokens."""
        ...

    @staticmethod
    def canonicalize(token: str) -> str:
        """Maps synonyms and abbreviations to canonical forms."""
        ...

class SignalExtractor:
    def extract_signals(self, context: FileContext) -> SignalSet:
        """Extracts weighted signals across all fields in FileContext."""
        ...
```

## Data Structures
- Consumes and populates `SignalSet` from `src.core.file_intelligence.context`.

## Algorithms
- CamelCase/acronym splitting uses fixed-width boundaries, including the
  boundary between `DBMS` and `Lecture` in `DBMSLecture03`. Greedy acronym
  prefix patterns are avoided to prevent quadratic work on uppercase runs.
- Delimiter and punctuation normalization: `[_\-.\s/]+`.
- Stop-word filtering: Removes noise tokens (`the`, `and`, `final`, `copy`, `download`).
- Canonical term dictionary mapping (`hw` $\rightarrow$ `assignment`, `db` $\rightarrow$ `database`, `sec` $\rightarrow$ `security`).
- `tokenize()` performs lexical splitting and noise removal; `canonicalize()`
  separately folds aliases. `DBMSLecture03` tokenizes to `dbms, lecture, 03`;
  extraction canonicalizes `db`, `dbms`, `sql`, and `database` to `database`.
  Direct `canonicalize('asgn1')` returns `assignment`; extraction keeps the
  numeric series token separately. Mappings are idempotent and explicit.
- Weighted signal aggregation:
  - Document Title: 0.90
  - Origin Domain: 0.85
  - Headings: 0.75
  - Filename Tokens: 0.65
  - Code Symbols: 0.65
  - Content Text: 0.50
  - Parent Directory: 0.40
  - Archive Content: 0.70
  - Media Metadata / Allowlisted EXIF: 0.50
  - Extension Hint: 0.20

## Error Handling
- Null/empty string safety; gracefully handles missing metadata fields.

## Security Considerations
- Pure text transformation; zero execution of code or external inputs.

## Performance Considerations
- Tokenization and feature extraction executes in < 0.2 ms per file.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_signals.py`:
  - Test camelCase, snake_case, and alphanumeric tokenization (`DBMSLecture03` $\rightarrow$ `['dbms', 'lecture', '03']`).
  - Test canonicalization mapping (`asgn1` $\rightarrow$ `assignment`).
  - Test multi-field signal weight generation.
  - Test domain affinity calculation.

## Acceptance Criteria
- [x] `LexicalTokenizer` and `SignalExtractor` implemented.
- [x] High-frequency noise words cleanly filtered.
- [x] 100% test pass on `test_signals.py`.

## Dependencies
- Standard library `re`, `typing`.

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [x] `signals.py` implemented.
- [x] Unit tests passing.

## Implementation State — 2026-11-15

Phase 09 functional acceptance is complete in the working tree. This phase adds
only standard-library transformations and models; no packages, NLP corpora,
network clients, or runtime organizer integrations were added.

Implemented behavior:

- Lexical splitting handles acronym/camel boundaries, snake/kebab/punctuation
  delimiters, letter/digit boundaries, and leading zeroes. Unicode is NFC
  normalized and case-folded. English/web/filename noise is removed.
- Canonicalization uses a direct alias/plural dictionary rather than blanket
  suffix stripping. The phase's `db -> database` rule is the canonical database
  family, resolving the earlier overview's conflicting `dbms` spelling.
  Known phrases such as operating system(s) fold to `os` during extraction.
- All documented channels carry their exact base weights. Titles, headings,
  stems, code symbols/language, keywords/previews, subjects/authors, archive
  paths, immediate parent names, validated origins, allowlisted camera tags,
  and weak format hints produce field-attributed `Signal` objects.
- Identical canonical tokens are deduplicated **within a signal type**. Repeated
  headings/keywords/TOC entries do not multiply the same feature. A token from
  separate types (for example title and filename) remains separate evidence.
- Origins contribute validated hostname and locally derived site labels only.
  URL paths, userinfo, queries, fragments, free-form origin evidence, and
  unverified friendly labels are not tokenized. EXIF uses only Make, Model,
  Software, and LensModel; GPS, dates, and arbitrary tag keys are excluded.
- Parent context uses only the immediate directory basename, with no stat,
  filesystem traversal, or username/ancestor tokenization. Numerical media
  properties, timestamps, and filesystem attributes remain in the context for
  their later consumers rather than becoming free-text features here.
- Domain vectors sum `signal.weight * token_affinity` and divide each positive
  domain sum by the total. Unknown tokens add no domain affinity. Scores are
  relative feature affinities, **not classification confidence**; even one
  weak archive-format hint can yield relative `Archives=1.0`.
- `extract_signals()` returns a fresh `SignalSet` and assigns it only to
  `context.signals`. Repeated calls replace the set without appending evidence
  or modifying metadata, origin, classification, confidence, or destinations.

Models and bounds:

- `Signal` is frozen, field-attributed, and validates finite [0,1] weights.
  `SignalSet` has independent token/signal/affinity containers and JSON-safe
  serialization with sorted token and affinity keys. `FileContext` round-trips
  populated sets while retaining `None` and unrecognized legacy dictionaries.
- Individual tokenizer calls sample at most **4,096 characters**, emit at most
  **512 tokens**, and omit tokens over **64 characters**. The public single-term
  canonicalizer accepts at most 128 characters. Numbers remain strings.
- Extraction samples at most **65,536 lexical characters** in priority order
  and emits at most **2,048 signals**. Per-field caps mirror existing extractors:
  titles 256 characters, stems 512, headings 64 x 256, code symbols 128 x 256,
  keywords 20 x 128, previews 1,024, and archive entries 500 x 1,024. Origins
  separately use the prior stage's bounded URL/hostname validation.
- Null/empty metadata is safe. Malformed field values and unsupported collection
  types are ignored without stringifying arbitrary objects. This is bounded
  prefix sampling, not complete analysis of arbitrarily large metadata.

Validation on Python 3.13.5:

- **117 Phase 09 tests passed**, no failures or skips.
- **952 full-suite tests passed, 1 existing skip**, genuine pytest return code
  **0**. Baseline was **835 passed, 1 skipped**. The existing skip is the
  Phase 02 permission test under a privileged user.
- Tests cover lexical examples, alias idempotence, Unicode/numbers, all channel
  weights and field provenance, per-channel deduplication, exact affinity
  arithmetic, multiple domains, null/malformed/bounded inputs, privacy
  filtering, extreme acronym/combining sequences, concurrency, immutable
  signals, schema validation, JSON/backward compatibility, hash-seed-independent
  serialization, and fresh-process Qt-free imports.
- Synthetic text/origin and ZIP-extractor results are fed through the signal
  API without file movement. No-I/O checks prohibit file opens/stat/scandir,
  DNS lookups, and connections during transformation.
- Compilation and whitespace checks pass. Test state/bytecode use temporary
  locations, and the runner preserves pytest's actual status before the
  existing Qt teardown exit-zero backstop.

Performance observations (100 warm extractions per synthetic context):

| Context | First observed call | Warm median | Warm maximum | Signals |
|---|---:|---:|---:|---:|
| Filename + immediate parent + extension | 0.1246 ms | 0.0283 ms | 0.0506 ms | 5 |
| Document title/headings/content + origin | 0.9091 ms | 0.0891 ms | 0.1395 ms | 18 |
| 500 archive paths + file context | 3.3888 ms | 3.6571 ms | 5.7239 ms | 508 |

The **0.2 ms target is met by these warm filename/document fixtures**, but not
the first document call or the 500-entry archive fixture. These are local
observations, not universal latency bounds. Large metadata remains bounded;
the all-files 0.2 ms performance target remains outstanding.

Remaining boundaries:

- English-oriented aliases/affinities are heuristics, not semantic entailment,
  language-wide lemmatization, or proof of domain membership. Ambiguous terms
  such as `test`/`sec` retain the documented alias meanings; later classification
  must evaluate corroboration. Non-English tokens are preserved where possible
  but have no inferred affinity unless present in the dictionary.
- Auxiliary affinities (`Code`, `Images`, `Audio`, `Videos`, `Personal`) coexist
  with broad domains for later scoring. This phase does not choose a domain,
  compute confidence, generate hierarchy, cluster files, or change user rules.
- Lists retain caller order; repeated terms are binary per-channel features,
  not term-frequency or TF-IDF scores. Different channels are preserved but
  are not guaranteed statistically independent. Metadata caps can omit evidence.
- Existing GUI, packaging, origin queries, organizers, and safe transfer logic
  are unchanged. Earlier pending work remains intact. Changes are uncommitted.

Next implementation phase: **10 — File Relationship Discovery & Cluster Analysis**.
