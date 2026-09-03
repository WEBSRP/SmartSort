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
- CamelCase regex splitting: `r'([a-z])([A-Z])'`.
- Delimiter and punctuation normalization: `[_\-.\s/]+`.
- Stop-word filtering: Removes noise tokens (`the`, `and`, `final`, `copy`, `download`).
- Canonical term dictionary mapping (`hw` $\rightarrow$ `assignment`, `db` $\rightarrow$ `database`, `sec` $\rightarrow$ `security`).
- Weighted signal aggregation:
  - Document Title: 0.90
  - Origin Domain: 0.85
  - Headings: 0.75
  - Filename Tokens: 0.65
  - Code Symbols: 0.65
  - Content Text: 0.50
  - Parent Directory: 0.40

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
- [ ] `LexicalTokenizer` and `SignalExtractor` implemented.
- [ ] High-frequency noise words cleanly filtered.
- [ ] 100% test pass on `test_signals.py`.

## Dependencies
- Standard library `re`, `typing`.

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [ ] `signals.py` implemented.
- [ ] Unit tests passing.
