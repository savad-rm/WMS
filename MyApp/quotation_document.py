import json
import re
from decimal import Decimal, InvalidOperation
from html import escape


DOCUMENT_PREFIX = '__WMS_QUOTATION_V1__\n'
SECTION_UNIT = '__SECTION__'
SUBHEADING_UNIT = '__SUBHEADING__'
NOTE_UNIT = '__NOTE__'

DEFAULT_INTRODUCTION = (
    'On behalf of Exalter Trading & Contracting, we thank you for giving us an '
    'opportunity to submit our Best offer.'
)
DEFAULT_CLOSING_TEXT = (
    'We hope the above quote meets your requirement and we assure a quality work '
    'completed in time. If you have any further queries please feel free to contact us.'
)
DEFAULT_TERMS = (
    ('Scope of Work', 'The quotation is based on the scope of work, drawings, specifications, and information provided by the Client. Any additional work requested beyond the agreed scope shall be treated as a variation and charged separately.'),
    ('Validity of Quotation', 'This quotation is valid for 14 days from the date of issue unless otherwise stated.'),
    ('Payment Terms', '30% In Advance upon confirmation of the work\n20% On Ceiling Closure\n20% On Shop Front Installation\n20% On Furniture Installation\n10% On completion of the project'),
    ('Exclusions', 'Unless specifically mentioned in the quotation, excluded items shall be confirmed with the Client before commencement.'),
    ('Mobilization', 'Work shall commence within 3 days after receipt of the advance payment, approved drawings, and site handover.'),
    ('Variations', 'Any changes to the approved design, materials, quantities, finishes, or scope requested by the Client shall be subject to a separate variation order and may affect the project cost and completion period.'),
    ('Client Responsibilities', 'Provide unrestricted access to the work site.\nEnsure availability of electricity and water during the construction period.\nProvide timely approvals for drawings, materials, and samples.'),
    ('Material Approval', 'All materials and finishes shall be subject to Client approval. Equivalent materials may be proposed if specified materials become unavailable.'),
    ('Project Duration', 'The project completion period will be confirmed from the date of advance payment, final design approval, and site handover.'),
)


def default_terms(validity_days=14):
    terms = [{'title': title, 'body': body} for title, body in DEFAULT_TERMS]
    terms[1]['body'] = f'This quotation is valid for {validity_days} days from the date of issue unless otherwise stated.'
    return terms


def pack_document(terms, remarks='', tracking=None, client_details=None, draft_state=None):
    payload = {
        'terms': [
            {'title': str(term.get('title', '')).strip(), 'body': str(term.get('body', '')).strip()}
            for term in terms if term.get('title') or term.get('body')
        ],
        'remarks': remarks.strip(),
    }
    if tracking:
        payload['tracking'] = {
            'submitted_at': str(tracking.get('submitted_at', '')).strip(),
            'client_remarks': str(tracking.get('client_remarks', '')).strip(),
            'client_status': str(tracking.get('client_status', 'under_review')).strip(),
            'submitted_to': str(tracking.get('submitted_to', '')).strip(),
            'submitted_cc': str(tracking.get('submitted_cc', '')).strip(),
            'submitted_subject': str(tracking.get('submitted_subject', '')).strip(),
            'delivery_status': str(tracking.get('delivery_status', '')).strip(),
            'delivery_at': str(tracking.get('delivery_at', '')).strip(),
        }
    if client_details:
        payload['client'] = {
            'name': str(client_details.get('name', '')).strip(),
            'phone': str(client_details.get('phone', '')).strip(),
            'email': str(client_details.get('email', '')).strip(),
        }
    if draft_state:
        payload['draft_state'] = draft_state
    return DOCUMENT_PREFIX + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def unpack_document(value, validity_days=14):
    if value and value.startswith(DOCUMENT_PREFIX):
        try:
            payload = json.loads(value[len(DOCUMENT_PREFIX):])
            if isinstance(payload, dict) and isinstance(payload.get('terms'), list):
                payload.setdefault('remarks', '')
                payload.setdefault('tracking', {})
                payload.setdefault('client', {})
                payload.setdefault('draft_state', {})
                return payload
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    terms = default_terms(validity_days)
    if value:
        terms[0]['body'] = value
    return {'terms': terms, 'remarks': '', 'tracking': {}, 'client': {}, 'draft_state': {}}


def quotation_tracking(value, validity_days=14):
    tracking = unpack_document(value, validity_days).get('tracking') or {}
    return {
        'submitted_at': str(tracking.get('submitted_at', '')).strip(),
        'client_remarks': str(tracking.get('client_remarks', '')).strip(),
        'client_status': str(tracking.get('client_status', 'under_review')).strip() or 'under_review',
        'submitted_to': str(tracking.get('submitted_to', '')).strip(),
        'submitted_cc': str(tracking.get('submitted_cc', '')).strip(),
        'submitted_subject': str(tracking.get('submitted_subject', '')).strip(),
        'delivery_status': str(tracking.get('delivery_status', '')).strip(),
        'delivery_at': str(tracking.get('delivery_at', '')).strip(),
    }


def quotation_discount(value, validity_days=14):
    """Return the saved quotation discount amount from the document payload."""
    raw = (unpack_document(value, validity_days).get('draft_state') or {}).get('discount', '0')
    try:
        discount = Decimal(str(raw or '0'))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')
    return max(Decimal('0.00'), discount).quantize(Decimal('0.01'))


def update_quotation_tracking(value, validity_days=14, **updates):
    document = unpack_document(value, validity_days)
    tracking = quotation_tracking(value, validity_days)
    tracking.update(updates)
    return pack_document(
        document['terms'], document.get('remarks', ''), tracking,
        client_details=document.get('client'),
        draft_state=document.get('draft_state'),
    )


def quotation_internal_review(value, validity_days=14):
    """Return the internal approval stage that asked the estimator to correct a quote."""
    stage = (unpack_document(value, validity_days).get('draft_state') or {}).get(
        'internal_revision_stage', ''
    )
    return stage if stage in ('manager', 'accountant') else ''


def update_quotation_internal_review(value, validity_days=14, stage=''):
    """Record internal rework without creating or changing client-submittal tracking."""
    document = unpack_document(value, validity_days)
    draft_state = dict(document.get('draft_state') or {})
    if stage in ('manager', 'accountant'):
        draft_state['internal_revision_stage'] = stage
    else:
        draft_state.pop('internal_revision_stage', None)
    # Keep tracking absent until the quotation has actually been submitted to the client.
    tracking = document.get('tracking') or None
    return pack_document(
        document['terms'], document.get('remarks', ''), tracking,
        client_details=document.get('client'), draft_state=draft_state,
    )


def line_kind(line):
    return {
        SECTION_UNIT: 'section',
        SUBHEADING_UNIT: 'subheading',
        NOTE_UNIT: 'note',
    }.get(line.unit, 'item')


def rich_text_to_html(value):
    """Render the editor's deliberately small **bold** markup safely."""
    escaped = escape(value or '')
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped, flags=re.DOTALL)
    return escaped.replace('\r\n', '<br/>').replace('\n', '<br/>')


def plain_rich_text(value):
    return re.sub(r'\*\*(.+?)\*\*', r'\1', value or '', flags=re.DOTALL)


def presentation_rows(lines):
    """Insert section subtotals without persisting derived values.

    Subheadings are descriptive breaks inside a section.  They deliberately do
    not produce financial subtotal rows, matching the approved quotation sample.
    """
    rows = []
    section = None
    section_total = 0
    section_direct_total = None
    lump_sum_group = None
    next_group_id = 0

    def close_section():
        nonlocal section, section_total, section_direct_total
        effective_total = section_direct_total if section_direct_total is not None else section_total
        if section is not None and effective_total:
            rows.append({
                'kind': 'section_total', 'code': section.item_code,
                'label': section.description, 'amount': effective_total,
            })
        section = None
        section_total = 0
        section_direct_total = None

    for line in lines:
        kind = line_kind(line)
        if kind == 'section':
            close_section()
            section = line
            section_direct_total = line.amount if line.amount > 0 else None
            lump_sum_group = None
            if line.amount:
                next_group_id += 1
                lump_sum_group = (next_group_id, line.amount)
            rows.append({'kind': kind, 'line': line, 'lump_sum_group_start': lump_sum_group})
        elif kind == 'subheading':
            lump_sum_group = None
            if line.amount:
                next_group_id += 1
                lump_sum_group = (next_group_id, line.amount)
            rows.append({'kind': kind, 'line': line, 'lump_sum_group_start': lump_sum_group})
            if section_direct_total is None:
                section_total += line.amount
        else:
            entry = {'kind': kind, 'line': line}
            if kind == 'item' and lump_sum_group:
                entry['lump_sum_group'] = lump_sum_group
            rows.append(entry)
            if kind == 'item' and section_direct_total is None:
                section_total += line.amount
            elif kind == 'note':
                lump_sum_group = None
    close_section()
    return rows
