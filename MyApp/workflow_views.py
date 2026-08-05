from functools import wraps
from pathlib import Path
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.db.models import Max, Prefetch, Q
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from .models import (
    costing, enquiry, enquiry_attachment, enquiry_comment, login,
    project_document, quotation, quotation_line, staff, workflow_notification,
)
from .middleware import role_is_allowed
from .deadline_notifications import ensure_quotation_deadline_notifications
from .quotation_exports import build_quotation_excel, build_quotation_pdf
from .quotation_numbers import assign_quotation_reference


WORKFLOW_ROLES = {
    'Admin', 'Marketing Executive', 'Marketing Manager', 'Estimator',
    'Document Controller', 'Project Manager', 'Project Engineer',
    'Operation Manager', 'Accountant',
}
UPLOAD_EXTENSIONS = ('xlsx', 'xls', 'jpg', 'jpeg', 'png', 'pdf', 'dwg', 'dxf', 'doc', 'docx')
MAX_UPLOAD_SIZE = 20 * 1024 * 1024

DEFAULT_PAYMENT_TERMS = (
    '50% in Advance upon confirmation of the work\n'
    '20% upon submittal of progressive invoice\n'
    '20% upon submittal of progressive invoice\n'
    '10% on completion of the project'
)
DEFAULT_MOBILIZATION = (
    'Work shall commence within 3 days after receipt of the advance payment, '
    'approved drawings, and site handover.'
)
DEFAULT_VARIATIONS = (
    'Any changes to the approved design, materials, quantities, finishes, or scope '
    'requested by the Client shall be subject to a separate variation order and may '
    'affect the project cost and completion period.'
)
DEFAULT_CLIENT_RESPONSIBILITIES = (
    'Provide unrestricted access to the work site.\n'
    'Ensure availability of electricity and water during the construction period.\n'
    'Obtain necessary landlord/building management approvals unless specifically included in our scope.\n'
    'Provide timely approvals for drawings, materials, and samples.'
)
DEFAULT_MATERIAL_APPROVAL = (
    'All materials and finishes shall be subject to Client approval. Equivalent '
    'materials may be proposed if specified materials become unavailable.'
)
DEFAULT_CLOSING_TEXT = (
    'We hope the above quote meets your requirement and we assure quality work '
    'completed on time. If you have any further queries, please feel free to contact us.'
)


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


def _workflow_role(role):
    if role in ('Project Engineer', 'Operation Manager'):
        return 'Project Manager'
    return role


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
    context = {
        'enquiry': record,
        'estimators': staff.objects.filter(designation='Estimator').only('id', 'name'),
        'can_assign': role in ('Marketing Manager', 'Project Manager'),
        'can_quote': role == 'Estimator',
        'can_manager_approve': role == 'Marketing Manager',
        'can_accountant_approve': role == 'Accountant',
        'can_approve_costing': role == 'Project Manager',
        'can_submit': role == 'Document Controller',
        'can_award': role == 'Marketing Executive',
        'can_collect': role == 'Marketing Executive',
        'can_verify': role == 'Document Controller',
    }
    context.update(extra or {})
    return context


@role_required(*WORKFLOW_ROLES)
def dashboard(request):
    role = _workflow_role(request.workflow_account.usertype)
    records = enquiry.objects.select_related('created_by', 'assigned_to', 'PROJECT')
    if role == 'Marketing Executive':
        records = records.filter(created_by=request.workflow_account)
    elif role == 'Estimator':
        records = records.filter(assigned_to=request.workflow_staff)
    query = request.GET.get('q', '').strip()
    if query:
        records = records.filter(
            Q(title__icontains=query)
            | Q(client_name__icontains=query)
            | Q(client_email__icontains=query)
            | Q(client_phone__icontains=query)
            | Q(assigned_to__name__icontains=query)
        )
    visible_records = records
    records = visible_records[:100]
    return _render(request, 'Workflow/dashboard.html', {
        'enquiries': records,
        'can_add': role == 'Marketing Executive',
        'query': query,
        'summary': {
            'open': visible_records.filter(status='open').count(),
            'assigned': visible_records.filter(status='assigned').count(),
            'awaiting_approval': quotation.objects.filter(
                ENQUIRY__in=visible_records,
                status__in=('manager_review', 'accountant_review'),
            ).count(),
            'awarded': visible_records.filter(status='awarded').count(),
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


@role_required('Marketing Executive')
def add_enquiry(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        client_name = request.POST.get('client_name', '').strip()
        if not title or not client_name:
            messages.error(request, 'Enquiry title and client name are required.')
            return _render(request, 'Workflow/enquiry_form.html', {
                'form_data': request.POST,
            }, status=400)
        deadline_value = request.POST.get('quotation_deadline', '').strip()
        deadline = parse_datetime(deadline_value) if deadline_value else None
        if not deadline:
            messages.error(request, 'Enter the quotation submission deadline.')
            return _render(request, 'Workflow/enquiry_form.html', {
                'form_data': request.POST,
            }, status=400)
        if timezone.is_naive(deadline):
            deadline = timezone.make_aware(deadline, timezone.get_current_timezone())
        if deadline <= timezone.now():
            messages.error(request, 'The quotation deadline must be in the future.')
            return _render(request, 'Workflow/enquiry_form.html', {
                'form_data': request.POST,
            }, status=400)
        uploads = request.FILES.getlist('files')
        try:
            for upload in uploads:
                _validate_upload(upload)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return _render(request, 'Workflow/enquiry_form.html', {
                'form_data': request.POST,
            }, status=400)
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
    if value:
        enquiry_comment.objects.create(ENQUIRY=record, author=request.workflow_account, comment=value)
        messages.success(request, 'Comment added.')
    return redirect('workflow_detail', enquiry_id=enquiry_id)


@require_POST
@role_required('Marketing Manager', 'Project Manager')
def assign_estimator(request, enquiry_id):
    record = get_object_or_404(enquiry, pk=enquiry_id)
    estimator = get_object_or_404(staff, pk=request.POST.get('estimator'), designation='Estimator')
    record.assigned_to = estimator
    record.status = 'assigned'
    record.save(update_fields=('assigned_to', 'status', 'updated_at'))
    messages.success(request, f'Enquiry assigned to {estimator.name}.')
    return redirect('workflow_detail', enquiry_id=enquiry_id)


@require_POST
@role_required('Estimator')
def add_quotation(request, enquiry_id):
    record = get_object_or_404(
        enquiry.objects.prefetch_related('quotations__lines'),
        pk=enquiry_id, assigned_to=request.workflow_staff,
    )
    item_codes = request.POST.getlist('item_code')
    descriptions = request.POST.getlist('line_description')
    units = request.POST.getlist('unit')
    quantities = request.POST.getlist('quantity')
    rates = request.POST.getlist('unit_rate')
    quote_rows = [
        {'item_code': code, 'description': description, 'unit': unit,
         'quantity': quantity, 'unit_rate': rate}
        for code, description, unit, quantity, rate in zip(
            item_codes, descriptions, units, quantities, rates
        )
    ]
    form_context = {
        'quote_form': request.POST,
        'quote_rows': quote_rows,
    }

    def quotation_error(message):
        messages.error(request, message)
        return _render(
            request, 'Workflow/enquiry_detail.html',
            _detail_context(request, record, form_context), status=400,
        )

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

    if not (len(item_codes) == len(descriptions) == len(units) == len(quantities) == len(rates)):
        return quotation_error('Quotation line-item data is incomplete.')
    parsed_lines = []
    for position, row in enumerate(quote_rows, start=1):
        values = tuple(str(value).strip() for value in row.values())
        if not any(values):
            continue
        if not row['description'].strip() or not row['quantity'] or not row['unit_rate']:
            return quotation_error(f'Complete the description, quantity and rate for line {position}.')
        try:
            quantity = Decimal(row['quantity'])
            rate = Decimal(row['unit_rate'])
        except InvalidOperation:
            return quotation_error(f'Quantity and rate on line {position} must be valid numbers.')
        if not quantity.is_finite() or not rate.is_finite() or quantity <= 0 or rate < 0:
            return quotation_error(f'Line {position} requires a positive quantity and non-negative rate.')
        parsed_lines.append({
            **row, 'quantity': quantity, 'unit_rate': rate,
            'amount': quantity * rate, 'position': position,
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
    if not parsed_lines:
        return quotation_error('Add at least one quotation line item.')
    try:
        validity_days = int(request.POST.get('validity_days') or 14)
    except ValueError:
        return quotation_error('Quotation validity must be a whole number of days.')
    if not 1 <= validity_days <= 365:
        return quotation_error('Quotation validity must be between 1 and 365 days.')
    amount = sum((item['amount'] for item in parsed_lines), Decimal('0'))
    with transaction.atomic():
        existing_quotes = quotation.objects.select_for_update().filter(ENQUIRY=record)
        version = (existing_quotes.aggregate(v=Max('version'))['v'] or 0) + 1
        first_quote = existing_quotes.order_by('version', 'id').first()
        revision = (existing_quotes.aggregate(v=Max('revision'))['v'] or 0) + 1 if first_quote else 0
        quote = quotation.objects.create(
            ENQUIRY=record, version=version, amount=amount,
            revision=revision,
            details=request.POST.get('details', '').strip(),
            subject=request.POST.get('subject', '').strip() or f'Quotation for {record.title}',
            client_address=request.POST.get('client_address', '').strip() or 'Doha-State of Qatar',
            introduction=request.POST.get('introduction', '').strip(),
            validity_days=validity_days,
            payment_terms=request.POST.get('payment_terms', '').strip() or DEFAULT_PAYMENT_TERMS,
            mobilization=request.POST.get('mobilization', '').strip() or DEFAULT_MOBILIZATION,
            variations=request.POST.get('variations', '').strip() or DEFAULT_VARIATIONS,
            client_responsibilities=(
                request.POST.get('client_responsibilities', '').strip()
                or DEFAULT_CLIENT_RESPONSIBILITIES
            ),
            material_approval=(
                request.POST.get('material_approval', '').strip()
                or DEFAULT_MATERIAL_APPROVAL
            ),
            project_duration=request.POST.get('project_duration', '').strip(),
            closing_text=request.POST.get('closing_text', '').strip() or DEFAULT_CLOSING_TEXT,
            signatory_name=request.POST.get('signatory_name', '').strip() or request.workflow_staff.name,
            signatory_title=request.POST.get('signatory_title', '').strip() or request.workflow_staff.designation,
            signatory_phone=request.POST.get('signatory_phone', '').strip() or request.workflow_staff.phone,
            file=upload or '', created_by=request.workflow_staff,
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
        costing.objects.create(
            QUOTATION=quote,
            material_cost=material_amount,
            labour_cost=labour_amount,
            other_cost=other_amount,
            notes=request.POST.get('costing_notes', '').strip(),
        )
        record.status = 'quoted'
        record.save(update_fields=('status', 'updated_at'))
    action = 'Revised quotation' if quote.revision else 'Quotation'
    messages.success(
        request,
        f'{action} {quote.display_number} and costing sent for Marketing Manager approval.',
    )
    return redirect('workflow_detail', enquiry_id=enquiry_id)


@role_required(*WORKFLOW_ROLES)
def download_quotation(request, quote_id, file_format):
    quote = get_object_or_404(
        quotation.objects.select_related('ENQUIRY').prefetch_related('lines'), pk=quote_id,
    )
    if not _can_access_enquiry(request, quote.ENQUIRY):
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
    return FileResponse(content, as_attachment=True, filename=filename, content_type=content_type)


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
@role_required('Marketing Manager')
def manager_approve(request, quote_id):
    with transaction.atomic():
        quote = get_object_or_404(
            quotation.objects.select_for_update(), pk=quote_id, status='manager_review'
        )
        quote.status = 'accountant_review'
        quote.manager_approved_by = request.workflow_staff
        quote.manager_approved_at = timezone.now()
        quote.save(update_fields=('status', 'manager_approved_by', 'manager_approved_at', 'updated_at'))
    messages.success(request, 'First quotation approval completed; Accountant approval is now pending.')
    return redirect('workflow_detail', enquiry_id=quote.ENQUIRY_id)


@require_POST
@role_required('Accountant')
def accountant_approve(request, quote_id):
    with transaction.atomic():
        quote = get_object_or_404(quotation.objects.select_for_update(), pk=quote_id, status='accountant_review')
        quote.status = 'approved'
        quote.accountant_approved_by = request.workflow_staff
        quote.accountant_approved_at = timezone.now()
        quote.save(update_fields=('status', 'accountant_approved_by', 'accountant_approved_at', 'updated_at'))
        quote.ENQUIRY.status = 'approved'
        quote.ENQUIRY.save(update_fields=('status', 'updated_at'))
    messages.success(request, 'Final quotation approval completed.')
    return redirect('workflow_detail', enquiry_id=quote.ENQUIRY_id)


@require_POST
@role_required('Project Manager')
def approve_costing(request, quote_id):
    quote = get_object_or_404(quotation, pk=quote_id)
    cost = get_object_or_404(costing, QUOTATION=quote)
    cost.approved_by = request.workflow_staff
    cost.approved_at = timezone.now()
    cost.save(update_fields=('approved_by', 'approved_at', 'updated_at'))
    messages.success(request, 'Costing approved.')
    return redirect('workflow_detail', enquiry_id=quote.ENQUIRY_id)


@require_POST
@role_required('Document Controller')
def submit_quotation(request, quote_id):
    with transaction.atomic():
        quote = get_object_or_404(
            quotation.objects.select_for_update(), pk=quote_id, status='approved',
            costing__approved_at__isnull=False,
        )
        quote.status = 'submitted'
        quote.save(update_fields=('status', 'updated_at'))
        quote.ENQUIRY.status = 'submitted'
        quote.ENQUIRY.save(update_fields=('status', 'updated_at'))
    messages.success(request, 'Quotation marked as submitted to the client.')
    return redirect('workflow_detail', enquiry_id=quote.ENQUIRY_id)


@require_POST
@role_required('Marketing Executive')
def award_project(request, quote_id):
    with transaction.atomic():
        quote = get_object_or_404(
            quotation.objects.select_for_update(), pk=quote_id, status='submitted',
            ENQUIRY__created_by=request.workflow_account,
        )
        quote.status = 'accepted'
        quote.save(update_fields=('status', 'updated_at'))
        quote.ENQUIRY.status = 'awarded'
        quote.ENQUIRY.save(update_fields=('status', 'updated_at'))
    messages.success(request, 'Client acceptance recorded; the enquiry is ready to become a project.')
    return redirect('workflow_detail', enquiry_id=quote.ENQUIRY_id)


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
