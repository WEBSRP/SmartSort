"""Bounded deterministic lexical features; no I/O, models, or classification."""

import os
import re
import unicodedata

from src.core.file_intelligence.context import FileContext, Signal, SignalSet, SignalType
from src.core.file_intelligence.origin import origin_from_url


_STOP_WORDS = frozenset("""
a an the and or but in on at to for of with by from is it as be was were are
been being have has had do does did will would shall should may might must can
could not no nor so if then than that this these those i me my we our you your
he him his she her they them their its what which who whom how when where why
all each every both few more most other some such only own same just also very
about up out into over after before between under again further here there once
during while too any above below through s t re ve ll d m o now
final copy download downloads untitled new file unknown temp tmp backup draft
pdf doc docx ppt pptx xls xlsx odt odp ods txt md zip tar gz bz2 xz jpg jpeg png
gif webp bmp tiff svg mp3 mp4 wav flac ogg mkv mov webm
""".split())

# All aliases map directly to their final form, so canonicalization is idempotent.
_CANONICAL = {
    **dict.fromkeys(("asgn", "asgns", "asg", "assignment", "assignments", "hw", "homework"), "assignment"),
    **dict.fromkeys(("lecture", "lectures", "lec", "slide", "slides", "ch", "chapter", "chapters"), "lecture"),
    **dict.fromkeys(("exam", "exams", "midterm", "midterms", "quiz", "quizzes", "test", "tests"), "exam"),
    **dict.fromkeys(("db", "dbs", "dbms", "database", "databases", "sql"), "database"),
    **dict.fromkeys(("sec", "vuln", "vulnerability", "vulnerabilities", "exploit", "exploits", "cve", "security"), "security"),
    "operating_system": "os", "operating_systems": "os", "systems": "system",
    "invoices": "invoice", "receipts": "receipt", "contracts": "contract",
    "repositories": "repository", "repos": "repository", "repo": "repository",
    "commits": "commit", "wordlists": "wordlist", "tutorials": "tutorial",
    "projects": "project", "images": "image", "videos": "video",
    "archives": "archive", "documents": "document", "notes": "note",
    "labs": "lab", "courses": "course",
}
# Fixed-width boundaries avoid retrying a greedy acronym prefix at every
# character of an all-uppercase input (quadratic regex backtracking).
_ACRONYM = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_CAMEL = re.compile(r"(?<=[a-z\d])(?=[A-Z])")
_PARTS = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)
_NUMBERED_ALIAS = re.compile(r"([a-z]+)\d+\Z")
_PHRASES = {("operating", "system"): "os", ("operating", "systems"): "os",
            ("code", "project"): "code_project", ("academic", "paper"): "academic_paper"}


class LexicalTokenizer:
    MAX_TEXT_CHARS = 4096
    MAX_TOKENS = 512
    MAX_TOKEN_CHARS = 64

    @staticmethod
    def tokenize(text):
        """Split lexical tokens, preserving numbers/leading zeroes and order.

        Canonicalization is separate: DBMSLecture03 yields dbms, lecture, 03.
        Only an explicit dictionary folds terms; there is no blanket stemming.
        """
        if not isinstance(text, str) or not text:
            return []
        text = unicodedata.normalize("NFC", text[:LexicalTokenizer.MAX_TEXT_CHARS])
        text = _CAMEL.sub(" ", _ACRONYM.sub(" ", text)).casefold()
        result = []
        for match in _PARTS.finditer(text):
            token = match.group()
            if len(token) <= LexicalTokenizer.MAX_TOKEN_CHARS and token not in _STOP_WORDS:
                result.append(token)
                if len(result) >= LexicalTokenizer.MAX_TOKENS:
                    break
        return result

    @staticmethod
    def canonicalize(token):
        """Normalize one term; numbered known aliases such as asgn1 are folded."""
        if not isinstance(token, str) or not token or len(token) > 128:
            return ""
        token = unicodedata.normalize("NFC", token).casefold().strip()
        token = re.sub(r"[\s-]+", "_", token)
        match = _NUMBERED_ALIAS.fullmatch(token)
        if match and match.group(1) in _CANONICAL:
            token = match.group(1)
        return _CANONICAL.get(token, token)


BASE_WEIGHTS = {
    SignalType.DOCUMENT_TITLE: 0.90, SignalType.ORIGIN_DOMAIN: 0.85,
    SignalType.DOCUMENT_HEADING: 0.75, SignalType.ARCHIVE_CONTENT: 0.70,
    SignalType.FILENAME_TOKEN: 0.65, SignalType.CODE_SYNTAX: 0.65,
    SignalType.CONTENT_KEYWORD: 0.50, SignalType.MEDIA_METADATA: 0.50,
    SignalType.EXIF_CAMERA: 0.50, SignalType.DIRECTORY_CONTEXT: 0.40,
    SignalType.EXTENSION_HINT: 0.20,
}

# These are evidence affinities, not predicted categories or confidence scores.
DOMAIN_SIGNAL_AFFINITIES = {
    "college": {"College": .90}, "course": {"College": .85},
    "cs": {"College": .80}, "lab": {"College": .80},
    "work": {"Work": .80}, "finance": {"Work": .90}, "legal": {"Work": .90},
    "personal": {"Personal": .80}, "media": {"Media": .80},
    "source": {"Projects": .75, "Code": .80}, "code": {"Projects": .80, "Code": .90},
    "lecture": {"College": .85, "Work": .15}, "assignment": {"College": .90},
    "syllabus": {"College": .95}, "semester": {"College": .90},
    "professor": {"College": .85}, "tutorial": {"College": .60, "Projects": .40},
    "exam": {"College": .90}, "database": {"College": .80, "Projects": .60},
    "os": {"College": .80, "Projects": .40}, "note": {"College": .60},
    "repository": {"Projects": .90, "Code": .80}, "commit": {"Projects": .85, "Code": .80},
    "makefile": {"Projects": .90, "Code": .90}, "dockerfile": {"Projects": .85, "Code": .85},
    "backend": {"Projects": .80, "Code": .70}, "frontend": {"Projects": .80, "Code": .70},
    "api": {"Projects": .75, "Code": .75}, "code_project": {"Projects": .90, "Code": .90},
    "project": {"Projects": .75}, "python": {"Projects": .70, "Code": .80},
    "javascript": {"Projects": .70, "Code": .80}, "typescript": {"Projects": .70, "Code": .80},
    "wireshark": {"Cybersecurity": .95}, "metasploit": {"Cybersecurity": .95},
    "nmap": {"Cybersecurity": .95}, "burp": {"Cybersecurity": .95},
    "security": {"Cybersecurity": .90}, "wordlist": {"Cybersecurity": .90},
    "ctf": {"Cybersecurity": .95}, "invoice": {"Work": .90, "Personal": .50},
    "receipt": {"Work": .80, "Personal": .70}, "statement": {"Work": .75, "Personal": .75},
    "contract": {"Work": .85, "Personal": .60}, "timesheet": {"Work": .95},
    "quarterly": {"Work": .90}, "wallpaper": {"Images": .95, "Media": .75},
    "screenshot": {"Images": .80, "Media": .60}, "image": {"Images": .80, "Media": .70},
    "soundtrack": {"Audio": .90, "Media": .75}, "podcast": {"Audio": .90, "Media": .75},
    "screencast": {"Videos": .85, "Media": .75}, "video": {"Videos": .80, "Media": .70},
    "audio": {"Audio": .80, "Media": .70}, "archive": {"Archives": .70},
    "github": {"Projects": .95, "Code": .90}, "gitlab": {"Projects": .95, "Code": .90},
    "bitbucket": {"Projects": .95, "Code": .90}, "lms": {"College": .95},
    "academic_paper": {"College": .95}, "kaggle": {"Projects": .85, "College": .60},
    "blender": {"Images": .85, "Media": .80}, "sony": {"Images": .75, "Media": .70},
    "canon": {"Images": .75, "Media": .70}, "nikon": {"Images": .75, "Media": .70},
}

_EXTENSIONS = {}
for _hint, _extensions in {
    "document": ".pdf .doc .docx .odt .rtf .txt .md .rst",
    "presentation": ".ppt .pptx .odp", "spreadsheet": ".xls .xlsx .ods .csv .tsv",
    "image": ".png .jpg .jpeg .gif .webp .bmp .tif .tiff .svg",
    "audio": ".mp3 .wav .flac .ogg .m4a", "video": ".mp4 .mkv .avi .mov .webm .wmv",
    "archive": ".zip .tar .gz .bz2 .xz .tgz .7z .rar .tar.gz .tar.bz2 .tar.xz",
    "code_project": ".py .c .cpp .h .hpp .java .js .ts .go .rs .sh .bash .sql .php",
}.items():
    _EXTENSIONS.update(dict.fromkeys(_extensions.split(), _hint))


class SignalExtractor:
    MAX_INPUT_CHARS = 65536
    MAX_SIGNALS = 2048
    MAX_ITEMS = 500

    def extract_signals(self, context):
        result = SignalSet()
        if not isinstance(context, FileContext):
            return result
        remaining = self.MAX_INPUT_CHARS
        seen = set()

        def add(token, kind, source):
            key = (kind, token)
            if token and key not in seen and len(result.weighted_signals) < self.MAX_SIGNALS:
                seen.add(key)
                result.tokens.add(token)
                result.weighted_signals.append(Signal(token, kind, BASE_WEIGHTS[kind], source))

        def field(text, kind, source, limit=1024):
            nonlocal remaining
            if not isinstance(text, str) or not text or remaining <= 0:
                return
            sample = text[:min(limit, remaining)]
            remaining -= len(sample)
            parts = LexicalTokenizer.tokenize(sample)
            index = 0
            while index < len(parts):
                phrase = _PHRASES.get(tuple(parts[index:index+2]))
                # tokenize() already normalized/split these terms; avoid doing
                # Unicode/regex normalization again for every archive member.
                add(phrase or _CANONICAL.get(parts[index], parts[index]), kind, source)
                index += 2 if phrase else 1

        def fields(values, kind, source, count=64, limit=256):
            if isinstance(values, (list, tuple)):
                for value in values[:min(count, self.MAX_ITEMS)]:
                    field(value, kind, source, limit)

        metadata = context.metadata
        field(getattr(metadata, "title", None), SignalType.DOCUMENT_TITLE, "metadata.title", 256)

        # Only validated hostname/site features enter this channel, never URL
        # paths, credentials, queries, fragments, or free-form evidence strings.
        origin = context.origin
        domain = getattr(origin, "domain", None)
        safe = None
        if isinstance(domain, str) and len(domain) <= 253 and not any(c in domain for c in "/@?#\\"):
            host = "[" + domain + "]" if domain.count(":") >= 2 and not domain.startswith("[") else domain
            safe = origin_from_url("https://" + host)
        if safe is None or not safe.url:
            safe = origin_from_url(getattr(origin, "url", None))
        if safe.url:
            add(safe.domain, SignalType.ORIGIN_DOMAIN, "origin.domain")
            if safe.site_name != safe.domain:
                add(safe.site_name, SignalType.ORIGIN_DOMAIN, "origin.site_name")

        fields(getattr(metadata, "headings", None), SignalType.DOCUMENT_HEADING, "metadata.headings")
        stem = context.stem
        if not isinstance(stem, str) or not stem:
            stem = os.path.splitext(context.filename)[0] if isinstance(context.filename, str) and len(context.filename) <= 4096 else ""
        field(stem, SignalType.FILENAME_TOKEN, "stem", 512)
        fields(getattr(metadata, "code_symbols", None), SignalType.CODE_SYNTAX, "metadata.code_symbols", 128)
        field(getattr(metadata, "code_language", None), SignalType.CODE_SYNTAX, "metadata.code_language", 64)
        fields(getattr(metadata, "keywords", None), SignalType.CONTENT_KEYWORD, "metadata.keywords", 20, 128)
        field(getattr(metadata, "text_preview", None), SignalType.CONTENT_KEYWORD, "metadata.text_preview")

        media = getattr(metadata, "extractor_name", "") in ("MediaExtractor", "ImageExtractor")
        for name in ("author", "subject"):
            field(getattr(metadata, name, None), SignalType.MEDIA_METADATA if media else SignalType.CONTENT_KEYWORD,
                  "metadata." + name, 256)
        tags = getattr(metadata, "exif_tags", None)
        if isinstance(tags, dict):
            for name in ("Make", "Model", "Software", "LensModel"):
                field(tags.get(name), SignalType.EXIF_CAMERA, "metadata.exif_tags." + name, 256)

        if isinstance(context.path, str) and len(context.path) <= 4096:
            parent = os.path.basename(os.path.dirname(context.path.rstrip("/")))
            field(parent, SignalType.DIRECTORY_CONTEXT, "parent_directory", 256)
        fields(getattr(metadata, "toc_entries", None), SignalType.ARCHIVE_CONTENT, "metadata.toc_entries", 500, 1024)
        extension = context.extension
        if isinstance(extension, str):
            hint = _EXTENSIONS.get(extension.lower())
            if hint:
                add(hint, SignalType.EXTENSION_HINT, "extension")

        scores = {}
        for signal in result.weighted_signals:
            for domain, affinity in DOMAIN_SIGNAL_AFFINITIES.get(signal.token, {}).items():
                scores[domain] = scores.get(domain, 0.0) + signal.weight * affinity
        total = sum(scores.values())
        if total:
            result.domain_affinities = {domain: scores[domain] / total for domain in sorted(scores)}
        context.signals = result
        return result
