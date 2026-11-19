"""Bounded PowerPoint/OpenDocument presentation metadata inspection."""

from contextlib import closing
import re

from src.core.file_intelligence.extractors._office import (
    OfficeExtractor, attribute, heading, local, text_of,
)


class PptxExtractor(OfficeExtractor):
    SUPPORTED_EXTENSIONS = frozenset([".pptx", ".ppt", ".odp"])
    LEGACY_EXTENSIONS = frozenset([".ppt"])
    ODF_EXTENSIONS = frozenset([".odp"])
    MIME_TYPES = frozenset([
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.presentation", "application/vnd.ms-powerpoint",
    ])

    def _content(self, package, result, sample):
        presentation = package.xml("ppt/presentation.xml", optional=True, root_tag="presentation")
        if presentation is not None:
            targets = package.relationships("ppt/_rels/presentation.xml.rels", "ppt", "slide")
            slides = []
            for node in presentation.iter():
                if local(node.tag) == "sldId":
                    rel_id = next((v for k, v in node.attrib.items() if k.endswith("}id")), "")
                    if rel_id in targets:
                        slides.append(targets[rel_id])
                    else:
                        package.warnings.append("Missing or external presentation slide relationship")
                    if len(slides) >= 5:
                        break
        else:
            slides = sorted(
                (name for name in package.zip.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=lambda name: int(re.search(r"slide(\d+)\.xml$", name).group(1)),
            )[:5]
        if not slides:
            package.warnings.append("No presentation slides available")
        for index, path in enumerate(slides):
            slide = package.xml(path, root_tag="sld")
            title = ""
            for shape in slide.iter():
                if local(shape.tag) != "sp":
                    continue
                if any(local(n.tag) == "ph" and attribute(n, "type") in ("title", "ctrTitle") for n in shape.iter()):
                    title = text_of(shape)
                    break
            heading(result, title)
            if index == 0 and not result.title and title:
                result.title = title[:256]
            if index < 3:
                sample.add("\n".join(n.text or "" for n in slide.iter() if local(n.tag) == "t"))

    def _odf(self, package, result, sample):
        count = 0
        with closing(package.events("content.xml", "document-content")) as events:
            for event, element in events:
                if event != "end" or local(element.tag) != "page":
                    continue
                title = next(("".join(n.itertext()).strip() for n in element.iter()
                              if local(n.tag) == "frame" and attribute(n, "class") == "title"), "")
                heading(result, title)
                if count == 0 and not result.title and title:
                    result.title = title[:256]
                if count < 3:
                    sample.add("\n".join("".join(n.itertext()).strip() for n in element.iter() if local(n.tag) in ("p", "h")))
                count += 1
                element.clear()
                if count >= 5:
                    break
