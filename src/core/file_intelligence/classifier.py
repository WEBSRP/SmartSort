"""Bounded, explainable domain heuristics. Scores are not probabilities."""

from collections import defaultdict
from dataclasses import replace
import math
import re

from src.core.file_intelligence.context import (
    ConfidenceLevel, EvidenceItem, FileContext, Signal, SignalSet, SignalType,
)
from src.core.file_intelligence.origin import origin_from_url
from src.core.file_intelligence.purpose import purpose_hint
from src.core.file_intelligence.signals import (
    BASE_WEIGHTS, DOMAIN_SIGNAL_AFFINITIES, LexicalTokenizer, SignalExtractor,
)


_CHANNELS = {
    SignalType.DOCUMENT_TITLE: "title", SignalType.ORIGIN_DOMAIN: "origin",
    SignalType.FILENAME_TOKEN: "filename", SignalType.CLUSTER_CONTEXT: "cluster",
    SignalType.ARCHIVE_CONTENT: "archive", SignalType.DOCUMENT_HEADING: "content",
    SignalType.CONTENT_KEYWORD: "content", SignalType.CODE_SYNTAX: "content",
    SignalType.MEDIA_METADATA: "content", SignalType.EXIF_CAMERA: "content",
}
_WEIGHTS = {"title": .25, "origin": .20, "content": .20,
            "filename": .15, "cluster": .15, "archive": .05}
_ROLLUP = {"Code": "Projects", "Personal": "Work", "Images": "Media",
           "Videos": "Media", "Audio": "Media"}
_EXTRA = {
    **{t: {"Projects": .85} for t in ("documentation", "readme", "design", "release")},
    **{t: {"Cybersecurity": .90} for t in ("pcap", "capture", "pentest", "nessus", "nikto")},
    **{t: {"Work": .90} for t in ("nda", "agreement", "billing")},
    "machine_learning": {"College": .85, "Projects": .60},
}
# Language evidence is specific to code metadata; ordinary prose about "go"
# or "C" must not acquire a Projects vote.
_CODE_LANGUAGES = frozenset(("c", "java", "go", "rust", "shell", "php", "typescript", "python", "javascript", "database"))
_SUBTYPES = {
    "College": (("exam", "Exams"), ("assignment", "Assignments"), ("lab", "Labs"), ("lecture", "Lectures")),
    "Projects": (("release", "Releases"), ("design", "Design"), ("documentation", "Documentation"),
                 ("readme", "Documentation"), ("report", "Documentation"),
                 ("source", "Source"), ("code", "Source"), ("code_project", "Source"),
                 ("python", "Source"), ("javascript", "Source"), ("repository", "Source")),
    "Cybersecurity": (("wordlist", "Wordlists"), ("exploit", "Exploits"), ("cve", "Exploits"),
                      ("pcap", "Captures"), ("capture", "Captures"), ("nmap", "Reports"),
                      ("scan", "Reports"), ("report", "Reports"), ("metasploit", "Tools"), ("burp", "Tools")),
    "Work": (("invoice", "Invoices"), ("billing", "Invoices"), ("contract", "Contracts"),
             ("agreement", "Contracts"), ("nda", "Contracts"), ("receipt", "Receipts"),
             ("quarterly", "Reports"), ("report", "Reports")),
    "Media": (("video", "Videos"), ("screencast", "Videos"), ("audio", "Audio"),
              ("podcast", "Audio"), ("soundtrack", "Audio"), ("image", "Images"),
              ("wallpaper", "Images"), ("screenshot", "Images"), ("canon", "Images"),
              ("nikon", "Images"), ("sony", "Images")),
}
_SOURCES = {
    SignalType.DOCUMENT_TITLE: "metadata.title", SignalType.ORIGIN_DOMAIN: "origin.domain",
    SignalType.FILENAME_TOKEN: "stem", SignalType.CLUSTER_CONTEXT: "cluster.shared_keywords",
    SignalType.ARCHIVE_CONTENT: "metadata.toc_entries", SignalType.DOCUMENT_HEADING: "metadata.headings",
    SignalType.CONTENT_KEYWORD: "metadata.text_preview", SignalType.CODE_SYNTAX: "metadata.code_symbols",
    SignalType.MEDIA_METADATA: "metadata.subject", SignalType.EXIF_CAMERA: "metadata.exif_tags",
    SignalType.DIRECTORY_CONTEXT: "parent_directory", SignalType.EXTENSION_HINT: "extension",
}
_SAFE_SOURCES = frozenset(_SOURCES.values()) | {
    "metadata.keywords", "metadata.author", "metadata.subject", "metadata.code_language",
    "metadata.exif_tags.Make", "metadata.exif_tags.Model", "metadata.exif_tags.Software",
    "metadata.exif_tags.LensModel", "origin.site_name",
    "cluster.inferred_domain",
}


def _affinities(token):
    result = {}
    for domain, value in _EXTRA.get(token, DOMAIN_SIGNAL_AFFINITIES.get(token, {})).items():
        root = _ROLLUP.get(domain, domain)
        # Code/Projects and Personal/Work are aliases, not independent votes.
        result[root] = max(result.get(root, 0.0), value)
    return result


_AFFINITIES = {token: _affinities(token) for token in DOMAIN_SIGNAL_AFFINITIES.keys() | _EXTRA.keys()}


class MultiSignalClassifier:
    """Classifies enriched contexts only; never selects or executes destinations."""

    DOMAINS = ("College", "Projects", "Cybersecurity", "Work", "Media", "Archives", "Others")
    MAX_SIGNALS = SignalExtractor.MAX_SIGNALS + 32

    def __init__(self, config=None):
        # Reserved API argument. No implicit ConfigManager construction or I/O.
        self.config = config

    def _analyze(self, context):
        if not isinstance(context, FileContext):
            raise ValueError("Classification requires a FileContext")
        signals = context.signals
        if not isinstance(signals, SignalSet) or not signals.weighted_signals:
            # Legacy unweighted affinities have no verifiable channel provenance.
            signals = SignalExtractor().extract_signals(replace(context))
        if len(signals.weighted_signals) > self.MAX_SIGNALS or len(signals.tokens) > self.MAX_SIGNALS:
            raise ValueError("Classification signal budget exceeded")
        records = {}
        origin_tokens = None
        for signal in signals.weighted_signals:
            if not isinstance(signal, Signal) or not signal.weight:
                continue
            kind = signal.signal_type
            if kind not in _SOURCES:
                continue
            if kind is SignalType.ORIGIN_DOMAIN:
                if origin_tokens is None:
                    origin = context.origin
                    domain = getattr(origin, "domain", "")
                    safe = None
                    if isinstance(domain, str) and domain and len(domain) <= 253 and not any(c in domain for c in "/@?#\\"):
                        host = "[" + domain + "]" if domain.count(":") >= 2 else domain
                        safe = origin_from_url("https://" + host)
                    if safe is None or not safe.url:
                        safe = origin_from_url(getattr(origin, "url", None))
                    origin_tokens = {safe.domain, safe.site_name} if safe and safe.url else set()
                if signal.token not in origin_tokens:
                    continue
            if not isinstance(signal.token, str) or len(signal.token) > 64:
                continue
            token = signal.token if signal.token in _AFFINITIES else LexicalTokenizer.canonicalize(signal.token)
            if kind is SignalType.CODE_SYNTAX and signal.source == "metadata.code_language":
                language = getattr(context.metadata, "code_language", None)
                if isinstance(language, str) and len(language) <= 32:
                    language = {"c++": "c", "sql": "database"}.get(language.casefold(), language.casefold())
                    if language in _CODE_LANGUAGES:
                        token = language
            if not token or not token.replace("_", "").isalnum():
                continue
            if kind is SignalType.CLUSTER_CONTEXT and not context.cluster_id:
                continue
            channel = _CHANNELS.get(kind, "weak")
            # One token per channel: headings and body repetitions aren't votes.
            key = (channel, token)
            previous = records.get(key)
            reliability = min(1.0, signal.weight / BASE_WEIGHTS.get(kind, .30))
            source = signal.source if len(signal.source) <= 80 and signal.source in _SAFE_SOURCES else _SOURCES[kind]
            item = (reliability, kind.value, source, kind)
            if previous is None or item[:3] > previous[:3]:
                records[key] = item
        channels = defaultdict(lambda: defaultdict(float))
        evidence = []
        tokens = set()
        for (channel, token), (reliability, _, source, kind) in sorted(records.items()):
            tokens.add(token)
            affinities = (_AFFINITIES.get(token, {}) if kind is not SignalType.CODE_SYNTAX or token not in _CODE_LANGUAGES
                          else {"Projects": .80})
            if not affinities:
                continue
            factor = min(.20, reliability * .20) if channel == "weak" else reliability
            for domain, affinity in affinities.items():
                channels[channel][domain] += factor * affinity
            evidence.append((channel, token, kind, source, factor, affinities))
        active = [c for c in _WEIGHTS if channels[c]]
        scores = dict.fromkeys(self.DOMAINS, 0.0)
        contributions = {}
        weight_total = math.fsum(_WEIGHTS[c] for c in active)
        for channel in active:
            divisor = max(1.0, math.fsum(channels[channel].values()))
            for domain, value in channels[channel].items():
                scores[domain] += _WEIGHTS[channel] * value / divisor / weight_total
            contributions[channel] = {d: v / divisor for d, v in channels[channel].items()}
        if not active and channels["weak"]:
            # Weak hints remain <= .20 even if there are many of them.
            divisor = max(1.0, math.fsum(channels["weak"].values()) / .20)
            scores.update({d: v / divisor for d, v in channels["weak"].items()})
        scores = {domain: min(1.0, max(0.0, score)) for domain, score in scores.items()}
        if active:
            evidence = [item for item in evidence if item[0] != "weak"]
            tokens = {token for channel, token in records if channel != "weak"}
            if any(item[2] is SignalType.CODE_SYNTAX and item[1] in _CODE_LANGUAGES for item in evidence):
                tokens.add("code_project")
        return scores, contributions, evidence, tokens

    def evaluate_domain_scores(self, context):
        """Return available-channel weighted strengths in [0,1], without mutation."""
        return self._analyze(context)[0]

    @staticmethod
    def _confidence(score, corroboration):
        if corroboration >= 3:
            score = min(1.0, score * 1.15)
        elif corroboration <= 1:
            score = min(.60, score * .85)
        if score >= .85 and corroboration >= 2:
            level = ConfidenceLevel.CONFIRMED
        elif score >= .60:
            level = ConfidenceLevel.PROBABLE
        elif score >= .35:
            level = ConfidenceLevel.UNCERTAIN
        else:
            level = ConfidenceLevel.UNKNOWN
        return level, score

    def classify(self, context):
        scores, contributions, records, tokens = self._analyze(context)
        ranked = sorted(scores, key=lambda d: (-scores[d], d))
        winner, runner_up = ranked[:2]
        # Only channels favoring the winning domain corroborate it; inherited
        # cluster hints aren't independent observations of this file.
        count = sum(c != "cluster" and v.get(winner, 0) > 0 and
                    v.get(winner, 0) == max(v.values()) and
                    list(v.values()).count(v[winner]) == 1
                    for c, v in contributions.items())
        level, score = self._confidence(scores[winner], count)
        if scores[winner] - scores[runner_up] < .10 and scores[runner_up] > 0:
            score = min(score, .59)
            level = ConfidenceLevel.UNCERTAIN if score >= .35 else ConfidenceLevel.UNKNOWN
        domain = "Others" if level is ConfidenceLevel.UNKNOWN else winner
        evidence = []
        for channel, token, kind, source, factor, affinities in records:
            # Preserve counterevidence too; explanations explicitly name each domain.
            for target, affinity in sorted(affinities.items()):
                evidence.append(EvidenceItem(kind, f"{channel.title()} token '{token}' supports {target}",
                                             min(1.0, factor * affinity), source))
        categories = self._subcategories(context, domain, tokens)
        hint = purpose_hint(context)
        if hint is not None and (domain in ("Media", "Others") or "Coding_Challenges" in hint[1]):
            purpose_domain, purpose_parts, purpose_score, purpose_evidence = hint
            # Preserve existing corroborated strength only when it agrees on
            # the domain; explicit purpose hints are otherwise merely probable.
            if purpose_domain != domain or score < purpose_score:
                score, level = purpose_score, ConfidenceLevel.PROBABLE
            domain, categories = purpose_domain, purpose_parts
            evidence.extend(purpose_evidence)
        context.classification_domain = domain
        context.subcategories = categories
        context.confidence = level
        context.confidence_score = score
        context.evidence_list = evidence
        # Classification recomputes from evidence; a previous relationship boost
        # must not be mistaken for part of this new score on the next cluster run.
        context.relationship_base_confidence = None
        context.relationship_confidence_boost = 0.0

    @staticmethod
    def _subcategories(context, domain, tokens):
        if domain not in _SUBTYPES:
            return []
        result = []
        if domain == "College":
            if "database" in tokens:
                result.append("DBMS")
            elif "os" in tokens:
                result.append("OS")
            elif {"machine", "learning"} <= tokens or "machine_learning" in tokens:
                result.append("Machine_Learning")
            else:
                matches = re.findall(r"(?<![A-Za-z0-9])([A-Za-z]{2,6}[0-9]{2,4})(?![A-Za-z0-9])",
                                     context.stem[:512] if isinstance(context.stem, str) else "")
                if matches:
                    result.append(sorted(matches, key=str.casefold)[0].upper())
        elif domain == "Projects":
            stem = context.stem if isinstance(context.stem, str) else ""
            # Keep an explicit role-delimited project name, never invent one
            # from a URL, full path, title, or archive member path.
            match = re.match(r"^([A-Za-z][A-Za-z0-9_-]{0,62}?)[ _-]+(?:source|code|report|documentation|readme|design|release|presentation)(?:[ _-]|$)", stem[:512], re.I)
            if match and match.group(1).casefold() not in (
                    "project", "my", "the", "source", "code", "report", "documentation", "release"):
                result.append(match.group(1).strip("_-")[:64])
        # Original subtype words can be folded by Phase 09 (CVE -> security).
        # Use bounded, safe stem words only for subtype disambiguation.
        subtype = None
        title = getattr(context.metadata, "title", None)
        for text in (context.stem, title, None):
            words = set(LexicalTokenizer.tokenize(text)) if text is not None else tokens
            words |= {LexicalTokenizer.canonicalize(word) for word in words}
            subtype = next((label for token, label in _SUBTYPES.get(domain, ()) if token in words), None)
            if subtype:
                break
        if subtype:
            result.append(subtype)
        return result
