"""Portrait PDF portfolio and participation extracts with vector QR codes."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics import renderSVG
from app.config import settings
from app.services.documents import OfficialDocument, render_pdf, pdf_fonts


def qr_drawing(url, size=105):
    qr = QrCodeWidget(url, barLevel="M")
    x1, y1, x2, y2 = qr.getBounds()
    drawing = Drawing(
        size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0]
    )
    drawing.add(qr)
    return drawing


def qr_svg(url):
    return renderSVG.drawToString(qr_drawing(url, 240)).encode("utf-8")


def certificate_pdf(data, url, *, certificate, private_access):
    """Use the protocol letterhead and layout for QR participation documents."""
    from datetime import date
    from reportlab.lib.units import mm

    pdf_fonts()
    entry, competition = data["entry"], data["competition"]
    number = data.get("certificate_number", "FSP-CERT-" + data["fingerprint"][:12].upper())
    document = OfficialDocument(
        kind="Справка" if certificate else "Выписка из протокола",
        title="об участии в соревновании" if certificate else "о результате участия в соревновании",
        dated=date.today(),
        number=number,
        place=settings.fsp_city,
        meta=[
            ("Соревнование", competition["title"]),
            ("Дата проведения", date.fromisoformat(competition["start_date"]).strftime("%d.%m.%Y")),
            ("Дисциплина", competition["discipline"]),
            ("Место проведения", competition["location"]),
            ("Основание", f"Опубликованный протокол, редакция {data['version']} от "
             + date.fromisoformat(data["published_at"][:10]).strftime("%d.%m.%Y")),
            ("Спортсмен", entry["full_name"]),
            ("Идентификатор спортсмена", data["public_id"]),
            ("Организация", entry["organization"]),
        ],
        intro=["Настоящая справка подтверждает участие спортсмена в указанном соревновании. "
               "Сведения о результате приведены по опубликованной редакции протокола."],
        headers=["№ п/п", "Место", "Баллы"],
        rows=[[1, entry["place"], entry["score"]]],
        signatures=[(settings.fsp_head_position, settings.fsp_head_name)],
    )
    if entry.get("team_name"):
        document.meta.append(("Команда", entry["team_name"]))
    if not data["is_current"]:
        document.outro.append(
            f"Редакция заменена. Актуальная редакция: {data['latest_version']}. "
            "Проверяйте сведения по QR-коду."
        )
    body = ParagraphStyle("certificate-proof", fontName="Doc", fontSize=8, leading=11,
                          spaceAfter=4)
    p = lambda value: Paragraph(escape(str(value)), body)
    proof = [
        Paragraph("<b>Проверка справки по QR-коду</b>", body),
        Paragraph('<link href="' + escape(url, {'"': '&quot;'})
                  + '"><u>Открыть страницу проверки</u></link>', body),
        p("QR открывает публичную проверку номера и статуса без персональных данных. "
          "Полная справка доступна только в личном кабинете."
          if private_access else "QR открывает страницу проверки сведений."),
        p("SHA-256: " + data["fingerprint"][:32]),
        p(data["fingerprint"][32:]),
        p("Справка сформирована автоматически и не является официальным документом."),
    ]
    width = A4[0] - 40 * mm
    verification = Table([[qr_drawing(url, 82), proof]], colWidths=[98, width - 98])
    verification.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    out = BytesIO()
    render_pdf(document, out, trailing_content=[KeepTogether([Spacer(1, 10), verification])])
    return out.getvalue()


def pdf_document(data, url, *, certificate=False, protocol=False, private_access=False):
    if certificate or protocol:
        return certificate_pdf(data, url, certificate=certificate, private_access=private_access)
    font = Path(settings.pdf_font)
    if not font.is_file():
        raise HTTPException(503, "Не найден PDF_FONT с поддержкой кириллицы")
    if "Cyrillic" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Cyrillic", str(font)))
    body = ParagraphStyle(
        "passport-body",
        fontName="Cyrillic",
        fontSize=9,
        leading=14,
        textColor=colors.HexColor("#242832"),
        spaceAfter=7,
    )
    heading = ParagraphStyle(
        "passport-title",
        parent=body,
        fontSize=20,
        leading=26,
        spaceAfter=14,
        textColor=colors.HexColor("#BB2E40"),
    )
    section = ParagraphStyle(
        "passport-section",
        parent=body,
        fontSize=12,
        leading=18,
        spaceBefore=12,
        spaceAfter=9,
    )
    tiny = ParagraphStyle(
        "passport-tiny",
        parent=body,
        fontSize=7.5,
        leading=11,
        textColor=colors.HexColor("#667085"),
    )
    para = lambda text, style=body: Paragraph(
        escape(str(text if text is not None else "")), style
    )
    out = BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        rightMargin=38,
        leftMargin=38,
        topMargin=35,
        bottomMargin=45,
        title="Цифровой паспорт спортсмена"
        if not certificate and not protocol
        else "Выписка из протокола",
        author="ОренКод · ФСП Оренбургской области",
    )
    story = [
        para(
            "оренкод · Федерация спортивного программирования Оренбургской области",
            tiny,
        ),
        Spacer(1, 15),
    ]
    story += [
        para("Цифровой паспорт спортсмена", heading),
        para(data["full_name"], section),
        para(data["public_id"]),
        para(f"{data['municipality']} · {data['organization']}"),
        para("Дисциплины: " + "; ".join(d["name"] for d in data["disciplines"])),
    ]
    for rank in data["ranks"]:
        story.append(
            para(
                f"{rank['discipline']}: {rank['name']} · до {rank['expires_on']}"
                + ("" if rank["active"] else " · требует подтверждения")
            )
        )
    for rating in data["ratings"]:
        story.append(
            para(
                f"Рейтинг {rating['season']} · {rating['discipline']}: {rating['points']} · место в регионе {rating['position']}"
            )
        )
    if data["team"]:
        story.append(
            para(
                "В сборной региона: "
                + "; ".join(
                    f"{t['discipline']} ({t['season']})" for t in data["team"]
                )
            )
        )
    if data.get("rusada"):
        story.append(para("Курс РУСАДА пройден: " + data["rusada"]["completed_on"]))
    if data["visibility"]["results"]:
        story.append(para("История выступлений", section))
        if data["results"]:
            rows = [
                [
                    para(x, tiny)
                    for x in ["Дата", "Соревнование / дисциплина", "Место", "Баллы"]
                ]
            ]
            rows += [
                [
                    para(r["start_date"], tiny),
                    para(r["title"] + " · " + r["discipline"], tiny),
                    para(r["place"]),
                    para(r["score"]),
                ]
                for r in data["results"]
            ]
            table = Table(
                rows,
                colWidths=[66, 300, 42, A4[0] - 76 - 408],
                repeatRows=1,
                hAlign="LEFT",
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3E7E8")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#F5F6F8")],
                        ),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ]
                )
            )
            story.append(table)
        else:
            story.append(para("Пока нет опубликованных выступлений"))
    digest = data["fingerprint"]
    from datetime import date

    proof_text = [
        Paragraph(
            '<link href="' + escape(url, {'"': '&quot;'})
            + '" color="#BB2E40"><u>Открыть страницу проверки</u></link>',
            tiny,
        ),
        para("SHA-256: " + digest[:32], tiny),
        para(digest[32:], tiny),
        para("Сформировано " + date.today().isoformat(), tiny),
        para(
            "Справка сформирована автоматически и не является официальным документом."
            if private_access
            else "Сформировано автоматически, не является официальным документом. Паспорт не является официальным документом о присвоении разряда.",
            tiny,
        ),
    ]
    if private_access:
        proof_text.insert(
            0,
            para(
                "QR открывает публичную проверку номера и статуса без персональных данных. Полная справка доступна только в личном кабинете.",
                tiny,
            ),
        )
    proof_table = Table(
        [[qr_drawing(url, 92), proof_text]],
        colWidths=[112, A4[0] - 76 - 112],
        hAlign="LEFT",
    )
    proof_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(
        KeepTogether(
            [
                Spacer(1, 12),
                para(
                    "Проверить справку по QR"
                    if private_access
                    else "Проверить сведения по QR",
                    section,
                ),
                proof_table,
            ]
        )
    )

    def footer(canvas, document):
        canvas.setFont("Cyrillic", 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(38, 24, "ОренКод · ФСП Оренбургской области")
        canvas.drawRightString(A4[0] - 38, 24, f"Страница {document.page}")

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
