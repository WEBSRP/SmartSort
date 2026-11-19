"""Word/OpenDocument text metadata inspection without loading Office SDKs."""

from contextlib import closing
import re

from src.core.file_intelligence.extractors._office import (
    OfficeExtractor, attribute, heading, local, text_of,
)


class DocxExtractor(OfficeExtractor):
    SUPPORTED_EXTENSIONS = frozenset([".docx", ".doc", ".odt", ".rtf"])
    LEGACY_EXTENSIONS = frozenset([".doc", ".rtf"])
    ODF_EXTENSIONS = frozenset([".odt"])
    MIME_TYPES = frozenset([
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text", "application/msword", "application/rtf",
    ])

    def _content(self, package, result, sample):
        title = result.title
        count = 0
        with closing(package.events("word/document.xml", "document")) as events:
            for event, element in events:
                if event != "end" or local(element.tag) != "p":
                    continue
                count += 1
                text = text_of(element)
                sample.add(text)
                style = next((attribute(n, "val") for n in element.iter() if local(n.tag) == "pStyle"), "")
                style = re.sub(r"\s", "", style).lower()
                if style in ("heading1", "heading2", "heading3"):
                    heading(result, text)
                if not title and text and (style == "title" or (style == "heading1" and not result.title)):
                    result.title = text[:256]
                    if style == "title":
                        title = result.title
                element.clear()
                if count >= 20:
                    break
        if not result.title:
            result.title = next((line[:256] for line in sample.text.splitlines() if line.strip()), None)

    def _odf(self, package, result, sample):
        count = 0
        with closing(package.events("content.xml", "document-content")) as events:
            for event, element in events:
                if event != "end" or local(element.tag) not in ("p", "h"):
                    continue
                text = "".join(element.itertext()).strip()
                count += 1
                sample.add(text)
                if local(element.tag) == "h":
                    heading(result, text)
                    if not result.title and text:
                        result.title = text[:256]
                element.clear()
                if count >= 20:
                    break
        if not result.title:
            result.title = next((line[:256] for line in sample.text.splitlines() if line.strip()), None)
