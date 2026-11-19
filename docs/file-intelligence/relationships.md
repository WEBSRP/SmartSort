# SmartSort File Intelligence Engine: Relationship Discovery & Clustering

## Implementation status

Phase 10 is implemented in `src/core/file_intelligence/relationships.py` and
exported from the file-intelligence package. It consumes existing `FileContext`
objects and returns deterministic `FileCluster` objects without opening files,
accessing the network, importing Qt, or moving anything. Missing signals are
computed from a copied context using Phase 09. Classifier, planner, organizer,
and GUI integration remain later phases.

## Similarity evidence

`calculate_similarity(a, b)` returns `(score, shared_identity_tokens)` without
mutating either input. The score is clamped to one:

```text
0.65 × Jaccard(identity_a, identity_b)
+ 0.20 if validated nonempty origin hostnames match
+ 0.15 if positive finite creation timestamps differ by less than 900 seconds
+ 0.25 if compatible same-directory numbered series have different numbers
```

Identity comes from canonical Phase 09 signals. Extension, directory, origin,
camera and inherited cluster channels, zero-weight records, and generic role
words such as `report`, `code` and `document` do not establish identity. Legacy
unweighted token sets are supported. A recognized series removes only its own
number token, preserving course identifiers such as `CS101`.

Series markers include lecture, assignment, exam, lab, part, volume, episode,
and week. Topics must agree, or one topic may be missing when attaching sparse
files. Number gaps are allowed. Unknown timestamps (including zero), invalid
hostnames, and raw URL strings do not contribute evidence. Origin and time
alone cannot reach the 0.60 edge threshold.

An archive TOC match raises the score to at least 0.75. The engine compares a
safe member-relative path, or a unique member basename for a same-directory
sibling. Absolute, traversal, drive and control-containing TOC entries are
ignored; duplicate basenames suppress the basename fallback. This is filename
evidence, not proof that an external file was extracted from that archive.
No archive payload is opened here.

## Guarded connected components

Profiles are sorted by normalized logical path. Token and series postings
identify candidate pairs; an exact score upper bound prunes broad-word near
misses. Union-find retains a spanning forest of qualifying edges, then BFS
extracts components with at least two members. Singletons remain unclustered.
The engine stores only `n - 1` relationship witnesses per cluster rather than
a dense graph.

Core files have a nonnumeric identity anchor beyond a generic series marker.
Core components are built first. Weak files can form components using strict
series or explicit archive evidence. A weak component attaches only when all
qualifying core neighbors belong to one core component. Ambiguous weak files
therefore cannot bridge different courses or projects. The guarded graph is
intentionally more conservative than unrestricted connected components.

Connected components remain transitive: two endpoints may have no direct edge.
This is not hierarchical clustering or a guarantee that every pair is similar.
`calculate_similarity` reports pair evidence independently of batch ambiguity
guards, so a qualifying pair can remain separate in an ambiguous batch.

## Stable output and propagation

Cluster IDs hash sorted normalized logical member paths; names use canonical
keywords present in at least half the members (and at least two). Keywords are
limited to 32 and names to 64 characters. Topic names precede series markers,
for example `DBMS_Lectures`; a supported project prefix such as `SmartSort` is
preserved. IDs are stable across input permutations and change with membership.
They identify logical paths, not physical files or file contents.

`FileCluster.inferred_domain` aggregates local signal affinities, rolls up domain
roots, and requires a 60% winning share. Phase 13 integration excludes typed
directory, extension and inherited cluster channels from those votes, so the
selected folder's generic name cannot contaminate cluster consensus. Legacy
unweighted input behavior is unchanged. Otherwise it is `Others` with no inferred
hierarchy. Cluster confidence is the mean score of the retained spanning
witnesses. It is not a calibrated classification probability or an all-pairs
cohesion measure.

Each member receives `cluster_id`, its own independent `related_file_paths`
list, and the documented confidence contribution:

```text
boosted = baseline + 0.30 × (1 - baseline) × cluster_confidence
```

Content-sparse members also receive missing shared keywords as `CLUSTER_CONTEXT`
signals weighted by `0.30 × cluster_confidence`. Inherited signals never feed
back into graph identity or local domain affinities. Per-file domain,
subcategories, confidence enum, evidence list and destination are untouched;
Phase 11 will consume these relationship hints during classification.

The serialized `relationship_base_confidence` and
`relationship_confidence_boost` fields make repeated and JSON-reloaded runs
idempotent. Re-clustering clears stale links, inherited signals and previous
boosts for the supplied contexts. Independently added signal records survive
cleanup. A changed external confidence score becomes a new baseline. Contexts
outside the supplied batch are not updated. All profiles and graph outputs are
validated before committing context mutations.

## Bounds and performance

- At most 2,000 contexts, with distinct normalized logical paths of at most
  4,096 characters; duplicate paths are rejected before mutation.
- At most 256 canonical identity tokens per profile and 32,768 batch vocabulary
  entries; input signal sets allow 2,080 tokens/records and 64 affinity keys.
- At most 500 TOC entries of 1,024 characters are examined per profile.
- Normalization cache is local to one batch and capped at 4,096 entries.
  There is no persistent Phase 17 cache.

Candidate comparisons have worst-case quadratic cost. Related-path output can
also be quadratic for a large single cluster. Bounds limit work but do not
provide a hard execution deadline.

An isolated local benchmark on 2026-11-15 used precomputed signals and eleven
runs per 500-file batch. Values are first run / median of ten subsequent runs /
maximum subsequent run, in milliseconds:

| Batch | First | Median | Maximum |
| --- | ---: | ---: | ---: |
| Numbered DBMS lectures | 19.677 | 21.542 | 22.872 |
| Disjoint identities | 12.469 | 11.605 | 17.160 |
| Shared-word near misses | 14.303 | 14.345 | 16.012 |

These fixtures meet the roadmap's 25 ms target. This is not a universal latency
guarantee; signal extraction, denser candidate graphs, larger batches and host
load can increase runtime.

## Verification

`tests/test_file_intelligence/test_relationships.py` contains 66 cases covering
exact scores, course/project examples, archive matches, sparse ambiguity,
transitivity, exhaustive reference graphs, permutations, hash seeds, JSON
round-trips, repeat-safe propagation, validation bounds and no-I/O/headless
behavior. The full suite passed with 1,018 tests and one existing privileged-user
permission skip. Source compilation and whitespace checks also pass.
