"""
ReportLab PDF export for SDA briefs.

Structure:
  Cover: ORBITAL SENTINEL header + conjunction summary table + DEMO watermark
  Body:  Five SDA brief sections as flowing text
  Footer: Classification caveat + page numbers
"""

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

from config import PDF_WATERMARK
from risk_engine import format_pc, object_type_label


# ---------------------------------------------------------------------------
# Color palette (dark-blue defense aesthetic)
# ---------------------------------------------------------------------------
C_NAVY = colors.HexColor("#0a1628")
C_BLUE = colors.HexColor("#1a3c5e")
C_ACCENT = colors.HexColor("#4fc3f7")
C_CRITICAL = colors.HexColor("#ff1744")
C_HIGH = colors.HexColor("#ff5722")
C_MEDIUM = colors.HexColor("#ffc107")
C_LOW = colors.HexColor("#66bb6a")
C_WHITE = colors.white
C_LIGHT = colors.HexColor("#b0bec5")

RISK_COLORS = {"CRITICAL": C_CRITICAL, "HIGH": C_HIGH, "MEDIUM": C_MEDIUM, "LOW": C_LOW}


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"],
            fontSize=20, textColor=C_WHITE, backColor=C_NAVY,
            spaceAfter=4, spaceBefore=0, leading=24,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"],
            fontSize=10, textColor=C_ACCENT, spaceAfter=2,
        ),
        "section_header": ParagraphStyle(
            "section_header", parent=base["Heading2"],
            fontSize=11, textColor=C_ACCENT,
            spaceBefore=14, spaceAfter=4, leading=14,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontSize=9, textColor=colors.HexColor("#222222"),
            spaceAfter=6, leading=13,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base["Normal"],
            fontSize=9, textColor=colors.HexColor("#222222"),
            spaceAfter=4, leading=13, leftIndent=14, bulletIndent=0,
        ),
        "caveat": ParagraphStyle(
            "caveat", parent=base["Normal"],
            fontSize=7, textColor=C_LIGHT, alignment=1,
        ),
        "watermark": ParagraphStyle(
            "watermark", parent=base["Normal"],
            fontSize=8, textColor=colors.red, alignment=1,
        ),
    }


def _summary_table(conjunction) -> Table:
    tca_str = conjunction.tca.strftime("%Y-%m-%d %H:%M UTC")
    pc_str = format_pc(conjunction.pc)
    risk_color = RISK_COLORS.get(conjunction.risk_level, C_LOW)

    data = [
        ["CONJUNCTION SUMMARY", ""],
        ["Object 1", f"{conjunction.sat1_name}  (NORAD {conjunction.sat1_norad})  —  {object_type_label(conjunction.sat1_type)}"],
        ["Object 2", f"{conjunction.sat2_name}  (NORAD {conjunction.sat2_norad})  —  {object_type_label(conjunction.sat2_type)}"],
        ["Time of Closest Approach", tca_str],
        ["Miss Distance", f"{conjunction.miss_distance_km * 1000:.0f} m  ({conjunction.miss_distance_km:.4f} km)"],
        ["Relative Speed", f"{conjunction.relative_speed_km_s:.2f} km/s"],
        ["Probability of Collision", pc_str],
        ["Risk Level", conjunction.risk_level],
        ["Risk Score", f"{conjunction.risk_score:.1f} / 100"],
        ["CDM ID", conjunction.cdm_id],
    ]

    table = Table(data, colWidths=[2.1 * inch, 4.4 * inch])
    style = TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), C_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("SPAN", (0, 0), (-1, 0)),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        # Data rows
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f5f8fa")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#f5f8fa"), colors.HexColor("#e8f0f5")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b0c4de")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        # Risk level row — colored text
        ("TEXTCOLOR", (1, 7), (1, 7), risk_color),
        ("FONTNAME", (1, 7), (1, 7), "Helvetica-Bold"),
    ])
    table.setStyle(style)
    return table


def generate_pdf(conjunction, brief_sections: dict) -> bytes:
    """
    Generate a PDF SDA brief and return raw bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    s = _styles()
    story = []

    # Header
    story.append(Paragraph("ORBITAL SENTINEL", s["title"]))
    story.append(Paragraph("Space Domain Awareness Brief Generator  ·  18th SDS Conjunction Data", s["subtitle"]))
    story.append(Paragraph(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        s["subtitle"],
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ACCENT, spaceAfter=10))

    if PDF_WATERMARK:
        story.append(Paragraph(f"⚠ {PDF_WATERMARK} — NOT FOR OPERATIONAL USE ⚠", s["watermark"]))
        story.append(Spacer(1, 6))

    # Summary table
    story.append(_summary_table(conjunction))
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BLUE, spaceAfter=6))

    # Brief sections
    section_order = [
        "SITUATION",
        "ORBITAL ENVIRONMENT",
        "CONJUNCTION ASSESSMENT",
        "DEFENSE & OPERATIONAL EXPOSURE",
        "WATCH ITEMS",
    ]

    for header in section_order:
        text = brief_sections.get(header, "")
        if not text:
            continue
        story.append(Paragraph(header, s["section_header"]))
        if header == "WATCH ITEMS":
            for line in text.split("\n"):
                line = line.strip().lstrip("•-·").strip()
                if line:
                    story.append(Paragraph(f"• {line}", s["bullet"]))
        else:
            for para in text.split("\n\n"):
                para = para.strip()
                if para:
                    story.append(Paragraph(para, s["body"]))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_LIGHT))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "UNCLASSIFIED // FOR DEMONSTRATION PURPOSES ONLY // NOT FOR OPERATIONAL USE",
        s["caveat"],
    ))
    story.append(Paragraph(
        "Data source: 18th Space Defense Squadron CDM (Space-Track.org) · "
        "Orbital Sentinel v1.0 · github.com/JakPot42/orbital-sentinel",
        s["caveat"],
    ))

    doc.build(story)
    return buf.getvalue()
