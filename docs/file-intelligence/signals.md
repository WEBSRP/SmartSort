# SmartSort File Intelligence Engine: Signal Processing

## 1. Overview

The Signal Processing Layer converts raw text, metadata, filenames, and origin URLs into a normalized, weighted set of **Signals** (`SignalSet`). These signals provide the quantitative input for both the **Relationship & Clustering Engine** and the **Multi-Signal Classifier**.

---

## 2. Tokenization & Feature Normalization

### 2.1 Lexical Tokenizer
Raw strings (filenames, headings, document titles) are decomposed into clean lexical tokens:
1. **Delimiter Splitting**: Splits on `_`, `-`, `.`, spaces, and punctuation.
2. **CamelCase Decomposition**: Splits `DatabaseManagementSystem` $\rightarrow$ `['database', 'management', 'system']`.
3. **Alphanumeric Separation**: Splits `Lecture3` $\rightarrow$ `['lecture', '3']`, `CS101` $\rightarrow$ `['cs', '101']`.
4. **Stop-Word Removal**: Filters common language and web noise (`the`, `and`, `for`, `with`, `download`, `copy`, `untitled`, `final`).
5. **Stemming & Canonical Mapping**: Maps synonyms and abbreviations to canonical forms:
   - `assignment`, `asgn`, `hw`, `homework` $\rightarrow$ `assignment`
   - `lecture`, `lec`, `slides`, `ch` $\rightarrow$ `lecture`
   - `exam`, `midterm`, `quiz`, `test` $\rightarrow$ `exam`
   - `dbms`, `database`, `sql` $\rightarrow$ `dbms`
   - `os`, `operating_system` $\rightarrow$ `os`
   - `sec`, `vuln`, `exploit`, `cve` $\rightarrow$ `security`

---

## 3. Signal Types & Base Weights

Signals carry explicit base weights reflecting their reliability as classification evidence:

| Signal Type | Base Weight | Description | Example |
|---|---|---|---|
| `DOCUMENT_TITLE` | **0.90** | Authoritative title in document metadata | `"Database Normalization Lecture 3"` in PDF `/Title` |
| `ORIGIN_DOMAIN` | **0.85** | Verified source domain from xattr or browser DB | `canvas.stanford.edu` or `github.com` |
| `DOCUMENT_HEADING`| **0.75** | Section headings or slide titles | `# Chapter 4: Relational Algebra` in DOCX/MD |
| `ARCHIVE_CONTENT` | **0.70** | Internal file types and folder names in archive | Archive contains `.c`, `.h`, `Makefile` |
| `FILENAME_TOKEN`  | **0.65** | Meaningful tokens from sanitized filename stem | `"Lecture_3_DBMS"` $\rightarrow$ `['lecture', '3', 'dbms']` |
| `CODE_SYNTAX`     | **0.65** | Symbols, imports, and shebang in code files | `import torch`, `class VulnerabilityScanner` |
| `CONTENT_KEYWORD` | **0.50** | High-frequency keywords in extracted text | Mention of `"ACID properties"`, `"foreign key"` |
| `MEDIA_METADATA`  | **0.50** | Artist, Album, EXIF camera tags | Artist: `"Hans Zimmer"`, Camera: `"Sony A7III"` |
| `DIRECTORY_CONTEXT`|**0.40** | Parent folder naming context | Parent: `/home/user/Downloads/CS101_Fall2026/` |
| `EXTENSION_HINT`  | **0.20** | Generic format type hint | `.pdf` $\rightarrow$ Document, `.zip` $\rightarrow$ Archive |

---

## 4. Domain Affinity Dictionaries

Signals map to standardized general-purpose domain affinities. A single token can contribute affinity to multiple domains with varying weights:

```python
DOMAIN_SIGNAL_AFFINITIES = {
    # Academic / College
    "lecture":     {"College": 0.85, "Work": 0.15},
    "assignment":  {"College": 0.90},
    "homework":    {"College": 0.90},
    "syllabus":    {"College": 0.95},
    "semester":    {"College": 0.90},
    "professor":   {"College": 0.85},
    "tutorial":    {"College": 0.60, "Projects": 0.40},

    # Software Engineering / Projects
    "repository":  {"Projects": 0.90, "Code": 0.80},
    "commit":      {"Projects": 0.85, "Code": 0.80},
    "makefile":    {"Projects": 0.90, "Code": 0.90},
    "dockerfile":  {"Projects": 0.85, "Code": 0.85},
    "backend":     {"Projects": 0.80, "Code": 0.70},
    "frontend":    {"Projects": 0.80, "Code": 0.70},
    "api":         {"Projects": 0.75, "Code": 0.75},

    # Cybersecurity / InfoSec
    "wireshark":   {"Cybersecurity": 0.95},
    "metasploit":  {"Cybersecurity": 0.95},
    "nmap":        {"Cybersecurity": 0.95},
    "burp":        {"Cybersecurity": 0.95},
    "exploit":     {"Cybersecurity": 0.90},
    "wordlist":    {"Cybersecurity": 0.90},
    "ctf":         {"Cybersecurity": 0.95},
    "cve":         {"Cybersecurity": 0.90},

    # Financial / Work / Legal
    "invoice":     {"Work": 0.90, "Personal": 0.50},
    "receipt":     {"Work": 0.80, "Personal": 0.70},
    "statement":   {"Work": 0.75, "Personal": 0.75},
    "contract":    {"Work": 0.85, "Personal": 0.60},
    "timesheet":   {"Work": 0.95},
    "quarterly":   {"Work": 0.90},

    # Media / Creative
    "wallpaper":   {"Images": 0.95},
    "screenshot":  {"Images": 0.80},
    "soundtrack":  {"Audio": 0.90},
    "podcast":     {"Audio": 0.90},
    "screencast":  {"Videos": 0.85},
}
```

---

## 5. Signal Vector Aggregation

For every file, the `SignalExtractor` aggregates all extracted signals into a unified `SignalSet`:

$$\text{DomainScore}(D) = \sum_{s \in \text{Signals}} \text{Weight}(s) \times \text{Affinity}(s, D)$$

The resulting normalized domain affinity scores are passed to the **Classifier** and **Relationship Engine**.
