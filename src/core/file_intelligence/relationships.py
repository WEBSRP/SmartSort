"""Deterministic, bounded relationship graphs. No file or network operations."""

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, replace
import hashlib
import math
import os
import re

from src.core.file_intelligence.context import (
    FileContext, FileCluster, FileRelationship, Signal, SignalSet, SignalType,
)
from src.core.file_intelligence.origin import origin_from_url
from src.core.file_intelligence.signals import DOMAIN_SIGNAL_AFFINITIES, LexicalTokenizer, SignalExtractor


_MARKERS = frozenset(("lecture", "assignment", "exam", "lab", "part", "volume", "episode", "week"))
_ROLES = frozenset("""report code source document presentation documentation release design
image video audio archive spreadsheet module project note readme bundle version v course college
work personal media code_project python javascript typescript""".split())
_IGNORED_CHANNELS = frozenset((SignalType.EXTENSION_HINT, SignalType.DIRECTORY_CONTEXT,
                             SignalType.ORIGIN_DOMAIN, SignalType.CLUSTER_CONTEXT, SignalType.EXIF_CAMERA))
_ROLLUP = {"Code": "Projects", "Images": "Media", "Audio": "Media", "Videos": "Media", "Personal": "Work"}
_DOMAINS = frozenset(("College", "Projects", "Cybersecurity", "Work", "Media", "Archives"))
_LABELS = {"database": "DBMS", "os": "OS", "lecture": "Lectures", "assignment": "Assignments",
           "exam": "Exams", "lab": "Labs", "api": "API"}
_CONTROL = re.compile(r"[\x00-\x1f]")
_TOKEN_PUNCTUATION = re.compile(r"[/\.\\:@?#]")


def _unit(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


@dataclass
class _Profile:
    context: FileContext
    path: str
    parent: str
    identity: frozenset
    base_signals: SignalSet
    base_score: float
    origin: str
    timestamp: object
    series: object
    members: frozenset
    unique_basenames: frozenset
    weak: bool
    content_sparse: bool


class _Forest:
    """Union-find skips redundant edges; retained edges are traversed by BFS."""

    def __init__(self, size):
        self.parents = list(range(size))
        self.members = [1 << i for i in range(size)]
        self.edges = []

    def root(self, index):
        while index != self.parents[index]:
            self.parents[index] = self.parents[self.parents[index]]
            index = self.parents[index]
        return index

    def join(self, a, b, evidence):
        left, right = self.root(a), self.root(b)
        if left == right:
            return
        if right < left:
            left, right = right, left
        self.parents[right] = left
        self.members[left] |= self.members[right]
        self.edges.append((a, b, evidence))


class RelationshipEngine:
    SIMILARITY_THRESHOLD = 0.60
    MAX_FILES = 2000
    MAX_TOKENS = 256
    MAX_VOCABULARY = 32768
    MAX_SHARED_KEYWORDS = 32

    def calculate_similarity(self, ctx_a, ctx_b):
        """Weighted identity overlap + provenance/time/series, in [0,1]."""
        a, b = self._profile(ctx_a), self._profile(ctx_b)
        score, shared, _ = self._similarity(a, b)
        return score, set(shared)

    def _profile(self, context, canonicalize=None):
        canonicalize = canonicalize or LexicalTokenizer.canonicalize
        if not isinstance(context, FileContext) or not isinstance(context.path, str) or not context.path or len(context.path) > 4096 or _CONTROL.search(context.path):
            raise ValueError("Relationships require FileContexts with bounded non-empty paths")
        if not _unit(context.confidence_score):
            raise ValueError("File confidence must be finite and in [0, 1]")
        path = os.path.normpath(context.path)
        signals = context.signals
        if not isinstance(signals, SignalSet):
            signals = SignalExtractor().extract_signals(replace(context))
        if (len(signals.tokens) > SignalExtractor.MAX_SIGNALS + self.MAX_SHARED_KEYWORDS or
                len(signals.weighted_signals) > SignalExtractor.MAX_SIGNALS + self.MAX_SHARED_KEYWORDS or
                len(signals.domain_affinities) > 64):
            raise ValueError("File signal set exceeds the bounded relationship input contract")
        weighted = [s for s in signals.weighted_signals if s.signal_type is not SignalType.CLUSTER_CONTEXT]
        inherited = {s.token for s in signals.weighted_signals if s.signal_type is SignalType.CLUSTER_CONTEXT} - {s.token for s in weighted}
        # Propagation adds only missing tokens; removing those records therefore
        # recovers the original tokens on repeated/serialized runs.
        base = SignalSet(set(signals.tokens) - inherited, weighted, dict(signals.domain_affinities))
        raw = [s.token for s in weighted if s.signal_type not in _IGNORED_CHANNELS and s.weight > 0] if weighted else sorted(base.tokens)
        tokens = set()
        for value in raw[:SignalExtractor.MAX_SIGNALS]:
            if isinstance(value, str) and 0 < len(value) <= 64 and not _TOKEN_PUNCTUATION.search(value):
                token = canonicalize(value)
                if token and token.replace("_", "").isalnum() and token not in _ROLES:
                    tokens.add(token)
                    if len(tokens) >= self.MAX_TOKENS:
                        break
        stem = context.stem if isinstance(context.stem, str) else ""
        words = [canonicalize(t) for t in LexicalTokenizer.tokenize(stem[:512])]
        series = None
        for i in range(len(words) - 1):
            if words[i] in _MARKERS and words[i+1].isascii() and words[i+1].isdigit() and len(words[i+1]) <= 9:
                number = words[i+1]
                topic = tuple(t for j, t in enumerate(words) if j not in (i, i+1) and t not in _ROLES)
                series = (words[i], topic, int(number))
                tokens.discard(number)
                break
        members = set()
        entries = getattr(context.metadata, "toc_entries", None)
        if isinstance(entries, (list, tuple)):
            for entry in entries[:500]:
                if not isinstance(entry, str) or not 0 < len(entry) <= 1024:
                    continue
                entry = entry.replace("\\", "/")
                if entry.startswith("/") or ".." in entry.split("/") or ":" in entry or any(ord(c) < 32 for c in entry):
                    continue
                if not entry.endswith("/"):
                    members.add(os.path.normpath(entry))
        counts = Counter(os.path.basename(item) for item in members)
        base_score = context.confidence_score
        prior = context.relationship_base_confidence
        boost = context.relationship_confidence_boost
        if _unit(prior) and _unit(boost) and abs(base_score - prior - boost) < 1e-12:
            base_score = prior
        origin = getattr(context.origin, "domain", "")
        if isinstance(origin, str) and origin and len(origin) <= 253 and not any(c in origin for c in "/@?#\\"):
            host = "[" + origin + "]" if origin.count(":") >= 2 and not origin.startswith("[") else origin
            safe = origin_from_url("https://" + host)
        else:
            safe = None
        if safe is None or not safe.url:
            url = getattr(context.origin, "url", None)
            if isinstance(url, str) and url:
                safe = origin_from_url(url)
        stamp = context.created_timestamp
        stamp = float(stamp) if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) and 0 < stamp < 10**12 else None
        content = any(s.signal_type in (SignalType.DOCUMENT_TITLE, SignalType.DOCUMENT_HEADING,
                      SignalType.CONTENT_KEYWORD, SignalType.CODE_SYNTAX) and s.weight > 0 and
                      s.token in tokens and s.token not in _MARKERS for s in weighted)
        return _Profile(context, path, os.path.dirname(path), frozenset(tokens), base, base_score,
                        safe.domain if safe and safe.url else "", stamp, series, frozenset(members),
                        frozenset(name for name, count in counts.items() if count == 1),
                        not bool(tokens - _MARKERS - {t for t in tokens if t.isdigit()}), not content)

    @staticmethod
    def _series_match(a, b, strict=False):
        if not a.series or not b.series or a.parent != b.parent:
            return False
        marker_a, topic_a, number_a = a.series
        marker_b, topic_b, number_b = b.series
        compatible = topic_a == topic_b or (not strict and (not topic_a or not topic_b))
        return marker_a == marker_b and number_a != number_b and compatible

    @staticmethod
    def _archive_match(a, b):
        for archive, member in ((a, b), (b, a)):
            if not archive.members:
                continue
            try:
                relative = os.path.relpath(member.path, archive.parent or ".")
            except ValueError:
                continue
            if relative in archive.members:
                return True
            if archive.parent == member.parent and os.path.basename(member.path) in archive.unique_basenames:
                return True
        return False

    def _similarity(self, a, b):
        shared = a.identity & b.identity
        union_size = len(a.identity) + len(b.identity) - len(shared)
        score = .65 * len(shared) / union_size if union_size else 0.0
        same_origin = bool(a.origin and a.origin == b.origin)
        if same_origin:
            score += .20
        if a.timestamp is not None and b.timestamp is not None and abs(a.timestamp - b.timestamp) < 900:
            score += .15
        series = self._series_match(a, b)
        if series:
            score += .25
        archive = self._archive_match(a, b) if a.members or b.members else False
        if archive:
            score = max(score, .75)
        kind = "ARCHIVE_EXTRACT" if archive else "SIBLING_SERIES" if series else "SHARED_ORIGIN" if same_origin else "TOKEN_SIMILARITY"
        return min(1.0, score), shared, kind

    def cluster_files(self, contexts):
        if contexts is None:
            return []
        if not isinstance(contexts, (list, tuple)) or len(contexts) > self.MAX_FILES:
            raise ValueError("Relationship batches must contain at most 2000 file contexts")
        normalized = {}
        def canonicalize(value):
            if value.isdigit():
                return value
            if value in normalized:
                return normalized[value]
            result = LexicalTokenizer.canonicalize(value)
            if len(normalized) < 4096:
                normalized[value] = result
            return result
        profiles = sorted((self._profile(ctx, canonicalize) for ctx in contexts), key=lambda p: p.path)
        if len({p.path for p in profiles}) != len(profiles):
            raise ValueError("Duplicate logical file paths in relationship batch")
        postings, names, series_groups = {}, defaultdict(int), defaultdict(int)
        for i, profile in enumerate(profiles):
            for token in sorted(profile.identity):
                postings[token] = postings.get(token, 0) | (1 << i)
            names[os.path.basename(profile.path)] |= 1 << i
            if profile.series:
                series_groups[(profile.parent, profile.series[0])] |= 1 << i
        if len(postings) > self.MAX_VOCABULARY:
            raise ValueError("Relationship vocabulary exceeds its bounded batch budget")
        candidates = [0] * len(profiles)
        for i, profile in enumerate(profiles):
            once, twice = 0, 0
            for token in profile.identity:
                twice |= once & postings[token]
                once |= postings[token]
            # With no series/archive bonus, one shared token cannot reach the
            # cutoff if .65/len(identity)+.35 is below it. This exact upper-bound
            # prune avoids comparing every broad-word near miss.
            if profile.identity and not profile.series and .65/len(profile.identity)+.35 < self.SIMILARITY_THRESHOLD:
                candidates[i] |= twice
            else:
                candidates[i] |= once
            if profile.series:
                candidates[i] |= series_groups[(profile.parent, profile.series[0])]
            for member in profile.members:
                # Archive candidates need not share any lexical identity tokens.
                mask = names.get(os.path.basename(member), 0)
                candidates[i] |= mask
                while mask:
                    bit = mask & -mask
                    candidates[bit.bit_length() - 1] |= 1 << i
                    mask ^= bit
        forest = _Forest(len(profiles))
        core = sum(1 << i for i, p in enumerate(profiles) if not p.weak)
        weak = ((1 << len(profiles)) - 1) ^ core
        # Keep only a spanning forest of qualifying edges. Skipping edges whose
        # endpoints are already connected preserves connected components exactly.
        for allowed in (core, weak):
            for i, a in enumerate(profiles):
                if not (allowed & (1 << i)):
                    continue
                mask = candidates[i] & allowed & ~((1 << (i+1)) - 1)
                while mask:
                    mask &= ~forest.members[forest.root(i)]
                    if not mask:
                        break
                    bit = mask & -mask
                    mask ^= bit
                    j = bit.bit_length() - 1
                    if a.weak and not (self._series_match(a, profiles[j], strict=True) or self._archive_match(a, profiles[j])):
                        continue
                    evidence = self._similarity(a, profiles[j])
                    if evidence[0] >= self.SIMILARITY_THRESHOLD:
                        forest.join(i, j, evidence)
        core_labels = {i: forest.root(i) for i, p in enumerate(profiles) if not p.weak}
        weak_groups = defaultdict(list)
        for i, p in enumerate(profiles):
            if p.weak:
                weak_groups[forest.root(i)].append(i)
        # Sparse components may attach to one core component, never bridge two.
        for group in weak_groups.values():
            choices = {}
            for i in group:
                mask = candidates[i] & core
                while mask:
                    bit = mask & -mask
                    mask ^= bit
                    j = bit.bit_length() - 1
                    evidence = self._similarity(profiles[i], profiles[j])
                    if evidence[0] >= self.SIMILARITY_THRESHOLD:
                        label = core_labels[j]
                        candidate = (evidence[0], -i, -j, evidence)
                        if label not in choices or candidate[:3] > choices[label][:3]:
                            choices[label] = candidate
                if len(choices) > 1:
                    break
            if len(choices) == 1:
                _, ni, nj, evidence = next(iter(choices.values()))
                forest.join(-ni, -nj, evidence)
        adjacency = [[] for _ in profiles]
        for a, b, evidence in forest.edges:
            adjacency[a].append((b, evidence))
            adjacency[b].append((a, evidence))
        visited, clusters = set(), []
        for start in range(len(profiles)):
            if start in visited:
                continue
            queue, component, witnesses = deque([start]), [], []
            visited.add(start)
            while queue:
                i = queue.popleft()
                component.append(i)
                for j, evidence in sorted(adjacency[i], key=lambda item: item[0]):
                    if j not in visited:
                        visited.add(j)
                        queue.append(j)
                        score, shared, kind = evidence
                        a, b = sorted((i, j))
                        witnesses.append(FileRelationship(profiles[a].context.path, profiles[b].context.path,
                                                          kind, score, set(shared)))
            if len(component) > 1:
                clusters.append(self._build_cluster([profiles[i] for i in sorted(component)], witnesses))
        # Commit only after validation/graph construction completed successfully.
        for p in profiles:
            p.context.cluster_id = None
            p.context.related_file_paths = []
            p.context.signals = p.base_signals
            p.context.confidence_score = p.base_score
            p.context.relationship_base_confidence = None
            p.context.relationship_confidence_boost = 0.0
        by_path = {p.context.path: p for p in profiles}
        for cluster in clusters:
            for position, path in enumerate(cluster.file_paths):
                profile = by_path[path]
                ctx = profile.context
                ctx.cluster_id = cluster.cluster_id
                ctx.related_file_paths = cluster.file_paths.copy()
                del ctx.related_file_paths[position]
                ctx.relationship_base_confidence = profile.base_score
                ctx.relationship_confidence_boost = .30 * (1.0 - profile.base_score) * cluster.cluster_confidence
                ctx.confidence_score = profile.base_score + ctx.relationship_confidence_boost
                if profile.content_sparse:
                    for token in sorted(cluster.shared_keywords - ctx.signals.tokens):
                        ctx.signals.tokens.add(token)
                        ctx.signals.weighted_signals.append(Signal(token, SignalType.CLUSTER_CONTEXT,
                            .30 * cluster.cluster_confidence, "cluster.shared_keywords"))
        return clusters

    def _build_cluster(self, profiles, witnesses):
        counts = Counter(token for p in profiles for token in p.identity if not token.isdigit())
        support = max(2, (len(profiles)+1)//2)
        keywords = sorted((t for t, count in counts.items() if count >= support),
                          key=lambda t: (t in _MARKERS, -counts[t], t))[:self.MAX_SHARED_KEYWORDS]
        name = "_".join(_LABELS.get(t, t.capitalize()) for t in keywords[:3]) or "Related_Files"
        prefixes = [p.context.stem.split("_", 1)[0] for p in profiles if isinstance(p.context.stem, str)]
        if prefixes and len(prefixes) == len(profiles) and len({p.casefold() for p in prefixes}) == 1:
            prefix_tokens = {LexicalTokenizer.canonicalize(t) for t in LexicalTokenizer.tokenize(prefixes[0])}
            if prefix_tokens and prefix_tokens <= set(keywords) and prefix_tokens - _MARKERS and prefixes[0].isalnum():
                name = prefixes[0][:64]
        votes = defaultdict(float)
        for p in profiles:
            affinities = defaultdict(float)
            if p.base_signals.weighted_signals:
                for signal in p.base_signals.weighted_signals:
                    if signal.signal_type in (SignalType.DIRECTORY_CONTEXT, SignalType.EXTENSION_HINT,
                                              SignalType.CLUSTER_CONTEXT):
                        continue
                    for domain, affinity in DOMAIN_SIGNAL_AFFINITIES.get(signal.token, {}).items():
                        affinities[domain] += signal.weight * affinity
            else:
                affinities.update(p.base_signals.domain_affinities)
                if not affinities:
                    for token in sorted(p.base_signals.tokens):
                        for domain, affinity in DOMAIN_SIGNAL_AFFINITIES.get(token, {}).items():
                            affinities[domain] += affinity
            total = math.fsum(affinities.values())
            for domain, affinity in sorted(affinities.items()):
                root = _ROLLUP.get(domain, domain)
                if root in _DOMAINS and _unit(affinity / total if total else 0):
                    votes[root] += affinity / total if total else 0
        ordered = sorted(votes, key=lambda d: (-votes[d], d))
        total = sum(votes.values())
        domain = ordered[0] if ordered and total and votes[ordered[0]] / total >= .60 else "Others"
        paths = [p.context.path for p in profiles]
        digest = hashlib.sha256("\x00".join(p.path for p in profiles).encode("utf-8", errors="surrogatepass")).hexdigest()[:20]
        confidence = math.fsum(edge.similarity_score for edge in witnesses) / len(witnesses)
        return FileCluster("cluster-" + digest, name[:64], paths, set(keywords), domain,
                           [domain, name[:64]] if domain != "Others" else [], confidence,
                           sorted(witnesses, key=lambda edge: (edge.source_path, edge.target_path)))
