from copy import copy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


ASSET_DIR = Path(settings.BASE_DIR) / 'MyApp' / 'quotation_templates'
EXCEL_TEMPLATE = ASSET_DIR / 'exalter_quotation_template.xlsx'
LETTERHEAD_IMAGE = ASSET_DIR / 'exalter_letterhead.jpeg'

DEFAULT_INTRODUCTION = (
    'On behalf of Exalter Trading & Contracting, we thank you for giving us an '
    'opportunity to submit our best offer.'
)


def _number_words(value):
    ones = (
        'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
        'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen',
        'sixteen', 'seventeen', 'eighteen', 'nineteen',
    )
    tens = ('', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety')

    def integer_words(number):
        if number < 20:
            return ones[number]
        if number < 100:
            return tens[number // 10] + (f'-{ones[number % 10]}' if number % 10 else '')
        if number < 1_000:
            return f'{ones[number // 100]} hundred' + (
                f' and {integer_words(number % 100)}' if number % 100 else ''
            )
        for size, label in ((1_000_000_000, 'billion'), (1_000_000, 'million'), (1_000, 'thousand')):
            if number >= size:
                return f'{integer_words(number // size)} {label}' + (
                    f' {integer_words(number % size)}' if number % size else ''
                )
        return str(number)

    amount = value.quantize(value.__class__('0.01'))
    riyals = int(amount)
    dirhams = int((amount - riyals) * 100)
    result = f'{integer_words(riyals)} Qatari riyals'
    if dirhams:
        result += f' and {integer_words(dirhams)} dirhams'
    return result


def _copy_row_style(sheet, source_row, target_row):
    sheet.row_dimensions[target_row].height = sheet.row_dimensions[source_row].height
    for column in range(2, 8):
        source = sheet.cell(source_row, column)
        target = sheet.cell(target_row, column)
        if source.has_style:
            target._style = copy(source._style)
        target.number_format = source.number_format
        target.alignment = copy(source.alignment)
        target.protection = copy(source.protection)


def _quotation_lines(quote):
    lines = list(quote.lines.all())
    if lines:
        return lines
    return [SimpleNamespace(
        description=quote.details or 'Quotation total', unit='lot',
        quantity=quote.amount.__class__('1'), unit_rate=quote.amount,
        amount=quote.amount,
    )]


def _insert_line_rows(sheet, count):
    extra = max(0, count - 1)
    if not extra:
        return 0
    shifted_merges = []
    for merged in list(sheet.merged_cells.ranges):
        if merged.min_row >= 19:
            shifted_merges.append((str(merged), merged.min_col, merged.min_row, merged.max_col, merged.max_row))
            sheet.unmerge_cells(str(merged))
    sheet.insert_rows(19, extra)
    for _, min_col, min_row, max_col, max_row in shifted_merges:
        sheet.merge_cells(
            start_row=min_row + extra, start_column=min_col,
            end_row=max_row + extra, end_column=max_col,
        )
    for row in range(19, 19 + extra):
        _copy_row_style(sheet, 18, row)
    return extra


def build_quotation_excel(quote):
    workbook = load_workbook(EXCEL_TEMPLATE)
    sheet = workbook.active
    lines = _quotation_lines(quote)
    extra = _insert_line_rows(sheet, len(lines))
    enquiry = quote.ENQUIRY

    sheet['B8'] = f'M/s {enquiry.client_name.upper()}'
    sheet['B9'] = quote.client_address or 'Doha-State of Qatar'
    sheet['B10'] = f'Mob: {enquiry.client_phone}' if enquiry.client_phone else 'Mob:'
    sheet['B11'] = f'Email: {enquiry.client_email}' if enquiry.client_email else 'Email:'
    sheet['F8'] = quote.display_number
    sheet['F9'] = quote.issue_date
    sheet['F9'].number_format = 'dd-mmm-yy'
    sheet['C14'] = f'Subject : {quote.subject}'
    sheet['C16'] = quote.introduction or DEFAULT_INTRODUCTION

    for offset, line in enumerate(lines):
        row = 18 + offset
        sheet.cell(row, 2, offset + 1)
        sheet.cell(row, 3, line.description)
        sheet.cell(row, 4, line.unit)
        sheet.cell(row, 5, float(line.quantity))
        sheet.cell(row, 6, float(line.unit_rate))
        sheet.cell(row, 7, f'=E{row}*F{row}')
        sheet.cell(row, 5).number_format = '#,##0.00'
        sheet.cell(row, 6).number_format = '#,##0.00'
        sheet.cell(row, 7).number_format = '#,##0.00'

    total_row = 19 + extra
    sheet.cell(total_row, 2, f'Grand Total (QAR - {_number_words(quote.amount)} only)')
    sheet.cell(total_row, 7, f'=SUM(G18:G{17 + len(lines)})')
    sheet.cell(total_row, 7).number_format = '#,##0.00'

    sheet.cell(23 + extra, 2, quote.details)
    sheet.cell(26 + extra, 2, f'This quotation is valid for {quote.validity_days} days from the date of issue unless otherwise stated.')
    payment_lines = [line.strip() for line in quote.payment_terms.splitlines() if line.strip()]
    for index, value in enumerate(payment_lines[:4]):
        sheet.cell(29 + extra + index, 2, value)
    sheet.cell(35 + extra, 2, quote.mobilization)
    sheet.cell(38 + extra, 2, quote.variations)
    responsibilities = [line.strip() for line in quote.client_responsibilities.splitlines() if line.strip()]
    for index, value in enumerate(responsibilities[:4]):
        sheet.cell(41 + extra + index, 2, value)
    sheet.cell(57 + extra, 2, quote.material_approval)
    sheet.cell(60 + extra, 2, quote.project_duration)
    sheet.cell(62 + extra, 2, quote.closing_text)
    sheet.cell(67 + extra, 2, quote.signatory_name)
    sheet.cell(68 + extra, 2, quote.signatory_title)
    sheet.cell(69 + extra, 2, f'Mobile {quote.signatory_phone}' if quote.signatory_phone else '')
    sheet.print_area = f'B8:G{69 + extra}'
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def build_quotation_pdf(quote):
    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=34 * mm, bottomMargin=26 * mm,
        title=quote.display_number, author='Exalter Trading & Contracting',
    )

    def draw_letterhead(canvas, document):
        canvas.saveState()
        canvas.drawImage(
            str(LETTERHEAD_IMAGE), 0, 0, width=A4[0], height=A4[1],
            preserveAspectRatio=False, mask='auto',
        )
        canvas.setFillColor(colors.HexColor('#8c7428'))
        canvas.setFont('Helvetica', 7)
        canvas.drawRightString(A4[0] - 14 * mm, 13 * mm, f'Page {document.page}')
        canvas.restoreState()

    styles = getSampleStyleSheet()
    normal = ParagraphStyle('QuotationBody', parent=styles['BodyText'], fontName='Helvetica', fontSize=8.5, leading=11)
    small = ParagraphStyle('QuotationSmall', parent=normal, fontSize=8, leading=10)
    heading = ParagraphStyle('QuotationHeading', parent=normal, fontName='Helvetica-Bold', spaceBefore=7, spaceAfter=3)
    title = ParagraphStyle('QuotationTitle', parent=styles['Heading2'], alignment=TA_CENTER, fontSize=13, leading=15)
    subject = ParagraphStyle('QuotationSubject', parent=normal, fontName='Helvetica-Bold', alignment=TA_LEFT, spaceBefore=7, spaceAfter=6)

    record = quote.ENQUIRY
    client_lines = [f'<b>M/s {record.client_name.upper()}</b>']
    if quote.client_address:
        client_lines.append(quote.client_address)
    if record.client_phone:
        client_lines.append(f'Mob: {record.client_phone}')
    if record.client_email:
        client_lines.append(f'Email: {record.client_email}')
    info = Table([
        [Paragraph('<br/>'.join(client_lines), normal), Paragraph(
            f'<b>{quote.display_number}</b><br/>{quote.issue_date:%d-%b-%y}', normal,
        )],
    ], colWidths=[105 * mm, 48 * mm])
    info.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))

    story = [info, Spacer(1, 4 * mm), Paragraph('Quotation', title)]
    story.extend([
        Paragraph(f'Subject : <u>{quote.subject}</u>', subject),
        Paragraph('<b>Dear Sir,</b>', normal),
        Spacer(1, 2 * mm),
        Paragraph(quote.introduction or DEFAULT_INTRODUCTION, normal),
        Spacer(1, 3 * mm),
    ])

    table_data = [[
        Paragraph('<b>ITEMS</b>', small), Paragraph('<b>DESCRIPTION</b>', small),
        Paragraph('<b>UNIT</b>', small), Paragraph('<b>QTY</b>', small),
        Paragraph('<b>RATE</b>', small), Paragraph('<b>AMOUNT</b>', small),
    ]]
    for index, line in enumerate(_quotation_lines(quote), start=1):
        table_data.append([
            str(index), Paragraph(line.description, small), line.unit,
            f'{line.quantity:,.2f}', f'{line.unit_rate:,.2f}', f'{line.amount:,.2f}',
        ])
    table_data.append([
        Paragraph(f'<b>Grand Total (QAR - {_number_words(quote.amount)} only)</b>', small),
        '', '', '', '', f'{quote.amount:,.2f}',
    ])
    line_table = Table(table_data, colWidths=[12 * mm, 72 * mm, 15 * mm, 14 * mm, 20 * mm, 23 * mm], repeatRows=1)
    line_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), .55, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
        ('SPAN', (0, -1), (4, -1)),
        ('ALIGN', (0, -1), (4, -1), 'CENTER'),
        ('FONTNAME', (-1, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f4f1e8')),
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.extend([line_table, Paragraph('<u><b>Specification/Clarification</b></u>', heading)])

    sections = [
        ('1. Scope of Work:', quote.details),
        ('2. Validity of Quotation:', f'This quotation is valid for {quote.validity_days} days from the date of issue unless otherwise stated.'),
        ('3. Payment Terms', quote.payment_terms),
        ('4. Mobilization', quote.mobilization),
        ('5. Variations', quote.variations),
        ('6. Client Responsibilities', quote.client_responsibilities),
        ('8. Material Approval', quote.material_approval),
        ('9. Project Duration', quote.project_duration),
    ]
    for label, value in sections:
        if not value:
            continue
        story.append(Paragraph(f'<u>{label}</u>', heading))
        for line in value.splitlines() or ['']:
            if line.strip():
                story.append(Paragraph(line.strip(), normal))

    story.extend([
        Spacer(1, 4 * mm), Paragraph(quote.closing_text, normal),
        Spacer(1, 5 * mm), Paragraph('<b>With Best Regards,</b>', normal),
        Spacer(1, 4 * mm), Paragraph('<b>Exalter Trading &amp; Contracting</b>', normal),
        Paragraph(f'<b>{quote.signatory_name}</b>', normal),
        Paragraph(f'<b>{quote.signatory_title}</b>', normal),
        Paragraph(f'<b>Mobile {quote.signatory_phone}</b>', normal),
    ])
    doc.build(story, onFirstPage=draw_letterhead, onLaterPages=draw_letterhead)
    output.seek(0)
    return output
