from __future__ import annotations

import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _run_props(bold: bool = False, size_half_points: int | None = None) -> str:
    parts: list[str] = []
    if bold:
        parts.append("<w:b/>")
    if size_half_points is not None:
        parts.append(f'<w:sz w:val="{size_half_points}"/>')
    if not parts:
        return ""
    return f"<w:rPr>{''.join(parts)}</w:rPr>"


def _text_run(text: str, *, bold: bool = False, size_half_points: int | None = None) -> str:
    attrs = ' xml:space="preserve"' if text.startswith(" ") or text.endswith(" ") else ""
    return (
        f"<w:r>{_run_props(bold=bold, size_half_points=size_half_points)}"
        f"<w:t{attrs}>{escape(text)}</w:t></w:r>"
    )


def _paragraph(text: str = "", *, style: str | None = None, bold: bool = False, size_half_points: int | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    run = _text_run(text, bold=bold, size_half_points=size_half_points) if text else ""
    return f"<w:p>{ppr}{run}</w:p>"


def _centered_paragraph(text: str = "", *, style: str | None = None, bold: bool = False, size_half_points: int | None = None) -> str:
    ppr_bits: list[str] = []
    if style:
        ppr_bits.append(f'<w:pStyle w:val="{style}"/>')
    ppr_bits.append("<w:jc w:val=\"center\"/>")
    ppr = f"<w:pPr>{''.join(ppr_bits)}</w:pPr>"
    run = _text_run(text, bold=bold, size_half_points=size_half_points) if text else ""
    return f"<w:p>{ppr}{run}</w:p>"


def _page_break_paragraph() -> str:
    return "<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>"


def _bullet_paragraph(text: str) -> str:
    ppr = (
        "<w:pPr>"
        '<w:pStyle w:val="ListParagraph"/>'
        '<w:ind w:left="720" w:hanging="360"/>'
        "</w:pPr>"
    )
    return f"<w:p>{ppr}{_text_run('- ', bold=True)}{_text_run(text)}</w:p>"


def _number_paragraph(number: str, text: str) -> str:
    ppr = (
        "<w:pPr>"
        '<w:pStyle w:val="ListParagraph"/>'
        '<w:ind w:left="720" w:hanging="360"/>'
        "</w:pPr>"
    )
    return f"<w:p>{ppr}{_text_run(number + ' ', bold=True)}{_text_run(text)}</w:p>"


def markdown_to_docx_body(markdown_text: str) -> str:
    paragraphs: list[str] = []
    in_cover = False
    cover_line_index = 0
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped == "<<<COVER>>>":
            in_cover = True
            cover_line_index = 0
            continue
        if stripped == "<<<END_COVER>>>":
            in_cover = False
            continue
        if stripped == "<<<PAGE_BREAK>>>":
            paragraphs.append(_page_break_paragraph())
            continue
        if in_cover:
            if not stripped:
                paragraphs.append(_centered_paragraph())
                continue
            if cover_line_index == 0:
                paragraphs.append(_centered_paragraph(stripped, style="Title", bold=True, size_half_points=36))
            elif cover_line_index == 1:
                paragraphs.append(_centered_paragraph(stripped, style="Heading2", bold=True, size_half_points=32))
            else:
                paragraphs.append(_centered_paragraph(stripped, size_half_points=24))
            cover_line_index += 1
            continue
        if not stripped:
            paragraphs.append(_paragraph())
            continue
        if stripped.startswith("### "):
            paragraphs.append(_paragraph(stripped[4:], style="Heading3"))
            continue
        if stripped.startswith("## "):
            paragraphs.append(_paragraph(stripped[3:], style="Heading2"))
            continue
        if stripped.startswith("# "):
            paragraphs.append(_paragraph(stripped[2:], style="Title"))
            continue
        if stripped.startswith("- "):
            paragraphs.append(_bullet_paragraph(stripped[2:]))
            continue
        number_match = re.match(r"^(\d+\.)\s+(.*)$", stripped)
        if number_match:
            paragraphs.append(_number_paragraph(number_match.group(1), number_match.group(2)))
            continue
        paragraphs.append(_paragraph(stripped))
    return "".join(paragraphs)


def build_document_xml(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
        'xmlns:wne="http://schemas.microsoft.com/office/2006/wordml" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
        'mc:Ignorable="w14 wp14">'
        f"<w:body>{body}"
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )


def build_styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NS}">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/>'
        '<w:qFormat/>'
        '<w:rPr><w:sz w:val="24"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Title">'
        '<w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
        '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2">'
        '<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
        '<w:rPr><w:b/><w:sz w:val="28"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading3">'
        '<w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
        '<w:rPr><w:b/><w:sz w:val="26"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="ListParagraph">'
        '<w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:spacing w:after="80"/></w:pPr>'
        '</w:style>'
        '</w:styles>'
    )


def build_content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )


def build_root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        '</Relationships>'
    )


def build_document_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        '</Relationships>'
    )


def build_core_xml(title: str) -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{escape(title)}</dc:title>"
        "<dc:creator>Codex</dc:creator>"
        "<cp:lastModifiedBy>Codex</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def build_app_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>Codex</Application>"
        "</Properties>"
    )


def write_docx(markdown_path: Path, output_path: Path) -> None:
    markdown_text = markdown_path.read_text(encoding="utf-8")
    title = next((line[2:].strip() for line in markdown_text.splitlines() if line.startswith("# ")), output_path.stem)
    body = markdown_to_docx_body(markdown_text)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", build_content_types_xml())
        docx.writestr("_rels/.rels", build_root_rels_xml())
        docx.writestr("word/document.xml", build_document_xml(body))
        docx.writestr("word/_rels/document.xml.rels", build_document_rels_xml())
        docx.writestr("word/styles.xml", build_styles_xml())
        docx.writestr("docProps/core.xml", build_core_xml(title))
        docx.writestr("docProps/app.xml", build_app_xml())


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python tools/generate_docx_report.py <input.md> <output.docx>")
        return 1
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    write_docx(input_path, output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
