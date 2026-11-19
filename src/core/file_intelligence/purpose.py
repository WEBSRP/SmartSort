"""Small, explicit purpose hints; no models, OCR, pixel decoding or network."""
import re
from src.core.file_intelligence.context import EvidenceItem, SignalType
from src.core.file_intelligence.mime import DeterministicMime
from src.core.file_intelligence.signals import LexicalTokenizer
from src.core.file_intelligence.origin import origin_from_url
from urllib.parse import urlsplit

_PLATFORMS = ('leetcode', 'hackerrank', 'codeforces', 'atcoder', 'codechef')


def purpose_hint(context):
    raw_stem = context.stem[:512] if isinstance(context.stem,str) else ''
    stem = raw_stem.casefold()
    tokens = LexicalTokenizer.tokenize(raw_stem)
    words = set(re.findall(r'[a-z0-9]+', stem)) | set(tokens)
    normalized = ' '.join(re.findall(r'[a-z0-9]+', stem)) + ' ' + ' '.join(tokens)
    metadata = context.metadata
    title = getattr(metadata, 'title', '') or ''
    body = getattr(metadata, 'text_preview', '') or ''
    text = ((title[:512] if isinstance(title,str) else '')+' '+(body[:4096] if isinstance(body,str) else '')).casefold()
    extension = context.extension if isinstance(context.extension,str) else ''
    image = (DeterministicMime.get_category_hint(extension)=='Images'
             or (isinstance(context.mime_type,str) and context.mime_type.startswith('image/')))
    # A site's logo or avatar is not a screenshot of a programming problem.
    asset = bool(words & {'logo','icon','avatar','banner'})
    named_challenge = (any(site in words for site in _PLATFORMS)
                       or any(phrase in normalized for phrase in (
                           'coding challenge','programming challenge','programming problem','algorithm challenge')))
    safe_origin = origin_from_url(getattr(context.origin, 'url', None))
    host = safe_origin.domain or ''
    trusted_source = any(host == domain or host.endswith('.'+domain) for domain in (
        'leetcode.com','hackerrank.com','codeforces.com','atcoder.jp','codechef.com'))
    source_challenge = trusted_source and (bool(words & {'screenshot','challenge','problem','solution'})
        or any(part in urlsplit(safe_origin.url or '').path.lower() for part in ('/problems/','/contest/','/contests/')))
    # Require several structural clues, not an isolated word such as "code".
    body_challenge = ('problem statement' in text and 'constraints' in text
                      and 'example' in text and ('input' in text or 'output' in text))
    # Existing academic heuristics retain explicit coursework contexts.
    coursework = bool(words & {'assignment','lecture','exam','semester','course'})
    if not asset and not coursework and (named_challenge or body_challenge or source_challenge):
        kind = SignalType.FILENAME_TOKEN if named_challenge else SignalType.CONTENT_KEYWORD if body_challenge else SignalType.ORIGIN_DOMAIN
        source = 'stem' if named_challenge else 'metadata.text_preview' if body_challenge else 'origin.domain'
        reason = ('Filename identifies a coding-challenge platform or purpose' if named_challenge
                  else 'Document has a problem statement, constraints and worked input/output examples' if body_challenge
                  else 'Known coding-challenge source with problem/screenshot context')
        domain,parts = ('Media',['Images','Coding_Challenges']) if image else ('Projects',['Coding_Challenges'])
        language = DeterministicMime.get_code_folder(context.extension,getattr(metadata,'code_language',None))
        if not image and language:
            parts.append(language)
        return domain,parts,.72,[EvidenceItem(kind,reason,.72,source)]
    if image:
        if 'wallpaper' in words or 'wallpapers' in words or 'desktop background' in normalized:
            return 'Media',['Images','Wallpapers'],.72,[EvidenceItem(SignalType.FILENAME_TOKEN,
                'Filename explicitly identifies a wallpaper/background',.72,'stem')]
        if 'screenshot' in words or 'screen capture' in normalized:
            return 'Media',['Images','Screenshots'],.65,[EvidenceItem(SignalType.FILENAME_TOKEN,
                'Filename explicitly identifies a screenshot',.65,'stem')]
    return None
