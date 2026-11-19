# SmartSort File Intelligence Engine: Classification & Confidence

## Implementation status

Phase 11 implements `MultiSignalClassifier` in
`src/core/file_intelligence/classifier.py`, exported by the package.
`classify(context)` updates the per-file domain, subcategories, confidence level,
confidence score and evidence list; it returns `None`.
`evaluate_domain_scores(context)` returns strengths for all seven roots without
mutating the context. Neither method opens files, accesses the network, imports
Qt, moves files, or selects a destination. The optional `config` constructor
argument is reserved and is not read or initialized implicitly.

## Domain taxonomy

| Root | Example subcategories |
| --- | --- |
| College | DBMS/Lectures, OS/Assignments, Machine_Learning/Labs, CS101/Exams |
| Projects | SmartSort/Source, PortfolioApp/Design, SmartSort/Documentation, Releases |
| Cybersecurity | Tools, Reports, Captures, Wordlists, Exploits |
| Work | Invoices, Contracts, Receipts, Reports |
| Media | Images, Videos, Audio |
| Archives | No additional hierarchy |
| Others | No additional hierarchy |

Phase 09 affinities are reused. `Code` rolls up to `Projects`, `Personal` to
`Work`, and image/audio/video roots to `Media`. Alias votes use their maximum,
not their sum. A small classifier-local vocabulary adds documentation/design/
release, security capture/tool, and billing/legal terms. Code language metadata
supports every language emitted by Phase 07; words such as `Go` and `Rust` in
ordinary prose do not independently establish a code domain. The language field
preserves `TypeScript`/`JavaScript` identities across lexical splitting and SQL
across the database alias fold.

## Channel scoring

| Channel | Weight | Signal types |
| --- | ---: | --- |
| Title | 0.25 | DOCUMENT_TITLE |
| Origin | 0.20 | ORIGIN_DOMAIN |
| Content | 0.20 | DOCUMENT_HEADING, CONTENT_KEYWORD, CODE_SYNTAX, MEDIA_METADATA, EXIF_CAMERA |
| Filename | 0.15 | FILENAME_TOKEN |
| Cluster | 0.15 | CLUSTER_CONTEXT |
| Archive | 0.05 | ARCHIVE_CONTENT |

Typed weighted signals are authoritative. Missing signals and legacy unweighted
sets are re-extracted from a copied context; unverifiable aggregate affinity
priors are not used as independent evidence. This does not modify stored signals.
Zero-weight records are ignored. Repeated canonical tokens within a channel use
only the strongest record, with deterministic tie-breaking. Headings and body
text therefore share one corroboration channel, even though their enum types
are different.

For each retained record:

```text
reliability = min(1, signal.weight / Phase09_base_weight)
channel_mass[domain] += reliability × rolled_up_token_affinity[domain]
channel_strength = channel_mass / max(1, sum(channel_mass))
score[domain] = sum(weight[channel] × channel_strength[domain])
                / sum(weight[channel] for available semantic channels)
```

The cluster base weight is 0.30, matching Phase 10 propagation. Empty channels
are omitted from the denominator, rather than treated as negative observations.
The returned scores lie in `[0, 1]`; they need not sum to one and are not
calibrated probabilities. Unknown tokens do not add domain mass.

Directory and extension hints are weak fallback evidence. They never count as
corroborating semantic channels, never determine semantic subcategories, and are
excluded when any semantic channel contributes. When they are the only evidence,
their aggregate strength is capped at 0.20. Thus `random.zip` remains
`Others/UNKNOWN`; its extension is not mistaken for semantic archive certainty.

Origin records must match hostname/site features independently derived from the
context's validated origin URL/hostname. URL paths, credentials, query strings,
fragments and arbitrary `site_name` strings do not acquire origin votes. Cluster
records require an assigned cluster ID. These checks verify representation and
association, not the truth of external metadata.

Phase 13 batch integration additionally supplies a cluster's known inferred root
as a bounded `CLUSTER_CONTEXT` token with source `cluster.inferred_domain` and
weight `0.30 × cluster_confidence`. This supports sparse members without counting
the cluster as an independent observation or bypassing conflict/uncertainty caps.

## Confidence and ambiguity

Only channels with a unique preference for the winning domain corroborate it.
Cluster hints affect scores but do not count as independent observations of this
file. Losing channels cannot supply a winning-domain corroboration boost.

```text
3 or more corroborating channels: min(1, top_score × 1.15)
0 or 1 corroborating channels: min(0.60, top_score × 0.85)
2 corroborating channels: top_score
```

The adjusted score maps to the roadmap tiers:

- `CONFIRMED`: at least 0.85 and at least two corroborating channels.
- `PROBABLE`: at least 0.60.
- `UNCERTAIN`: at least 0.35.
- `UNKNOWN`: below 0.35, with domain fallback to `Others`.

If the top two raw domain strengths differ by less than 0.10, confidence is
capped at 0.59. Ties use deterministic alphabetical ordering but remain uncertain
or unknown. Tier comparisons use unrounded numbers; the stored float is not
rounded upward across a threshold. These are transparent heuristics, not
empirically calibrated correctness rates. Available channels can contain
correlated metadata even when they have different field origins.

## Hierarchy and evidence

Course labels recognize DBMS, OS, Machine Learning and bounded filename course
codes. Project names require a bounded ASCII role-delimited stem such as
`SmartSort_Source`; a URL, absolute path, or archive member cannot supply a
project name. Generic role prefixes are not treated as project identities.
Names are at most 64 characters and contain no path separators. The planner
will still need to enforce destination containment in Phase 12.

Subtype selection prefers explicit filename terms, then title terms, then
canonical signal tokens. Raw bounded lexical words preserve distinctions such
as CVE/Exploits that Phase 09 intentionally folds into `security`. Contradictory
subtypes have a fixed deterministic priority. Other subjects and arbitrary
project naming patterns may yield a subtype without a topic/project folder;
there is no open-ended course or entity recognizer in this phase.

Evidence records name the channel, safe canonical token, supported domain,
strength and known source field. All retained domain-contributing records are
explained, including counterevidence for losing domains. The evidence weight is
record reliability times domain affinity, not the final weighted channel share.
Repeated records are deduplicated, and ignored weak hints are not presented as
contributing evidence. Unknown source strings are replaced by known field names.
Descriptions do not copy full paths, URLs, source strings or metadata excerpts.

## Repeatability and bounds

Classification replaces stale outputs rather than accumulating evidence or
boosts. It recomputes from signals, disregards previous classification scores,
and clears Phase 10 confidence bookkeeping to prevent an old relationship boost
being mistaken for part of the new baseline. Cluster IDs, related paths, stored
signals, origin/metadata and proposed destinations are otherwise untouched.
Repeated, permuted and JSON-reloaded inputs produce the same outputs.

At most 2,080 weighted signals/tokens are accepted. Signal tokens are bounded to
64 characters and restricted to canonical alphanumeric/underscore forms. Source
field validation is bounded to 80 characters. Oversized weighted batches raise
`ValueError` before output mutations; individual unsafe tokens are ignored.
Fallback extraction retains Phase 09 budgets. Hierarchy lexical inspection uses
the bounded tokenizer, course/project patterns inspect at most 512 stem
characters, and the classifier stores no cache or background workers.
