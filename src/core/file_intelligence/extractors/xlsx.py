"""Workbook names and first-row headers; no formula evaluation or data import."""

from contextlib import closing

from src.core.file_intelligence.extractors._office import (
    OfficeExtractor, attribute, heading, local, text_of,
)


class XlsxExtractor(OfficeExtractor):
    SUPPORTED_EXTENSIONS = frozenset([".xlsx", ".xls", ".ods"])
    LEGACY_EXTENSIONS = frozenset([".xls"])
    ODF_EXTENSIONS = frozenset([".ods"])
    MIME_TYPES = frozenset([
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.oasis.opendocument.spreadsheet", "application/vnd.ms-excel",
    ])

    def _content(self, package, result, sample):
        workbook = package.xml("xl/workbook.xml", root_tag="workbook")
        targets = package.relationships("xl/_rels/workbook.xml.rels", "xl", "worksheet")
        cells = []
        sheets = [n for n in workbook.iter() if local(n.tag) == "sheet"]
        if len(sheets) > 32:
            package.warnings.append("Workbook inspection limited to 32 sheets")
        for sheet in sheets[:32]:
            name = attribute(sheet, "name")[:256]
            heading(result, name)
            sample.add(name)
            if not result.title:
                result.title = name or None
            rel_id = next((v for k, v in sheet.attrib.items() if k.endswith("}id")), "")
            path = targets.get(rel_id)
            if path is None:
                package.warnings.append("Missing or external worksheet relationship")
                continue
            with closing(package.events(path, "worksheet")) as events:
                for event, element in events:
                    if event != "end" or local(element.tag) != "row":
                        continue
                    if attribute(element, "r", "1") == "1":
                        for cell in list(element)[:64]:
                            if local(cell.tag) != "c":
                                continue
                            kind = attribute(cell, "t")
                            value = text_of(cell, ("t",)) if kind == "inlineStr" else text_of(cell, ("v",))
                            cells.append((kind, value[:256]))
                    break
        needed = {int(v) for kind, v in cells if kind == "s" and v.isdecimal()}
        strings = {}
        if needed:
            if not package.has("xl/sharedStrings.xml"):
                package.warnings.append("Shared string table is missing")
            else:
                index = 0
                with closing(package.events("xl/sharedStrings.xml", "sst")) as events:
                    for event, element in events:
                        if event != "end" or local(element.tag) != "si":
                            continue
                        if index in needed:
                            strings[index] = text_of(element)[:256]
                        element.clear()
                        index += 1
                        if needed.issubset(strings):
                            break
        for kind, value in cells:
            if kind == "s":
                value = strings.get(int(value), "") if value.isdecimal() else ""
                if not value:
                    package.warnings.append("A shared header string could not be resolved")
            heading(result, value)
            sample.add(value)

    def _odf(self, package, result, sample):
        count, row = 0, 0
        with closing(package.events("content.xml", "document-content")) as events:
            for event, element in events:
                name = local(element.tag)
                if event == "start" and name == "table":
                    count += 1
                    if count > 32:
                        package.warnings.append("Workbook inspection limited to 32 sheets")
                        break
                    row = 0
                    title = attribute(element, "name")[:256]
                    heading(result, title)
                    sample.add(title)
                    if not result.title:
                        result.title = title or None
                elif event == "end" and name == "table-row":
                    if row == 0:
                        for cell in list(element)[:64]:
                            text = " ".join("".join(n.itertext()).strip() for n in cell.iter() if local(n.tag) == "p")
                            heading(result, text)
                            sample.add(text)
                    row += 1
                    element.clear()
