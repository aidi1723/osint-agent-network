from __future__ import annotations

import html
import importlib
from io import BytesIO
from typing import Any

from app.services.report_export import build_report_payload, redact_report_text


PDF_UNAVAILABLE_DETAIL = "PDF export is unavailable because reportlab is not installed."


class ReportPdfDependencyError(RuntimeError):
    pass


def render_report_pdf(detail: dict) -> bytes:
    reportlab = _load_reportlab()
    colors = reportlab["colors"]
    letter = reportlab["letter"]
    inch = reportlab["inch"]
    get_sample_style_sheet = reportlab["get_sample_style_sheet"]
    paragraph_style = reportlab["paragraph_style"]
    simple_doc_template = reportlab["simple_doc_template"]
    paragraph = reportlab["paragraph"]
    spacer = reportlab["spacer"]
    table = reportlab["table"]
    table_style = reportlab["table_style"]
    list_flowable = reportlab["list_flowable"]
    list_item = reportlab["list_item"]
    base_font = reportlab["base_font"]

    payload = build_report_payload(detail)
    title = str(payload.get("name") or "Investigation report")
    quality = payload.get("quality") or {}
    completion = "Ready" if quality.get("completion_ready") else "Needs Review"

    buffer = BytesIO()
    doc = simple_doc_template(
        buffer,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=redact_report_text(title),
        author="osint-agent-network",
    )

    styles = get_sample_style_sheet()
    _apply_base_font(styles, base_font)
    styles.add(
        paragraph_style(
            name="ReportMeta",
            parent=styles["BodyText"],
            fontName=base_font,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#52616f"),
        )
    )
    styles.add(
        paragraph_style(
            name="ReportSectionTitle",
            parent=styles["Heading2"],
            fontName=base_font,
            fontSize=13,
            leading=16,
            spaceBefore=12,
            spaceAfter=6,
            textColor=colors.HexColor("#1f2933"),
        )
    )
    styles.add(
        paragraph_style(
            name="ReportBullet",
            parent=styles["BodyText"],
            fontName=base_font,
            fontSize=9,
            leading=12,
            leftIndent=4,
        )
    )

    story: list[Any] = [
        paragraph(_xml(title), styles["Title"]),
        paragraph(_xml(f"Generated at {payload.get('generated_at', '')}"), styles["ReportMeta"]),
        spacer(1, 8),
        _summary_table(payload, completion, table, table_style, paragraph, styles, colors),
        spacer(1, 10),
    ]

    for section in payload.get("sections", []):
        section_title = str(section.get("title") or section.get("id") or "Section")
        story.append(paragraph(_xml(section_title), styles["ReportSectionTitle"]))
        items = [
            list_item(paragraph(_xml(str(item)), styles["ReportBullet"]), leftIndent=10)
            for item in section.get("items", [])
        ]
        if not items:
            items = [list_item(paragraph("No records available.", styles["ReportBullet"]), leftIndent=10)]
        story.append(list_flowable(items, bulletType="bullet", start="circle", leftIndent=16))

    story.append(spacer(1, 14))
    story.append(
        paragraph(
            "Generated from structured OSINT records. Review source evidence before external distribution.",
            styles["ReportMeta"],
        )
    )

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _load_reportlab() -> dict[str, Any]:
    try:
        colors = importlib.import_module("reportlab.lib.colors")
        pagesizes = importlib.import_module("reportlab.lib.pagesizes")
        units = importlib.import_module("reportlab.lib.units")
        styles = importlib.import_module("reportlab.lib.styles")
        pdfmetrics = importlib.import_module("reportlab.pdfbase.pdfmetrics")
        cidfonts = importlib.import_module("reportlab.pdfbase.cidfonts")
        platypus = importlib.import_module("reportlab.platypus")
        return {
            "colors": colors,
            "letter": pagesizes.letter,
            "inch": units.inch,
            "get_sample_style_sheet": styles.getSampleStyleSheet,
            "paragraph_style": styles.ParagraphStyle,
            "simple_doc_template": platypus.SimpleDocTemplate,
            "paragraph": platypus.Paragraph,
            "spacer": platypus.Spacer,
            "table": platypus.Table,
            "table_style": platypus.TableStyle,
            "list_flowable": platypus.ListFlowable,
            "list_item": platypus.ListItem,
            "base_font": _register_unicode_font(pdfmetrics, cidfonts),
        }
    except ModuleNotFoundError as exc:
        if _is_reportlab_import_error(exc):
            raise ReportPdfDependencyError(PDF_UNAVAILABLE_DETAIL) from exc
        raise


def _summary_table(
    payload: dict,
    completion: str,
    table: Any,
    table_style: Any,
    paragraph: Any,
    styles: Any,
    colors: Any,
) -> Any:
    quality = payload.get("quality") or {}
    rows = [
        ("Status", str(payload.get("status") or "")),
        ("Seed", f"{payload.get('seed_type') or ''}: {payload.get('seed_value') or ''}"),
        ("Quality", f"{quality.get('score', 0)} / 100"),
        ("Completion", completion),
    ]
    summary = table(
        [[paragraph(_xml(label), styles["ReportMeta"]), paragraph(_xml(value), styles["BodyText"])] for label, value in rows],
        colWidths=[90, 370],
    )
    summary.setStyle(
        table_style(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfcfd")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8dee4")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8dee4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return summary


def _footer(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    canvas.setFont("STSong-Light", 8)
    canvas.setFillColorRGB(0.42, 0.47, 0.53)
    canvas.drawString(doc.leftMargin, 0.38 * 72, "Generated from structured OSINT records")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.38 * 72, f"Page {doc.page}")
    canvas.restoreState()


def _xml(value: str) -> str:
    return html.escape(redact_report_text(str(value)), quote=True)


def _is_reportlab_import_error(exc: ModuleNotFoundError) -> bool:
    missing_name = getattr(exc, "name", "") or ""
    return missing_name.startswith("reportlab") or "reportlab" in str(exc)


def _register_unicode_font(pdfmetrics: Any, cidfonts: Any) -> str:
    font_name = "STSong-Light"
    try:
        pdfmetrics.getFont(font_name)
    except KeyError:
        pdfmetrics.registerFont(cidfonts.UnicodeCIDFont(font_name))
    return font_name


def _apply_base_font(styles: Any, font_name: str) -> None:
    for style_name in ("Title", "Heading1", "Heading2", "Heading3", "BodyText"):
        if style_name in styles:
            styles[style_name].fontName = font_name
