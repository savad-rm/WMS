from functools import wraps
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime, time
import re

from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.db.models import Count, Max, Prefetch, Q
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from .models import (
    costing, enquiry, enquiry_attachment, enquiry_comment, login,
    project_document, quotation, quotation_line, staff, workflow_notification,
)
from .middleware import role_is_allowed
from .deadline_notifications import ensure_quotation_deadline_notifications
from .quotation_exports import (
    build_quotation_excel, build_quotation_pdf, quotation_amount_words,
)
from .quotation_document import (
    DEFAULT_CLOSING_TEXT, DEFAULT_INTRODUCTION, NOTE_UNIT, SECTION_UNIT,
    SUBHEADING_UNIT, default_terms, line_kind, pack_document, presentation_rows,
    quotation_internal_review, quotation_tracking, unpack_document,
    update_quotation_internal_review, update_quotation_tracking,
)
from .quotation_numbers import assign_quotation_reference
from .quotation_activity import publish_client_response, publish_quotation_message
from .quotation_email import QuotationDeliveryError, send_quotation_to_client
from .quotation_email import quotation_email_content


WORKFLOW_ROLES = {
    'Admin', 'Marketing Executive', 'Marketing Manager', 'Estimator',
    'Document Controller', 'Project Manager', 'Project Engineer',
    'Operation Manager', 'Accountant',
}
UPLOAD_EXTENSIONS = ('xlsx', 'xls', 'jpg', 'jpeg', 'png', 'pdf', 'dwg', 'dxf', 'doc', 'docx')
MAX_UPLOAD_SIZE = 20 * 1024 * 1024

DEFAULT_TERM_MAP = {item['title']: item['body'] for item in default_terms()}
CLIENT_RESPONSE_STATUSES = {
    'under_review': 'Under Review',
    'under_revision': 'Under Revision',
    'approved': 'Approved',
    'rejected': 'Rejected',
}
QUOTATION_UNITS = ('M2', 'Nos.', 'ITEM', 'LM', 'RM', 'Sets')
QUOTATION_COMMENT_ROLES = (
    'Marketing Executive', 'Marketing Manager', 'Estimator', 'Accountant',
)
ENQUIRY_COMMENT_ROLES = QUOTATION_COMMENT_ROLES


def _current_login(request):
    login_id = request.session.get('lid')
    return login.objects.filter(pk=login_id).first() if login_id else None


def _current_staff(request):
    staff_id = request.session.get('sid')
    if staff_id:
        return staff.objects.filter(pk=staff_id).select_related('LOGIN').first()
    account = _current_login(request)
    return staff.objects.filter(LOGIN=account).select_related('LOGIN').first() if account else None


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            account = _current_login(request)
            if not account:
                messages.error(request, 'Please sign in to continue.')
                return redirect('login')
            if not role_is_allowed(account.usertype, allowed_roles):
                return HttpResponseForbidden('You do not have permission to perform this action.')
            request.workflow_account = account
            request.workflow_staff = _current_staff(request)
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def _validate_upload(upload):
    FileExtensionValidator(UPLOAD_EXTENSIONS)(upload)
    if upload.size > MAX_UPLOAD_SIZE:
        raise ValidationError('Each file must be 20 MB or smaller.')


def _non_negative_decimal(request, field, label):
    try:
        value = Decimal(request.POST.get(field) or '0')
    except InvalidOperation as exc:
        raise ValidationError(f'{label} must be a valid number.') from exc
    if not value.is_finite():
        raise ValidationError(f'{label} must be a finite number.')
    if value < 0:
        raise ValidationError(f'{label} cannot be negative.')
    return value


def _render(request, template, context=None, status=200):
    ensure_quotation_deadline_notifications()
    context = context or {}
    context.update({
        'current_role': request.workflow_account.usertype,
        'current_account': request.workflow_account,
        'current_staff': getattr(request, 'workflow_staff', None),
        'workflow_roles': WORKFLOW_ROLES,
        'workflow_notifications': workflow_notification.objects.filter(
            recipient=request.workflow_account,
        ).select_related('ENQUIRY')[:6],
        'workflow_unread_count': workflow_notification.objects.filter(
            recipient=request.workflow_account, read_at__isnull=True,
        ).count(),
    })
    return render(request, template, context, status=status)


def _can_access_enquiry(request, record):
    role = request.workflow_account.usertype
    if role == 'Marketing Executive':
        return record.created_by_id == request.workflow_account.id
    if role == 'Estimator':
        return record.assigned_to_id == getattr(request.workflow_staff, 'id', None)
    return True


def _can_view_quotation(request, quote):
    if not _can_access_enquiry(request, quote.ENQUIRY):
        return False
    if quote.status != 'draft':
        if (
            _workflow_role(request.workflow_account.usertype) == 'Marketing Executive'
            and _is_marketing_restricted_quotation(quote)
        ):
            return False
        return True
    return (
        _workflow_role(request.workflow_account.usertype) == 'Estimator'
        and quote.created_by_id == getattr(request.workflow_staff, 'id', None)
    )


def _is_marketing_restricted_quotation(quote):
    """Marketing can track internal work, but cannot open it before final approval."""
    return quote.status in ('manager_review', 'accountant_review') or (
        quote.status == 'under_revision' and not quote.accountant_approved_at
    )


def _is_current_quotation(quote):
    return not quotation.objects.filter(
        ENQUIRY_id=quote.ENQUIRY_id, version__gt=quote.version,
    ).exists()


def _workflow_role(role):
    if role in ('Project Engineer', 'Operation Manager'):
        return 'Project Manager'
    return role


def _quotation_discussion_url(quote):
    return reverse('workflow_quotation_discussion', args=(quote.pk,))


def _quotation_comment_prefix(quote):
    return f'[QID:{quote.pk}] '


def _quotation_comment_threads(quote, viewer=None):
    prefixes = (_quotation_comment_prefix(quote), f'[{quote.display_number}] ')
    comments = list(quote.ENQUIRY.comments.filter(
        Q(comment__startswith=prefixes[0]) | Q(comment__startswith=prefixes[1]),
    ).select_related('author'))
    roots = []
    by_id = {}
    for item in comments:
        value = item.comment
        for prefix in prefixes:
            if value.startswith(prefix):
                value = value[len(prefix):]
                break
        reply_match = re.match(r'^\[REPLY:(\d+)\]\s*(.*)$', value, re.DOTALL)
        value = reply_match.group(2) if reply_match else value
        recipient_match = re.match(r'^\[TO:([0-9,]+)\]\s*(.*)$', value, re.DOTALL)
        item.recipient_ids = {
            int(value) for value in recipient_match.group(1).split(',') if value.isdigit()
        } if recipient_match else set()
        item.display_comment = recipient_match.group(2) if recipient_match else value
        item.is_client_response = item.display_comment.startswith('Client response updated to ')
        item.replies = []
        marketing_private = (
            viewer is not None and viewer.usertype == 'Marketing Executive'
            and _is_marketing_restricted_quotation(quote)
        )
        if marketing_private and item.author_id != viewer.id and viewer.id not in item.recipient_ids:
            continue
        if reply_match and int(reply_match.group(1)) in by_id:
            by_id[int(reply_match.group(1))].replies.append(item)
        else:
            roots.append(item)
            by_id[item.pk] = item
    return roots


def _quotation_discussion_recipient_ids(quote):
    recipient_ids = {quote.ENQUIRY.created_by_id}
    if quote.ENQUIRY.assigned_to_id and quote.ENQUIRY.assigned_to.LOGIN_id:
        recipient_ids.add(quote.ENQUIRY.assigned_to.LOGIN_id)
    recipient_ids.update(login.objects.filter(
        usertype__in=('Marketing Manager', 'Accountant'),
    ).values_list('id', flat=True))
    return recipient_ids


def _enquiry_discussion_url(record):
    return reverse('workflow_enquiry_discussion', args=(record.pk,))


def _enquiry_comment_prefix(record):
    return f'[ENQ:{record.pk}] '


def _enquiry_comment_threads(record):
    prefix = _enquiry_comment_prefix(record)
    comments = list(record.comments.filter(
        Q(comment__startswith=prefix)
        | (~Q(comment__startswith='[QID:') & ~Q(comment__startswith='[QTN/'))
    ).select_related('author').order_by('created_at', 'id'))
    roots, by_id = [], {}
    for item in comments:
        value = item.comment[len(prefix):] if item.comment.startswith(prefix) else item.comment
        reply_match = re.match(r'^\[REPLY:(\d+)\]\s*(.*)$', value, re.DOTALL)
        item.display_comment = reply_match.group(2) if reply_match else value
        item.replies = []
        parent_id = int(reply_match.group(1)) if reply_match else None
        if parent_id in by_id:
            by_id[parent_id].replies.append(item)
        else:
            roots.append(item)
        by_id[item.pk] = item
    return roots


def _enquiry_discussion_recipient_ids(record):
    recipient_ids = {record.created_by_id}
    if record.assigned_to_id and record.assigned_to.LOGIN_id:
        recipient_ids.add(record.assigned_to.LOGIN_id)
    recipient_ids.update(login.objects.filter(
        usertype__in=('Marketing Manager', 'Accountant'),
    ).values_list('id', flat=True))
    return recipient_ids


def _roman_number(number):
    values = ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'),
              (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'),
              (5, 'V'), (4, 'IV'), (1, 'I'))
    result = []
    for value, symbol in values:
        while number >= value:
            result.append(symbol)
            number -= value
    return ''.join(result)


def _detail_record(enquiry_id):
    return get_object_or_404(
        enquiry.objects.select_related('created_by', 'assigned_to', 'PROJECT').prefetch_related(
            'attachments', 'comments__author', 'project_documents__verified_by',
            Prefetch('quotations', queryset=quotation.objects.select_related(
                'created_by', 'manager_approved_by', 'accountant_approved_by',
                'costing', 'costing__approved_by',
            ).prefetch_related('lines')),
        ), pk=enquiry_id,
    )


def _detail_context(request, record, extra=None):
    role = _workflow_role(request.workflow_account.usertype)
    is_awarded = (
        record.status == 'awarded'
        or record.quotations.filter(status='accepted').exists()
    )
    revision_source = None
    editing_quote = None
    revision_id = request.GET.get('revise', '').strip()
    if role == 'Estimator' and revision_id and not is_awarded:
        revision_source = record.quotations.filter(
            pk=revision_id, status='under_revision',
        ).first()
    edit_id = request.GET.get('edit', '').strip()
    if role == 'Estimator' and edit_id:
        editing_quote = record.quotations.filter(
            pk=edit_id, status='draft', created_by=request.workflow_staff,
        ).first()
        if editing_quote is None:
            returned_quote = record.quotations.filter(
                pk=edit_id, status='under_revision', created_by=request.workflow_staff,
            ).first()
            if returned_quote and quotation_internal_review(
                returned_quote.details, returned_quote.validity_days,
            ):
                editing_quote = returned_quote
    if (extra or {}).get('editing_quote') and not is_awarded:
        editing_quote = extra['editing_quote']
    if (extra or {}).get('revision_source') and not is_awarded:
        revision_source = extra['revision_source']
    may_create_initial = role == 'Estimator' and not record.quotations.exists()
    can_quote = may_create_initial or revision_source is not None or editing_quote is not None
    importable_quotations = quotation.objects.none()
    imported_quote = None
    if role == 'Estimator' and can_quote:
        importable_quotations = quotation.objects.filter(
            status__in=('approved', 'submitted', 'accepted', 'rejected'),
            lines__isnull=False,
        ).exclude(ENQUIRY=record).select_related('ENQUIRY').distinct().order_by(
            '-issue_date', '-created_at',
        )[:150]
        import_id = request.GET.get('import_quote', '').strip()
        if import_id:
            imported_quote = next(
                (item for item in importable_quotations if str(item.pk) == import_id), None,
            )
    form_source = imported_quote or editing_quote or revision_source
    marketing_executive_name = staff.objects.filter(
        LOGIN_id=record.created_by_id,
    ).values_list('name', flat=True).first() or record.created_by.username
    quotation_prefixes = tuple(
        f'[{item.display_number}]' for item in record.quotations.all()
    )
    enquiry_comments = [
        item for item in record.comments.all()
        if not item.comment.startswith('[QID:')
        and not any(item.comment.startswith(prefix) for prefix in quotation_prefixes)
    ]
    context = {
        'enquiry': record,
        'marketing_executive_name': marketing_executive_name,
        'enquiry_comments': enquiry_comments,
        'enquiry_unread_comment_count': workflow_notification.objects.filter(
            recipient=request.workflow_account, event='enquiry_comment',
            link=_enquiry_discussion_url(record), read_at__isnull=True,
        ).count(),
        'estimators': staff.objects.filter(designation='Estimator').only('id', 'name'),
        'can_assign': role in ('Marketing Manager', 'Project Manager'),
        'can_quote': can_quote,
        'visible_quotations': [
            quote for quote in record.quotations.all()
            if quote.status != 'draft'
            or (role == 'Estimator' and quote.created_by_id == getattr(request.workflow_staff, 'id', None))
        ],
        # This flag now only controls editing an estimator-owned draft. New
        # revisions are started from the quotation view after Under Revision.
        'can_start_revision': role == 'Estimator' and not is_awarded,
        'revision_source': revision_source,
        'editing_quote': editing_quote,
        'imported_quote': imported_quote,
        'importable_quotations': importable_quotations,
        'can_manager_approve': role == 'Marketing Manager',
        'can_accountant_approve': role == 'Accountant',
        'can_approve_costing': role == 'Project Manager',
        'can_submit': role in ('Document Controller', 'Marketing Executive', 'Marketing Manager'),
        'can_award': role == 'Marketing Executive',
        'can_collect': role == 'Marketing Executive',
        'can_verify': role == 'Document Controller',
        'default_introduction': DEFAULT_INTRODUCTION,
        'default_closing_text': DEFAULT_CLOSING_TEXT,
        'quotation_units': QUOTATION_UNITS,
        'quotation_issue_date': timezone.localdate().isoformat(),
    }
    if form_source and not (extra or {}).get('quote_form'):
        document = unpack_document(form_source.details, form_source.validity_days)
        draft_state = document.get('draft_state') if editing_quote else {}
        document_client = document.get('client') or {}
        quote_costing = getattr(form_source, 'costing', None)
        saved_form = draft_state.get('form', {}) if isinstance(draft_state, dict) else {}
        saved_rows = draft_state.get('rows', []) if isinstance(draft_state, dict) else []
        saved_terms = draft_state.get('terms', []) if isinstance(draft_state, dict) else []
        quote_form = {
            'issue_date': (
                timezone.localdate().isoformat() if imported_quote
                else form_source.issue_date.isoformat()
            ),
            'subject': (
                f'Quotation for {record.title}' if imported_quote else form_source.subject
            ),
            'client_address': (
                'Doha - State of Qatar' if imported_quote else form_source.client_address
            ),
            'client_name': (
                record.client_name if imported_quote
                else document_client.get('name', record.client_name)
            ),
            'client_phone': (
                record.client_phone if imported_quote
                else document_client.get('phone', record.client_phone)
            ),
            'client_email': (
                record.client_email if imported_quote
                else document_client.get('email', record.client_email)
            ),
            'introduction': form_source.introduction,
            'validity_days': form_source.validity_days,
            'project_duration': form_source.project_duration,
            'closing_text': form_source.closing_text,
            'signatory_name': (
                request.workflow_staff.name if imported_quote else form_source.signatory_name
            ),
            'signatory_title': (
                request.workflow_staff.designation if imported_quote else form_source.signatory_title
            ),
            'signatory_phone': (
                request.workflow_staff.phone if imported_quote else form_source.signatory_phone
            ),
            'remarks': document.get('remarks', ''),
            'material_cost': quote_costing.material_cost if quote_costing else '',
            'labour_cost': quote_costing.labour_cost if quote_costing else '',
            'other_cost': quote_costing.other_cost if quote_costing else '',
            'costing_notes': quote_costing.notes if quote_costing else '',
        }
        if saved_form and not imported_quote:
            quote_form.update(saved_form)
        context.update({
            'quote_form': quote_form,
            'quote_terms': saved_terms or document['terms'],
            'quote_rows': saved_rows or [
                {
                    'row_type': line_kind(line), 'item_code': line.item_code,
                    'description': line.description,
                    'unit': '' if line_kind(line) != 'item' else line.unit,
                    'quantity': '' if line_kind(line) != 'item' or not line.quantity else line.quantity,
                    'unit_rate': '' if line_kind(line) != 'item' or not line.unit_rate else line.unit_rate,
                    'amount': line.amount if line_kind(line) != 'item' and line.amount else '',
                }
                for line in form_source.lines.all()
            ],
        })
    elif may_create_initial and not (extra or {}).get('quote_terms'):
        context['quote_terms'] = default_terms()
        context['quote_form'] = {
            'issue_date': timezone.localdate().isoformat(),
            'client_name': record.client_name,
            'client_phone': record.client_phone,
            'client_email': record.client_email,
            'client_address': 'Doha - State of Qatar',
        }
    context.update(extra or {})
    return context


@role_required(*WORKFLOW_ROLES)
def dashboard(request):
    role = _workflow_role(request.workflow_account.usertype)
    records = enquiry.objects.select_related('created_by', 'assigned_to', 'PROJECT').prefetch_related(
        Prefetch(
            'quotations',
            queryset=quotation.objects.exclude(status='draft').only('id', 'ENQUIRY_id'),
        )
    )
    if role == 'Marketing Executive':
        records = records.filter(created_by=request.workflow_account)
    elif role == 'Estimator':
        records = records.filter(assigned_to=request.workflow_staff)
    accessible_records = records
    dashboard_view = request.GET.get('view', '').strip()
    dashboard_views = {
        'open': {
            'label': 'Open enquiries awaiting assignment',
            'target': 'enquiries',
        },
        'assigned': {
            'label': 'Enquiries assigned to estimators',
            'target': 'enquiries',
        },
        'awaiting_approval': {
            'label': 'Quotations awaiting internal approval',
            'target': 'quotations',
        },
        'awarded': {
            'label': 'Awarded quotations',
            'target': 'quotations',
        },
    }
    if dashboard_view not in dashboard_views:
        dashboard_view = ''

    enquiry_query = request.GET.get('enquiry_q', '').strip()
    if enquiry_query:
        records = records.filter(
            Q(title__icontains=enquiry_query)
            | Q(client_name__icontains=enquiry_query)
            | Q(client_email__icontains=enquiry_query)
            | Q(client_phone__icontains=enquiry_query)
            | Q(assigned_to__name__icontains=enquiry_query)
        )
    if dashboard_view == 'open':
        records = records.filter(status='open')
    elif dashboard_view == 'assigned':
        records = records.filter(status='assigned')
    enquiry_sort = request.GET.get('enquiry_sort', '-date')
    enquiry_ordering = {
        'date': ('created_at',), '-date': ('-created_at',),
        'client': ('client_name', 'created_at'), '-client': ('-client_name', '-created_at'),
        'deadline': ('quotation_deadline', 'created_at'),
        '-deadline': ('-quotation_deadline', '-created_at'),
    }.get(enquiry_sort, ('-created_at',))
    records = records.order_by(*enquiry_ordering)

    quote_records = quotation.objects.filter(
        ENQUIRY__in=accessible_records,
    ).exclude(status='draft').select_related(
        'ENQUIRY', 'ENQUIRY__created_by', 'created_by',
    )
    quotation_query = request.GET.get('quotation_q', '').strip()
    if quotation_query:
        quote_records = quote_records.filter(
            Q(quotation_number__icontains=quotation_query)
            | Q(ENQUIRY__client_name__icontains=quotation_query)
            | Q(ENQUIRY__title__icontains=quotation_query)
            | Q(ENQUIRY__created_by__username__icontains=quotation_query)
            | Q(created_by__name__icontains=quotation_query)
        )
    if dashboard_view == 'awaiting_approval':
        quote_records = quote_records.filter(
            status__in=('manager_review', 'accountant_review'),
        )
    elif dashboard_view == 'awarded':
        quote_records = quote_records.filter(status='accepted')
    quotation_sort = request.GET.get('quotation_sort', '-date')
    quotation_ordering = {
        'date': ('issue_date', 'created_at'), '-date': ('-issue_date', '-created_at'),
        'number': ('quotation_number',), '-number': ('-quotation_number',),
        'client': ('ENQUIRY__client_name', 'issue_date'),
        '-client': ('-ENQUIRY__client_name', '-issue_date'),
    }.get(quotation_sort, ('-issue_date', '-created_at'))
    # The register represents the current shared quotation for each enquiry.
    # Historical client revisions remain available from that quotation's version selector.
    latest_quote_ids = {}
    for quote_id, enquiry_id in quote_records.order_by('ENQUIRY_id', '-version', '-id').values_list('id', 'ENQUIRY_id'):
        latest_quote_ids.setdefault(enquiry_id, quote_id)
    quote_records = list(quote_records.filter(pk__in=latest_quote_ids.values()).order_by(*quotation_ordering)[:100])
    enquiry_records = list(records[:100])
    creator_ids = {
        item.created_by_id for item in enquiry_records
    } | {
        quote.ENQUIRY.created_by_id for quote in quote_records
    }
    marketing_names = dict(staff.objects.filter(
        LOGIN_id__in=creator_ids
    ).values_list('LOGIN_id', 'name'))
    unread_notices = workflow_notification.objects.filter(
        recipient=request.workflow_account, read_at__isnull=True,
        ENQUIRY__in=accessible_records,
    )
    unread_by_enquiry = dict(unread_notices.filter(
        event='enquiry_comment',
    ).values_list('ENQUIRY_id').annotate(total=Count('id')))
    unread_by_link = dict(unread_notices.filter(
        event='quotation_comment',
    ).values_list('link').annotate(total=Count('id')))
    for item in enquiry_records:
        item.marketing_executive_name = marketing_names.get(
            item.created_by_id, item.created_by.username,
        )
        item.unread_comment_count = unread_by_enquiry.get(item.pk, 0)
    for quote in quote_records:
        tracking = quotation_tracking(quote.details, quote.validity_days)
        quote.internal_revision_stage = quotation_internal_review(
            quote.details, quote.validity_days,
        )
        quote.client_status = tracking['client_status'] if tracking['client_status'] in CLIENT_RESPONSE_STATUSES else 'under_review'
        quote.client_status_label = CLIENT_RESPONSE_STATUSES[quote.client_status]
        quote.submitted_at_display = parse_datetime(tracking['submitted_at']) if tracking['submitted_at'] else None
        quote.client_response_editable = quote.status in ('submitted', 'rejected') or (
            quote.status == 'under_revision' and not quote.internal_revision_stage
        )
        quote.restricted_for_marketing = (
            role == 'Marketing Executive' and _is_marketing_restricted_quotation(quote)
        )
        quote.marketing_executive_name = marketing_names.get(
            quote.ENQUIRY.created_by_id, quote.ENQUIRY.created_by.username,
        )
        quote.unread_comment_count = unread_by_link.get(_quotation_discussion_url(quote), 0)

    return _render(request, 'Workflow/dashboard.html', {
        'enquiries': enquiry_records,
        'quotations': quote_records,
        'can_add': role in ('Marketing Executive', 'Marketing Manager'),
        'can_manage_client_response': role in ('Admin', 'Marketing Executive', 'Marketing Manager'),
        'query': enquiry_query,
        'enquiry_query': enquiry_query,
        'quotation_query': quotation_query,
        'enquiry_sort': enquiry_sort,
        'quotation_sort': quotation_sort,
        'dashboard_view': dashboard_view,
        'dashboard_view_label': dashboard_views.get(dashboard_view, {}).get('label', ''),
        'dashboard_view_target': dashboard_views.get(dashboard_view, {}).get('target', ''),
        'client_response_statuses': CLIENT_RESPONSE_STATUSES,
        'summary': {
            'open': accessible_records.filter(status='open').count(),
            'assigned': accessible_records.filter(status='assigned').count(),
            'awaiting_approval': quotation.objects.filter(
                ENQUIRY__in=accessible_records,
                status__in=('manager_review', 'accountant_review'),
            ).count(),
            'awarded': accessible_records.filter(status='awarded').count(),
        },
    })


@role_required(*WORKFLOW_ROLES)
def profile(request):
    return _render(request, 'Workflow/profile.html')


@role_required(*WORKFLOW_ROLES)
def change_password(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirmation = request.POST.get('confirm_password', '')
        if not check_password(current_password, request.workflow_account.password):
            messages.error(request, 'The current password is incorrect.')
        elif len(new_password) < 8:
            messages.error(request, 'The new password must contain at least 8 characters.')
        elif new_password != confirmation:
            messages.error(request, 'The new password and confirmation do not match.')
        else:
            request.workflow_account.password = make_password(new_password)
            request.workflow_account.api_token_version += 1
            request.workflow_account.save(update_fields=('password', 'api_token_version'))
            messages.success(request, 'Password changed successfully.')
            return redirect('workflow_profile')
    return _render(request, 'Workflow/change_password.html')


@require_POST
@role_required(*WORKFLOW_ROLES)
def logout(request):
    request.session.flush()
    return redirect('login')


@role_required('Marketing Executive', 'Marketing Manager')
def add_enquiry(request):
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        def enquiry_error(message):
            if is_ajax:
                return JsonResponse({'ok': False, 'error': message}, status=400)
            messages.error(request, message)
            return _render(request, 'Workflow/enquiry_form.html', {
                'form_data': request.POST,
            }, status=400)

        title = request.POST.get('title', '').strip()
        client_name = request.POST.get('client_name', '').strip()
        if not title or not client_name:
            return enquiry_error('Enquiry title and client name are required.')
        deadline_value = request.POST.get('quotation_deadline', '').strip()
        deadline_date = parse_date(deadline_value) if deadline_value else None
        legacy_deadline = parse_datetime(deadline_value) if deadline_value and not deadline_date else None
        if not deadline_date and not legacy_deadline:
            return enquiry_error('Enter the quotation submission deadline.')
        deadline = legacy_deadline or timezone.make_aware(
            datetime.combine(deadline_date, time.max), timezone.get_current_timezone(),
        )
        if timezone.is_naive(deadline):
            deadline = timezone.make_aware(deadline, timezone.get_current_timezone())
        if deadline <= timezone.now():
            return enquiry_error('The quotation deadline must be in the future.')
        uploads = request.FILES.getlist('files')
        try:
            for upload in uploads:
                _validate_upload(upload)
        except ValidationError as exc:
            return enquiry_error(exc.messages[0])
        else:
            with transaction.atomic():
                record = enquiry.objects.create(
                    title=title,
                    client_name=client_name,
                    client_email=request.POST.get('client_email', '').strip().lower(),
                    client_phone=request.POST.get('client_phone', '').strip(),
                    description=request.POST.get('description', '').strip(),
                    quotation_deadline=deadline,
                    created_by=request.workflow_account,
                )
                for upload in uploads:
                    enquiry_attachment.objects.create(
                        ENQUIRY=record, file=upload, original_name=Path(upload.name).name
                    )
            if is_ajax:
                return JsonResponse({
                    'ok': True,
                    'redirect_url': reverse('workflow_detail', args=(record.pk,)),
                })
            messages.success(request, 'Project enquiry added successfully.')
            return redirect('workflow_detail', enquiry_id=record.pk)
    return _render(request, 'Workflow/enquiry_form.html')


@role_required(*WORKFLOW_ROLES)
def detail(request, enquiry_id):
    record = _detail_record(enquiry_id)
    if not _can_access_enquiry(request, record):
        return HttpResponseForbidden('You do not have permission to view this enquiry.')
    return _render(request, 'Workflow/enquiry_detail.html', _detail_context(request, record))


@require_POST
@role_required(*WORKFLOW_ROLES)
def add_comment(request, enquiry_id):
    record = get_object_or_404(enquiry, pk=enquiry_id)
    if not _can_access_enquiry(request, record):
        return HttpResponseForbidden('You do not have permission to comment on this enquiry.')
    value = request.POST.get('comment', '').strip()
    if not value:
        messages.error(request, 'Enter a message before sending.')
        return redirect('workflow_enquiry_discussion', enquiry_id=record.pk)
    parent_id = request.POST.get('parent_id', '').strip()
    parent_prefix = ''
    if parent_id:
        valid_parent_ids = {item.pk for item in record.comments.filter(
            Q(comment__startswith=_enquiry_comment_prefix(record))
            | (~Q(comment__startswith='[QID:') & ~Q(comment__startswith='[QTN/'))
        )}
        if not parent_id.isdigit() or int(parent_id) not in valid_parent_ids:
            messages.error(request, 'The message you are replying to is no longer available.')
            return redirect('workflow_enquiry_discussion', enquiry_id=record.pk)
        parent_prefix = f'[REPLY:{parent_id}] '
    item = enquiry_comment.objects.create(
        ENQUIRY=record, author=request.workflow_account,
        comment=f'{_enquiry_comment_prefix(record)}{parent_prefix}{value}',
    )
    discussion_url = _enquiry_discussion_url(record)
    for recipient_id in _enquiry_discussion_recipient_ids(record) - {request.workflow_account.id}:
        workflow_notification.objects.get_or_create(
            dedupe_key=f'enquiry-comment:{item.pk}:{recipient_id}',
            defaults={
                'recipient_id': recipient_id, 'ENQUIRY': record,
                'event': 'enquiry_comment', 'level': 'info',
                'message': f'New discussion message on enquiry {record.title}.',
                'link': discussion_url,
            },
        )
    messages.success(request, 'Message added to the enquiry discussion.')
    return redirect('workflow_enquiry_discussion', enquiry_id=record.pk)


@role_required(*ENQUIRY_COMMENT_ROLES)
def enquiry_discussion(request, enquiry_id):
    record = _detail_record(enquiry_id)
    if not _can_access_enquiry(request, record):
        return HttpResponseForbidden('You do not have permission to view this discussion.')
    workflow_notification.objects.filter(
        recipient=request.workflow_account, event='enquiry_comment',
        link=_enquiry_discussion_url(record), read_at__isnull=True,
    ).update(read_at=timezone.now())
    return _render(request, 'Workflow/enquiry_discussion.html', {
        'enquiry': record,
        'discussion_threads': _enquiry_comment_threads(record),
    })


@require_POST
@role_required('Marketing Manager', 'Project Manager')
def assign_estimator(request, enquiry_id):
    record = get_object_or_404(enquiry, pk=enquiry_id)
    estimator = get_object_or_404(staff, pk=request.POST.get('estimator'), designation='Estimator')
    record.assigned_to = estimator
    record.status = 'assigned'
    record.save(update_fields=('assigned_to', 'status', 'updated_at'))
    # Assignment can happen after a discussion has already started. Surface the
    # discussion to the estimator immediately instead of waiting for a new post.
    if estimator.LOGIN_id:
        workflow_notification.objects.update_or_create(
            dedupe_key=f'enquiry-assignment:{record.pk}:{estimator.LOGIN_id}',
            defaults={
                'recipient_id': estimator.LOGIN_id,
                'ENQUIRY': record,
                'event': 'enquiry_comment',
                'level': 'info',
                'message': f'You were assigned to {record.title}. Open the enquiry discussion.',
                'link': _enquiry_discussion_url(record),
                'read_at': None,
            },
        )
    messages.success(request, f'Enquiry assigned to {estimator.name}.')
    return redirect('workflow_detail', enquiry_id=enquiry_id)


def _autosave_decimal(value):
    try:
        number = Decimal(str(value).strip() or '0')
    except InvalidOperation:
        return Decimal('0')
    return number if number.is_finite() and number >= 0 else Decimal('0')


@require_POST
@role_required('Estimator')
def autosave_quotation(request, enquiry_id):
    """Persist an in-progress quotation without requiring it to be valid yet."""
    record = get_object_or_404(
        enquiry.objects.prefetch_related('quotations__lines'),
        pk=enquiry_id, assigned_to=request.workflow_staff,
    )
    if record.status == 'awarded' or record.quotations.filter(status='accepted').exists():
        return JsonResponse({
            'ok': False,
            'error': 'An awarded quotation cannot be revised.',
        }, status=409)
    row_fields = {
        'row_type': request.POST.getlist('row_type'),
        'item_code': request.POST.getlist('item_code'),
        'description': request.POST.getlist('line_description'),
        'unit': request.POST.getlist('unit'),
        'quantity': request.POST.getlist('quantity'),
        'unit_rate': request.POST.getlist('unit_rate'),
        'amount': request.POST.getlist('line_amount'),
    }
    row_count = max((len(values) for values in row_fields.values()), default=0)
    draft_rows = [
        {key: values[index] if index < len(values) else '' for key, values in row_fields.items()}
        for index in range(row_count)
    ]
    term_titles = request.POST.getlist('term_title')
    term_bodies = request.POST.getlist('term_body')
    draft_terms = [
        {
            'title': term_titles[index] if index < len(term_titles) else '',
            'body': term_bodies[index] if index < len(term_bodies) else '',
        }
        for index in range(max(len(term_titles), len(term_bodies)))
    ] or default_terms()
    client = {
        'name': request.POST.get('quotation_client_name', '').strip() or record.client_name,
        'phone': (
            request.POST.get('quotation_client_phone', '').strip()
            if 'quotation_client_phone' in request.POST else record.client_phone
        ),
        'email': (
            request.POST.get('quotation_client_email', '').strip().lower()
            if 'quotation_client_email' in request.POST else record.client_email
        ),
    }
    draft_form_names = (
        'issue_date', 'subject', 'client_address', 'introduction', 'validity_days',
        'project_duration', 'closing_text', 'signatory_name', 'signatory_title',
        'signatory_phone', 'remarks', 'material_cost', 'labour_cost', 'other_cost',
        'costing_notes', 'quotation_client_name', 'quotation_client_phone',
        'quotation_client_email',
    )
    draft_form = {name: request.POST.get(name, '') for name in draft_form_names}
    details = pack_document(
        draft_terms, request.POST.get('remarks', ''), client_details=client,
        draft_state={'form': draft_form, 'rows': draft_rows, 'terms': draft_terms},
    )

    parsed_lines = []
    section_number = subheading_number = item_number = 0
    for position, row in enumerate(draft_rows, start=1):
        kind = row['row_type'] if row['row_type'] in ('item', 'section', 'subheading', 'note') else 'item'
        if not any(str(value).strip() for value in row.values()):
            continue
        if kind == 'section':
            section_number += 1
            subheading_number = item_number = 0
            code = _roman_number(section_number)
        elif kind == 'subheading':
            if section_number == 0:
                section_number = 1
            subheading_number += 1
            item_number = 0
            code = f'{_roman_number(section_number)}.{subheading_number}'
        else:
            item_number += 1
            code = row['item_code'].strip() or str(item_number)
        quantity = _autosave_decimal(row['quantity']) if kind == 'item' else Decimal('0')
        rate = _autosave_decimal(row['unit_rate']) if kind == 'item' else Decimal('0')
        amount = quantity * rate if kind == 'item' else _autosave_decimal(row['amount'])
        parsed_lines.append({
            'item_code': code,
            'description': row['description'].strip() or ' ',
            'unit': row['unit'].strip() if kind == 'item' else {
                'section': SECTION_UNIT, 'subheading': SUBHEADING_UNIT, 'note': NOTE_UNIT,
            }[kind],
            'quantity': quantity, 'unit_rate': rate, 'amount': amount, 'position': position,
        })

    issue_date = parse_date(request.POST.get('issue_date', '')) or timezone.localdate()
    try:
        validity_days = min(365, max(1, int(request.POST.get('validity_days') or 14)))
    except ValueError:
        validity_days = 14
    amount = sum((line['amount'] for line in parsed_lines), Decimal('0'))
    with transaction.atomic():
        quotes = quotation.objects.select_for_update().filter(ENQUIRY=record)
        draft_id = request.POST.get('draft_id', '').strip()
        quote = quotes.filter(
            pk=draft_id, status='draft', created_by=request.workflow_staff,
        ).first() if draft_id.isdigit() else None
        if draft_id.isdigit() and quote is None:
            returned_quote = quotes.filter(
                pk=draft_id, status='under_revision', created_by=request.workflow_staff,
            ).first()
            if returned_quote and quotation_internal_review(
                returned_quote.details, returned_quote.validity_days,
            ):
                quote = returned_quote
        revision_source_id = request.POST.get('revision_of', '').strip()
        revision_source = quotes.exclude(status='draft').filter(
            pk=revision_source_id,
        ).first() if revision_source_id.isdigit() else None
        if not quote:
            if quotes.exists() and not revision_source:
                return JsonResponse({'ok': False, 'error': 'Open the existing draft or start a revision.'}, status=409)
            version = (quotes.aggregate(value=Max('version'))['value'] or 0) + 1
            first_quote = quotes.order_by('version', 'id').first()
            revision = (
                (quotes.aggregate(value=Max('revision'))['value'] or 0) + 1
                if first_quote else 0
            )
            quote = quotation.objects.create(
                ENQUIRY=record, version=version, revision=revision, issue_date=issue_date,
                amount=amount, details=details, status='draft', created_by=request.workflow_staff,
            )
            assign_quotation_reference(quote, first_quote)
        elif quote.status == 'under_revision':
            quote.status = 'draft'
        quote.issue_date = issue_date
        quote.amount = amount
        quote.details = details
        quote.subject = request.POST.get('subject', '').strip()[:255]
        quote.client_address = request.POST.get('client_address', '').strip()[:255]
        quote.introduction = request.POST.get('introduction', '').strip()
        quote.validity_days = validity_days
        quote.project_duration = request.POST.get('project_duration', '').strip()
        quote.closing_text = request.POST.get('closing_text', '').strip()
        quote.signatory_name = request.POST.get('signatory_name', '').strip()[:100]
        quote.signatory_title = request.POST.get('signatory_title', '').strip()[:100]
        quote.signatory_phone = request.POST.get('signatory_phone', '').strip()[:40]
        quote.save()
        quote.lines.all().delete()
        quotation_line.objects.bulk_create([
            quotation_line(QUOTATION=quote, **line) for line in parsed_lines
        ])
        costing.objects.update_or_create(
            QUOTATION=quote,
            defaults={
                'material_cost': _autosave_decimal(request.POST.get('material_cost')),
                'labour_cost': _autosave_decimal(request.POST.get('labour_cost')),
                'other_cost': _autosave_decimal(request.POST.get('other_cost')),
                'notes': request.POST.get('costing_notes', '').strip(),
            },
        )
    return JsonResponse({
        'ok': True, 'draft_id': quote.pk, 'quotation_number': quote.display_number,
        'saved_at': timezone.localtime().strftime('%H:%M:%S'),
    })


@require_POST
@role_required('Estimator')
def add_quotation(request, enquiry_id):
    record = get_object_or_404(
        enquiry.objects.prefetch_related('quotations__lines'),
        pk=enquiry_id, assigned_to=request.workflow_staff,
    )
    existing_snapshot = quotation.objects.filter(ENQUIRY=record)
    draft_id = request.POST.get('draft_id', '').strip()
    draft_quote = existing_snapshot.filter(
        pk=draft_id, status='draft', created_by=request.workflow_staff,
    ).first() if draft_id else None
    if draft_id and not draft_quote:
        returned_quote = existing_snapshot.filter(
            pk=draft_id, status='under_revision', created_by=request.workflow_staff,
        ).first()
        if returned_quote and quotation_internal_review(
            returned_quote.details, returned_quote.validity_days,
        ):
            draft_quote = returned_quote
    revision_source_id = request.POST.get('revision_of', '').strip()
    revision_source = existing_snapshot.filter(
        pk=revision_source_id, status='under_revision',
    ).first() if revision_source_id else None
    row_types = request.POST.getlist('row_type')
    item_codes = request.POST.getlist('item_code')
    descriptions = request.POST.getlist('line_description')
    units = request.POST.getlist('unit')
    quantities = request.POST.getlist('quantity')
    rates = request.POST.getlist('unit_rate')
    direct_amounts = request.POST.getlist('line_amount')
    if not row_types and descriptions:
        row_types = ['item'] * len(descriptions)
    if not direct_amounts:
        direct_amounts = [''] * len(descriptions)
    quote_rows = [
        {'row_type': row_type, 'item_code': code, 'description': description, 'unit': unit,
         'quantity': quantity, 'unit_rate': rate, 'amount': direct_amount}
        for row_type, code, description, unit, quantity, rate, direct_amount in zip(
            row_types, item_codes, descriptions, units, quantities, rates, direct_amounts
        )
    ]
    term_titles = request.POST.getlist('term_title')
    term_bodies = request.POST.getlist('term_body')
    quote_terms = [
        {'title': title.strip(), 'body': body.strip()}
        for title, body in zip(term_titles, term_bodies) if title.strip() or body.strip()
    ]
    if not quote_terms:
        quote_terms = default_terms()
        quote_terms[0]['body'] = (
            request.POST.get('details', '').strip()
            or record.description
            or quote_terms[0]['body']
        )
    posted_form = request.POST.dict()
    posted_form.update({
        'client_name': request.POST.get('quotation_client_name', ''),
        'client_phone': request.POST.get('quotation_client_phone', ''),
        'client_email': request.POST.get('quotation_client_email', ''),
    })
    form_context = {
        'quote_form': posted_form,
        'quote_rows': quote_rows,
        'quote_terms': quote_terms or default_terms(),
        'editing_quote': draft_quote,
        'revision_source': revision_source,
    }

    def quotation_error(message):
        messages.error(request, message)
        return _render(
            request, 'Workflow/enquiry_detail.html',
            _detail_context(request, record, form_context), status=400,
        )

    if record.status == 'awarded' or existing_snapshot.filter(status='accepted').exists():
        return quotation_error('An awarded quotation cannot be revised or edited.')

    if draft_id and not draft_quote:
        return quotation_error('This draft is no longer available for editing.')

    upload = request.FILES.get('file')
    if upload:
        try:
            _validate_upload(upload)
        except ValidationError as exc:
            return quotation_error(exc.messages[0])
    try:
        material_amount = _non_negative_decimal(request, 'material_cost', 'Material cost')
        labour_amount = _non_negative_decimal(request, 'labour_cost', 'Labour cost')
        other_amount = _non_negative_decimal(request, 'other_cost', 'Other cost')
    except ValidationError as exc:
        return quotation_error(exc.messages[0])

    if not (
        len(row_types) == len(item_codes) == len(descriptions)
        == len(units) == len(quantities) == len(rates) == len(direct_amounts)
    ):
        return quotation_error('Quotation line-item data is incomplete.')
    parsed_lines = []
    active_lump_sum = False
    for position, row in enumerate(quote_rows, start=1):
        values = tuple(
            str(row[field]).strip()
            for field in ('description', 'unit', 'quantity', 'unit_rate', 'amount')
        )
        if not any(values):
            continue
        row_type = row['row_type'] if row['row_type'] in ('item', 'section', 'subheading', 'note') else 'item'
        if row_type != 'item':
            if not row['description'].strip():
                return quotation_error(f'Enter a heading or note for row {position}.')
            try:
                direct_amount = Decimal(str(row['amount']).strip() or '0')
            except InvalidOperation:
                return quotation_error(f'Total amount on row {position} must be a valid number.')
            if not direct_amount.is_finite() or direct_amount < 0:
                return quotation_error(f'Total amount on row {position} cannot be negative.')
            parsed_lines.append({
                **row,
                'unit': {
                    'section': SECTION_UNIT, 'subheading': SUBHEADING_UNIT, 'note': NOTE_UNIT,
                }[row_type],
                'quantity': Decimal('0'), 'unit_rate': Decimal('0'),
                'amount': direct_amount, 'position': position,
            })
            active_lump_sum = row_type in ('section', 'subheading') and direct_amount > 0
            continue
        if not row['description'].strip():
            return quotation_error(f'Enter a description for line {position}.')
        if not active_lump_sum and (not row['quantity'] or not row['unit_rate']):
            return quotation_error(f'Complete the description, quantity and rate for line {position}.')
        try:
            quantity = Decimal(row['quantity'] or '0')
            rate = Decimal(row['unit_rate'] or '0')
        except InvalidOperation:
            return quotation_error(f'Quantity and rate on line {position} must be valid numbers.')
        if not quantity.is_finite() or not rate.is_finite() or quantity < 0 or rate < 0:
            return quotation_error(f'Line {position} requires a positive quantity and non-negative rate.')
        if not active_lump_sum and (quantity <= 0 or rate <= 0):
            return quotation_error(f'Line {position} requires a positive quantity and non-negative rate.')
        parsed_lines.append({
            **row, 'quantity': quantity, 'unit_rate': rate,
            # A direct section/subheading total is authoritative for its child
            # rows. Child quantities remain useful for the BOQ, while their
            # rate and calculated amount may legitimately be blank.
            'amount': Decimal('0') if active_lump_sum else quantity * rate,
            'position': position,
        })

    # Preserve compatibility for integrations that still send a single total.
    if not parsed_lines and request.POST.get('amount'):
        try:
            legacy_amount = _non_negative_decimal(request, 'amount', 'Quotation amount')
        except ValidationError as exc:
            return quotation_error(exc.messages[0])
        if legacy_amount > 0:
            parsed_lines.append({
                'item_code': '', 'description': request.POST.get('details', '').strip() or 'Quotation total',
                'unit': 'lot', 'quantity': Decimal('1'), 'unit_rate': legacy_amount,
                'amount': legacy_amount, 'position': 1,
            })
    if not parsed_lines or not any(item['amount'] > 0 for item in parsed_lines):
        return quotation_error('Add at least one priced item or enter a total on a section/subheading.')
    section_number = 0
    subheading_number = 0
    item_number = 0
    for line in parsed_lines:
        row_type = line.get('row_type', 'item')
        if row_type == 'section':
            section_number += 1
            subheading_number = 0
            item_number = 0
            line['item_code'] = _roman_number(section_number)
        elif row_type == 'subheading':
            if section_number == 0:
                section_number = 1
            subheading_number += 1
            item_number = 0
            line['item_code'] = f'{_roman_number(section_number)}.{subheading_number}'
        elif row_type == 'item':
            item_number += 1
            if not line['item_code'].strip():
                line['item_code'] = str(item_number)
    try:
        validity_days = int(request.POST.get('validity_days') or 14)
    except ValueError:
        return quotation_error('Quotation validity must be a whole number of days.')
    if not 1 <= validity_days <= 365:
        return quotation_error('Quotation validity must be between 1 and 365 days.')
    issue_date_value = request.POST.get('issue_date', '').strip()
    issue_date = parse_date(issue_date_value) if issue_date_value else timezone.localdate()
    if not issue_date:
        return quotation_error('Enter a valid quotation date.')
    amount = sum((item['amount'] for item in parsed_lines), Decimal('0'))
    if revision_source_id and not revision_source:
        return quotation_error('The selected quotation revision source is not valid for this enquiry.')
    if revision_source and quotation_internal_review(
        revision_source.details, revision_source.validity_days,
    ):
        return quotation_error('Internal revisions must be saved on the existing quotation number.')
    if existing_snapshot.exists() and not revision_source and not draft_quote:
        return quotation_error(
            'Edit the saved draft, or use Create Revision from a quotation returned Under Revision.'
        )
    if revision_source and revision_source.created_by_id != request.workflow_staff.id:
        return quotation_error('You can revise only a quotation created by you.')
    term_map = {term['title'].strip().lower(): term['body'] for term in quote_terms}
    client_name = request.POST.get('quotation_client_name', '').strip() or record.client_name
    client_phone = (
        request.POST.get('quotation_client_phone', '').strip()
        if 'quotation_client_phone' in request.POST else record.client_phone
    )
    client_email = (
        request.POST.get('quotation_client_email', '').strip().lower()
        if 'quotation_client_email' in request.POST else record.client_email
    )
    if len(client_name) > 255:
        return quotation_error('Client name cannot exceed 255 characters.')
    if len(client_phone) > 30:
        return quotation_error('Client phone cannot exceed 30 characters.')
    if len(client_email) > 254 or (client_email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', client_email)):
        return quotation_error('Enter a valid client email address.')
    client_address = request.POST.get('client_address', '').strip()
    if len(client_address) > 255:
        return quotation_error('Client address cannot exceed 255 characters.')
    document_details = pack_document(
        quote_terms, request.POST.get('remarks', ''),
        client_details={
            'name': client_name,
            'phone': client_phone,
            'email': client_email,
        },
    )
    quote_values = {
        'amount': amount,
        'issue_date': issue_date,
        'details': document_details,
        'subject': request.POST.get('subject', '').strip() or f'Quotation for {record.title}',
        'client_address': client_address or 'Doha-State of Qatar',
        'introduction': request.POST.get('introduction', '').strip() or DEFAULT_INTRODUCTION,
        'validity_days': validity_days,
        'payment_terms': term_map.get('payment terms', DEFAULT_TERM_MAP['Payment Terms']),
        'mobilization': term_map.get('mobilization', DEFAULT_TERM_MAP['Mobilization']),
        'variations': term_map.get('variations', DEFAULT_TERM_MAP['Variations']),
        'client_responsibilities': term_map.get(
            'client responsibilities', DEFAULT_TERM_MAP['Client Responsibilities']
        ),
        'material_approval': term_map.get(
            'material approval', DEFAULT_TERM_MAP['Material Approval']
        ),
        'project_duration': (
            term_map.get('project duration')
            or request.POST.get('project_duration', '').strip()
        ),
        'closing_text': request.POST.get('closing_text', '').strip() or DEFAULT_CLOSING_TEXT,
        'signatory_name': request.POST.get('signatory_name', '').strip() or request.workflow_staff.name,
        'signatory_title': (
            request.POST.get('signatory_title', '').strip() or request.workflow_staff.designation
        ),
        'signatory_phone': request.POST.get('signatory_phone', '').strip() or request.workflow_staff.phone,
    }
    with transaction.atomic():
        existing_quotes = quotation.objects.select_for_update().filter(ENQUIRY=record)
        if draft_quote:
            quote = get_object_or_404(
                existing_quotes, pk=draft_quote.pk, created_by=request.workflow_staff,
            )
            if quote.status == 'under_revision' and not quotation_internal_review(
                quote.details, quote.validity_days,
            ):
                return quotation_error('Client-requested revisions must be created as a new quotation version.')
            for field, value in quote_values.items():
                setattr(quote, field, value)
            if quote.status == 'under_revision':
                quote.status = 'draft'
                quote.details = update_quotation_internal_review(
                    quote.details, quote.validity_days,
                )
            if upload:
                quote.file = upload
            quote.save()
            quote.lines.all().delete()
        else:
            version = (existing_quotes.aggregate(v=Max('version'))['v'] or 0) + 1
            first_quote = existing_quotes.order_by('version', 'id').first()
            revision = (
                (existing_quotes.aggregate(v=Max('revision'))['v'] or 0) + 1
                if first_quote else 0
            )
            quote = quotation.objects.create(
                ENQUIRY=record, version=version, revision=revision,
                file=upload or '', created_by=request.workflow_staff,
                status='draft', **quote_values,
            )
            assign_quotation_reference(quote, first_quote)
        quotation_line.objects.bulk_create([
            quotation_line(
                QUOTATION=quote, item_code=item['item_code'].strip(),
                description=item['description'].strip(), unit=item['unit'].strip(),
                quantity=item['quantity'], unit_rate=item['unit_rate'],
                amount=item['amount'], position=item['position'],
            )
            for item in parsed_lines
        ])
        costing.objects.update_or_create(
            QUOTATION=quote,
            defaults={
                'material_cost': material_amount,
                'labour_cost': labour_amount,
                'other_cost': other_amount,
                'notes': request.POST.get('costing_notes', '').strip(),
            },
        )
    action = 'Revised quotation draft' if quote.revision else 'Quotation draft'
    messages.success(
        request,
        f'{action} {quote.display_number} saved. Review it, edit if required, then submit it for approval.',
    )
    return redirect('workflow_view_quotation', quote_id=quote.pk)


@role_required(*WORKFLOW_ROLES)
@xframe_options_sameorigin
def download_quotation(request, quote_id, file_format):
    quote = get_object_or_404(
        quotation.objects.select_related('ENQUIRY').prefetch_related('lines'), pk=quote_id,
    )
    if not _can_view_quotation(request, quote):
        return HttpResponseForbidden('You do not have permission to download this quotation.')
    safe_number = quote.display_number.replace('/', '-').replace('\\', '-')
    if file_format == 'xlsx':
        content = build_quotation_excel(quote)
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        filename = f'{safe_number}.xlsx'
    elif file_format == 'pdf':
        content = build_quotation_pdf(quote)
        content_type = 'application/pdf'
        filename = f'{safe_number}.pdf'
    else:
        raise Http404('Unsupported quotation format.')
    return FileResponse(
        content,
        as_attachment=request.GET.get('preview') != '1',
        filename=filename,
        content_type=content_type,
    )


@role_required(*WORKFLOW_ROLES)
def view_quotation(request, quote_id):
    quote = get_object_or_404(
        quotation.objects.select_related(
            'ENQUIRY', 'ENQUIRY__assigned_to__LOGIN', 'created_by', 'costing',
        ).prefetch_related('lines'),
        pk=quote_id,
    )
    if not _can_view_quotation(request, quote):
        return HttpResponseForbidden('You do not have permission to view this quotation.')
    document = unpack_document(quote.details, quote.validity_days)
    tracking = quotation_tracking(quote.details, quote.validity_days)
    tracking['submitted_at_value'] = parse_datetime(tracking['submitted_at']) if tracking['submitted_at'] else None
    tracking['client_status_label'] = CLIENT_RESPONSE_STATUSES.get(
        tracking['client_status'], CLIENT_RESPONSE_STATUSES['under_review'],
    )
    internal_revision_stage = quotation_internal_review(quote.details, quote.validity_days)
    is_current_quote = _is_current_quotation(quote)
    role = _workflow_role(request.workflow_account.usertype)
    discussion_url = _quotation_discussion_url(quote)
    quote_costing = getattr(quote, 'costing', None)
    email_subject, email_body = quotation_email_content(quote)
    return _render(request, 'Workflow/quotation_view.html', {
        'quote': quote,
        'enquiry': quote.ENQUIRY,
        'document': document,
        'quotation_rows': presentation_rows(quote.lines.all()),
        'amount_words': quotation_amount_words(quote.amount),
        'discussion_unread_count': workflow_notification.objects.filter(
            recipient=request.workflow_account, event='quotation_comment',
            link=discussion_url, read_at__isnull=True,
        ).count(),
        'client_tracking': tracking,
        'client_response_statuses': CLIENT_RESPONSE_STATUSES,
        'internal_revision_stage': internal_revision_stage,
        'has_client_submission': bool(tracking['submitted_at']),
        'related_quotations': [
            item for item in quotation.objects.filter(ENQUIRY=quote.ENQUIRY).order_by('-version')
            if _can_view_quotation(request, item)
        ],
        'is_current_quote': is_current_quote,
        'email_subject': email_subject,
        'email_body': email_body,
        'submission_recipient': (document.get('client') or {}).get(
            'email', quote.ENQUIRY.client_email,
        ),
        'can_manage_client_response': (
            _workflow_role(request.workflow_account.usertype) in (
                'Admin', 'Marketing Executive', 'Marketing Manager',
            ) and is_current_quote and (
                quote.status in ('submitted', 'rejected')
                or (quote.status == 'under_revision' and not internal_revision_stage)
            )
        ),
        'can_remove_quote_file': (
            _workflow_role(request.workflow_account.usertype) == 'Estimator'
            and quote.created_by_id == getattr(request.workflow_staff, 'id', None)
        ),
        'can_edit_draft': (
            role == 'Estimator'
            and is_current_quote
            and (
                quote.status == 'draft'
                or (quote.status == 'under_revision' and internal_revision_stage)
            )
            and quote.created_by_id == getattr(request.workflow_staff, 'id', None)
        ),
        'can_create_revision': (
            role == 'Estimator'
            and is_current_quote
            and quote.status == 'under_revision'
            and not internal_revision_stage
            and quote.created_by_id == getattr(request.workflow_staff, 'id', None)
        ),
        'can_manager_approve': is_current_quote and role == 'Marketing Manager' and quote.status == 'manager_review',
        'can_accountant_approve': is_current_quote and role == 'Accountant' and quote.status == 'accountant_review',
        'can_request_revision': (
            is_current_quote and ((role == 'Marketing Manager' and quote.status == 'manager_review')
            or (role == 'Accountant' and quote.status == 'accountant_review'))
        ),
        'can_approve_costing': (
            role == 'Project Manager' and quote_costing is not None
            and not quote_costing.approved_at
        ),
        'can_submit': (
            role in ('Document Controller', 'Marketing Executive', 'Marketing Manager')
            and is_current_quote and quote.status == 'approved'
        ),
        'costing_approved': bool(quote_costing and quote_costing.approved_at),
        'can_award': (
            role in ('Marketing Executive', 'Marketing Manager')
            and is_current_quote and quote.status == 'submitted'
        ),
    })


@role_required('Estimator')
def start_quotation_revision(request, quote_id):
    quote = get_object_or_404(
        quotation.objects.select_related('ENQUIRY'), pk=quote_id,
        status='under_revision', created_by=request.workflow_staff,
    )
    if quote.ENQUIRY.status == 'awarded' or quote.ENQUIRY.quotations.filter(status='accepted').exists():
        messages.error(request, 'An awarded quotation cannot be revised.')
        return redirect('workflow_view_quotation', quote_id=quote.pk)
    if quotation_internal_review(quote.details, quote.validity_days):
        messages.error(request, 'This is an internal revision. Edit the same quotation; no new revision number is created.')
        return redirect(
            f'{reverse("workflow_detail", args=(quote.ENQUIRY_id,))}?edit={quote.pk}#quotationForm'
        )
    return redirect(
        f'{reverse("workflow_detail", args=(quote.ENQUIRY_id,))}?revise={quote.pk}#quotationForm'
    )


@role_required(*QUOTATION_COMMENT_ROLES)
def quotation_discussion(request, quote_id):
    quote = get_object_or_404(
        quotation.objects.select_related(
            'ENQUIRY', 'ENQUIRY__assigned_to__LOGIN', 'created_by',
        ), pk=quote_id,
    )
    restricted_marketing = (
        request.workflow_account.usertype == 'Marketing Executive'
        and _is_marketing_restricted_quotation(quote)
    )
    mentioned_threads = _quotation_comment_threads(quote, request.workflow_account)
    if not _can_view_quotation(request, quote) and not (restricted_marketing and mentioned_threads):
        return HttpResponseForbidden('You do not have permission to view this discussion.')
    workflow_notification.objects.filter(
        recipient=request.workflow_account, event='quotation_comment',
        link=_quotation_discussion_url(quote), read_at__isnull=True,
    ).update(read_at=timezone.now())
    return _render(request, 'Workflow/quotation_discussion.html', {
        'quote': quote,
        'enquiry': quote.ENQUIRY,
        'discussion_threads': mentioned_threads,
        'discussion_recipients': [
            account for account in login.objects.filter(
                pk__in=_quotation_discussion_recipient_ids(quote),
            ).order_by('usertype', 'username') if account.pk != request.workflow_account.pk
        ],
        'restricted_marketing_discussion': restricted_marketing,
    })


@require_POST
@role_required('Estimator')
def remove_quotation_file(request, quote_id):
    quote = get_object_or_404(quotation, pk=quote_id, created_by=request.workflow_staff)
    if quote.file:
        quote.file.delete(save=False)
        quote.file = ''
        quote.save(update_fields=('file', 'updated_at'))
        messages.success(request, 'The attached quotation file was removed.')
    return redirect('workflow_view_quotation', quote_id=quote.pk)


@require_POST
@role_required('Marketing Executive', 'Marketing Manager', 'Estimator', 'Accountant')
def add_quotation_comment(request, quote_id):
    quote = get_object_or_404(
        quotation.objects.select_related('ENQUIRY', 'ENQUIRY__assigned_to__LOGIN'),
        pk=quote_id,
    )
    if not _can_view_quotation(request, quote):
        return HttpResponseForbidden('You do not have permission to comment on this quotation.')
    value = request.POST.get('comment', '').strip()
    if value:
        parent_id = request.POST.get('parent_id', '').strip()
        parent_prefix = ''
        parent_recipients = set()
        if parent_id:
            valid_parents = list(quote.ENQUIRY.comments.filter(
                    Q(comment__startswith=_quotation_comment_prefix(quote))
                    | Q(comment__startswith=f'[{quote.display_number}] ')
                ))
            valid_parent_ids = {item.pk for item in valid_parents}
            if not parent_id.isdigit() or int(parent_id) not in valid_parent_ids:
                messages.error(request, 'The message you are replying to is no longer available.')
                return redirect('workflow_quotation_discussion', quote_id=quote.pk)
            parent_prefix = f'[REPLY:{parent_id}] '
            parent_comment = next(item for item in valid_parents if item.pk == int(parent_id)).comment
            inherited_match = re.search(r'\[TO:([0-9,]+)\]', parent_comment)
            if inherited_match:
                parent_recipients = {
                    int(value) for value in inherited_match.group(1).split(',') if value.isdigit()
                }
        valid_recipient_ids = _quotation_discussion_recipient_ids(quote) - {request.workflow_account.id}
        selected_recipient_ids = {
            int(value) for value in request.POST.getlist('recipient_ids') if value.isdigit()
        }
        if not selected_recipient_ids and parent_recipients:
            selected_recipient_ids = parent_recipients - {request.workflow_account.id}
        if not selected_recipient_ids:
            selected_recipient_ids = valid_recipient_ids
        if not selected_recipient_ids.issubset(valid_recipient_ids):
            messages.error(request, 'Select only valid quotation discussion recipients.')
            return redirect('workflow_quotation_discussion', quote_id=quote.pk)
        if _is_marketing_restricted_quotation(quote) and not request.POST.getlist('recipient_ids') and not parent_recipients:
            messages.error(request, 'Select at least one recipient for an internal discussion message.')
            return redirect('workflow_quotation_discussion', quote_id=quote.pk)
        recipient_prefix = f'[TO:{",".join(str(value) for value in sorted(selected_recipient_ids))}] '
        item = enquiry_comment.objects.create(
            ENQUIRY=quote.ENQUIRY,
            author=request.workflow_account,
            comment=f'{_quotation_comment_prefix(quote)}{parent_prefix}{recipient_prefix}{value}',
        )
        discussion_url = _quotation_discussion_url(quote)
        for recipient_id in selected_recipient_ids:
            workflow_notification.objects.get_or_create(
                dedupe_key=f'quotation-comment:{item.pk}:{recipient_id}',
                defaults={
                    'recipient_id': recipient_id,
                    'ENQUIRY': quote.ENQUIRY,
                    'event': 'quotation_comment',
                    'level': 'info',
                    'message': f'New discussion message on {quote.display_number}.',
                    'link': discussion_url,
                },
            )
        messages.success(request, 'Message added to the quotation discussion.')
    return redirect('workflow_quotation_discussion', quote_id=quote.pk)


@require_POST
@role_required('Estimator')
def submit_quotation_for_approval(request, quote_id):
    with transaction.atomic():
        quote = get_object_or_404(
            quotation.objects.select_for_update().select_related('ENQUIRY'),
            pk=quote_id,
            status='draft',
            created_by=request.workflow_staff,
            ENQUIRY__assigned_to=request.workflow_staff,
        )
        if not _is_current_quotation(quote):
            messages.error(request, 'Only the current quotation version can be submitted for approval.')
            return redirect('workflow_view_quotation', quote_id=quote.pk)
        if not quote.lines.filter(amount__gt=0).exists():
            messages.error(request, 'Add at least one priced item or heading total before submitting for approval.')
            return redirect('workflow_view_quotation', quote_id=quote.pk)
        quote.status = 'manager_review'
        quote.save(update_fields=('status', 'updated_at'))
        quote.ENQUIRY.status = 'quoted'
        quote.ENQUIRY.save(update_fields=('status', 'updated_at'))
    messages.success(
        request,
        f'{quote.display_number} submitted to the Marketing Manager for first approval.',
    )
    return redirect('workflow_view_quotation', quote_id=quote.pk)


@role_required(*WORKFLOW_ROLES)
def workflow_notifications(request):
    notices = workflow_notification.objects.filter(
        recipient=request.workflow_account,
    ).select_related('ENQUIRY')
    return _render(request, 'Workflow/notifications.html', {'notifications': notices})


@require_POST
@role_required(*WORKFLOW_ROLES)
def read_workflow_notification(request, notification_id):
    notice = get_object_or_404(
        workflow_notification, pk=notification_id, recipient=request.workflow_account,
    )
    if not notice.read_at:
        notice.read_at = timezone.now()
        notice.save(update_fields=('read_at',))
    return redirect(notice.link or 'workflow_notifications')


@require_POST
@role_required('Marketing Manager', 'Accountant')
def request_quotation_revision(request, quote_id):
    role = _workflow_role(request.workflow_account.usertype)
    expected_status = 'manager_review' if role == 'Marketing Manager' else 'accountant_review'
    with transaction.atomic():
        quote = get_object_or_404(
            quotation.objects.select_for_update().select_related('ENQUIRY'),
            pk=quote_id, status=expected_status,
        )
        if not _is_current_quotation(quote):
            messages.error(request, 'Only the current quotation version can be reviewed.')
            return redirect('workflow_view_quotation', quote_id=quote.pk)
        remarks = request.POST.get('remarks', '').strip()
        if not remarks:
            messages.error(request, 'Enter the correction or revision request for the estimator.')
            return redirect('workflow_view_quotation', quote_id=quote.pk)
        if len(remarks) > 2000:
            messages.error(request, 'Revision request cannot exceed 2,000 characters.')
            return redirect('workflow_view_quotation', quote_id=quote.pk)
        quote.status = 'under_revision'
        quote.details = update_quotation_internal_review(
            quote.details, quote.validity_days,
            stage='manager' if role == 'Marketing Manager' else 'accountant',
        )
        update_fields = ['status', 'details', 'updated_at']
        if role == 'Marketing Manager':
            quote.manager_approved_by = None
            quote.manager_approved_at = None
            update_fields.extend(['manager_approved_by', 'manager_approved_at'])
        else:
            quote.accountant_approved_by = None
            quote.accountant_approved_at = None
            update_fields.extend(['accountant_approved_by', 'accountant_approved_at'])
        quote.save(update_fields=update_fields)
        if quote.ENQUIRY.status not in ('closed', 'awarded'):
            quote.ENQUIRY.status = 'quoted'
            quote.ENQUIRY.save(update_fields=('status', 'updated_at'))
        publish_quotation_message(
            quote, request.workflow_account,
            f'{role} requested quotation revision.\nRevision request: {remarks}',
            recipient_ids=(
                _quotation_discussion_recipient_ids(quote)
                - {quote.ENQUIRY.created_by_id}
            ),
        )
    messages.success(request, 'Internal revision request sent to the estimator.')
    return redirect('workflow_dashboard')


@require_POST
@role_required('Marketing Manager')
def manager_approve(request, quote_id):
    with transaction.atomic():
        quote = get_object_or_404(
            quotation.objects.select_for_update(), pk=quote_id, status='manager_review'
        )
        if not _is_current_quotation(quote):
            messages.error(request, 'Only the current quotation version can be approved.')
            return redirect('workflow_view_quotation', quote_id=quote.pk)
        quote.status = 'accountant_review'
        quote.manager_approved_by = request.workflow_staff
        quote.manager_approved_at = timezone.now()
        quote.save(update_fields=('status', 'manager_approved_by', 'manager_approved_at', 'updated_at'))
    messages.success(request, 'First quotation approval completed; Accountant approval is now pending.')
    return redirect('workflow_view_quotation', quote_id=quote.pk)


@require_POST
@role_required('Accountant')
def accountant_approve(request, quote_id):
    with transaction.atomic():
        quote = get_object_or_404(quotation.objects.select_for_update(), pk=quote_id, status='accountant_review')
        if not _is_current_quotation(quote):
            messages.error(request, 'Only the current quotation version can be approved.')
            return redirect('workflow_view_quotation', quote_id=quote.pk)
        quote.status = 'approved'
        quote.accountant_approved_by = request.workflow_staff
        quote.accountant_approved_at = timezone.now()
        quote.save(update_fields=('status', 'accountant_approved_by', 'accountant_approved_at', 'updated_at'))
        quote.ENQUIRY.status = 'approved'
        quote.ENQUIRY.save(update_fields=('status', 'updated_at'))
    messages.success(request, 'Final quotation approval completed.')
    return redirect('workflow_view_quotation', quote_id=quote.pk)


@require_POST
@role_required('Project Manager')
def approve_costing(request, quote_id):
    quote = get_object_or_404(quotation, pk=quote_id)
    cost = get_object_or_404(costing, QUOTATION=quote)
    cost.approved_by = request.workflow_staff
    cost.approved_at = timezone.now()
    cost.save(update_fields=('approved_by', 'approved_at', 'updated_at'))
    messages.success(request, 'Costing approved.')
    return redirect('workflow_view_quotation', quote_id=quote.pk)


@require_POST
@role_required('Document Controller', 'Marketing Executive', 'Marketing Manager')
def submit_quotation(request, quote_id):
    try:
        with transaction.atomic():
            quote = get_object_or_404(
                quotation.objects.select_for_update().select_related('ENQUIRY'),
                pk=quote_id, status='approved',
            )
            if not _is_current_quotation(quote):
                messages.error(request, 'Only the current quotation version can be submitted to the client.')
                return redirect('workflow_view_quotation', quote_id=quote.pk)
            if not _can_access_enquiry(request, quote.ENQUIRY):
                return HttpResponseForbidden('You do not have permission to submit this quotation.')
            recipient = send_quotation_to_client(
                quote,
                to=request.POST.get('to', ''),
                cc=request.POST.get('cc', ''),
                subject=request.POST.get('subject'),
                body=request.POST.get('body'),
            )
            quote.status = 'submitted'
            quote.details = update_quotation_tracking(
                quote.details, quote.validity_days,
                submitted_at=timezone.now().isoformat(), client_status='under_review',
            )
            quote.save(update_fields=('status', 'details', 'updated_at'))
            quote.ENQUIRY.status = 'submitted'
            quote.ENQUIRY.save(update_fields=('status', 'updated_at'))
    except QuotationDeliveryError as exc:
        messages.error(request, f'{exc} The quotation remains approved and was not submitted.')
        return redirect('workflow_view_quotation', quote_id=quote_id)
    messages.success(
        request,
        f'Quotation emailed successfully to {recipient}; client status is now Under Review.',
    )
    return redirect('workflow_view_quotation', quote_id=quote.pk)


@require_POST
@role_required('Marketing Executive', 'Marketing Manager')
def award_project(request, quote_id):
    with transaction.atomic():
        quote = get_object_or_404(
            quotation.objects.select_for_update(), pk=quote_id, status='submitted',
        )
        if not _is_current_quotation(quote):
            messages.error(request, 'Only the current quotation version can be awarded.')
            return redirect('workflow_view_quotation', quote_id=quote.pk)
        if not _can_access_enquiry(request, quote.ENQUIRY):
            return HttpResponseForbidden('You do not have permission to update this quotation.')
        quote.status = 'accepted'
        quote.details = update_quotation_tracking(
            quote.details, quote.validity_days, client_status='approved',
        )
        quote.save(update_fields=('status', 'details', 'updated_at'))
        quote.ENQUIRY.status = 'awarded'
        quote.ENQUIRY.save(update_fields=('status', 'updated_at'))
        publish_client_response(quote, request.workflow_account, 'approved')
    messages.success(request, 'Client acceptance recorded; the enquiry is ready to become a project.')
    return redirect('workflow_detail', enquiry_id=quote.ENQUIRY_id)


@require_POST
@role_required('Admin', 'Marketing Executive', 'Marketing Manager')
def update_quotation_client_response(request, quote_id):
    with transaction.atomic():
        quote = get_object_or_404(
            quotation.objects.select_for_update().select_related('ENQUIRY'), pk=quote_id,
        )
        if not _can_access_enquiry(request, quote.ENQUIRY):
            return HttpResponseForbidden('You do not have permission to update this quotation.')
        if quote.status not in ('submitted', 'rejected', 'under_revision'):
            messages.error(request, 'Client feedback can be recorded only after quotation submittal.')
            return redirect('workflow_dashboard')
        if not _is_current_quotation(quote):
            messages.error(request, 'Only the current quotation version can receive a client response.')
            return redirect('workflow_dashboard')
        if quote.status == 'under_revision' and quotation_internal_review(
            quote.details, quote.validity_days,
        ):
            messages.error(request, 'Internal revision requests do not change client response details.')
            return redirect('workflow_dashboard')
        client_status = request.POST.get('client_status', 'under_review').strip()
        if client_status not in CLIENT_RESPONSE_STATUSES:
            messages.error(request, 'Select a valid client quotation status.')
            return redirect('workflow_dashboard')
        if client_status == 'under_revision' and _workflow_role(request.workflow_account.usertype) not in ('Admin', 'Marketing Manager'):
            messages.error(request, 'Only a Marketing Manager or Admin can return a quotation for revision.')
            return redirect('workflow_dashboard')
        client_remarks = request.POST.get('client_remarks', '').strip()
        if len(client_remarks) > 2000:
            messages.error(request, 'Client remarks cannot exceed 2,000 characters.')
            return redirect('workflow_dashboard')

        quote.details = update_quotation_tracking(
            quote.details, quote.validity_days,
            client_remarks=client_remarks, client_status=client_status,
        )
        quote.status = {
            'under_review': 'submitted', 'approved': 'accepted', 'rejected': 'rejected',
            'under_revision': 'under_revision',
        }[client_status]
        quote.save(update_fields=('details', 'status', 'updated_at'))
        if client_status == 'approved':
            quote.ENQUIRY.status = 'awarded'
        elif client_status in ('under_review', 'under_revision', 'rejected') and quote.ENQUIRY.status != 'closed':
            quote.ENQUIRY.status = 'submitted' if client_status in ('under_review', 'under_revision') else 'quoted'
        quote.ENQUIRY.save(update_fields=('status', 'updated_at'))
        publish_client_response(
            quote, request.workflow_account, client_status, client_remarks,
        )
    messages.success(request, f'Client response saved for {quote.display_number}.')
    if request.POST.get('return_to') == 'quotation':
        return redirect('workflow_view_quotation', quote_id=quote.pk)
    return redirect('workflow_dashboard')


@require_POST
@role_required('Marketing Executive')
def collect_document(request, enquiry_id):
    record = get_object_or_404(enquiry, pk=enquiry_id, created_by=request.workflow_account)
    uploads = request.FILES.getlist('files') or request.FILES.getlist('file')
    if not uploads:
        messages.error(request, 'Select at least one document to upload.')
    else:
        try:
            for upload in uploads:
                _validate_upload(upload)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            with transaction.atomic():
                for upload in uploads:
                    project_document.objects.create(
                        ENQUIRY=record,
                        file=upload,
                        document_type=request.POST.get('document_type', 'client'),
                        collected_by=request.workflow_account,
                    )
            messages.success(
                request, f'{len(uploads)} client project document(s) collected.'
            )
    return redirect('workflow_detail', enquiry_id=enquiry_id)


@require_POST
@role_required('Document Controller')
def verify_document(request, document_id):
    document = get_object_or_404(project_document, pk=document_id)
    document.verified_by = request.workflow_staff
    document.verified_at = timezone.now()
    document.save(update_fields=('verified_by', 'verified_at'))
    messages.success(request, 'Project document verified.')
    return redirect('workflow_detail', enquiry_id=document.ENQUIRY_id)


def _cad_source(source, file_id):
    if source == 'enquiry':
        item = get_object_or_404(
            enquiry_attachment.objects.select_related('ENQUIRY'), pk=file_id
        )
        file_name = item.original_name
    elif source == 'document':
        item = get_object_or_404(
            project_document.objects.select_related('ENQUIRY'), pk=file_id
        )
        file_name = Path(item.file.name).name
    else:
        raise Http404('Unknown CAD file source.')
    if not item.is_cad:
        raise Http404('This file is not a supported CAD drawing.')
    return item, file_name


@role_required(*WORKFLOW_ROLES)
def cad_viewer(request, source, file_id):
    item, file_name = _cad_source(source, file_id)
    if not _can_access_enquiry(request, item.ENQUIRY):
        return HttpResponseForbidden('You do not have permission to view this drawing.')
    return _render(request, 'Workflow/cad_viewer.html', {
        'enquiry': item.ENQUIRY,
        'cad_file_name': file_name,
        'cad_file_url': request.build_absolute_uri(
            reverse('workflow_cad_file', args=(source, file_id))
        ),
    })


@role_required(*WORKFLOW_ROLES)
def cad_file(request, source, file_id):
    item, file_name = _cad_source(source, file_id)
    if not _can_access_enquiry(request, item.ENQUIRY):
        return HttpResponseForbidden('You do not have permission to view this drawing.')
    response = FileResponse(
        item.file.open('rb'),
        as_attachment=False,
        filename=file_name,
        content_type='application/octet-stream',
    )
    response['Cache-Control'] = 'private, no-store'
    return response
