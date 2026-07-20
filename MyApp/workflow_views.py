from functools import wraps
from pathlib import Path
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.db.models import Max, Prefetch
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    costing, enquiry, enquiry_attachment, enquiry_comment, login,
    project_document, quotation, staff,
)


WORKFLOW_ROLES = {
    'Admin', 'Marketing Executive', 'Marketing Manager', 'Estimator',
    'Document Controller', 'Project Manager', 'Accountant',
}
UPLOAD_EXTENSIONS = ('xlsx', 'xls', 'jpg', 'jpeg', 'png', 'pdf', 'dwg', 'dxf', 'doc', 'docx')
MAX_UPLOAD_SIZE = 20 * 1024 * 1024


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
            if account.usertype not in allowed_roles:
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


def _render(request, template, context=None):
    context = context or {}
    context.update({'current_role': request.workflow_account.usertype, 'workflow_roles': WORKFLOW_ROLES})
    return render(request, template, context)


def _can_access_enquiry(request, record):
    role = request.workflow_account.usertype
    if role == 'Marketing Executive':
        return record.created_by_id == request.workflow_account.id
    if role == 'Estimator':
        return record.assigned_to_id == getattr(request.workflow_staff, 'id', None)
    return True


@role_required(*WORKFLOW_ROLES)
def dashboard(request):
    role = request.workflow_account.usertype
    records = enquiry.objects.select_related('created_by', 'assigned_to', 'PROJECT')
    if role == 'Marketing Executive':
        records = records.filter(created_by=request.workflow_account)
    elif role == 'Estimator':
        records = records.filter(assigned_to=request.workflow_staff)
    visible_records = records
    records = visible_records[:100]
    return _render(request, 'Workflow/dashboard.html', {
        'enquiries': records,
        'can_add': role == 'Marketing Executive',
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


@role_required('Marketing Executive')
def add_enquiry(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        client_name = request.POST.get('client_name', '').strip()
        if not title or not client_name:
            messages.error(request, 'Enquiry title and client name are required.')
            return _render(request, 'Workflow/enquiry_form.html')
        uploads = request.FILES.getlist('files')
        try:
            for upload in uploads:
                _validate_upload(upload)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            with transaction.atomic():
                record = enquiry.objects.create(
                    title=title,
                    client_name=client_name,
                    client_email=request.POST.get('client_email', '').strip().lower(),
                    client_phone=request.POST.get('client_phone', '').strip(),
                    description=request.POST.get('description', '').strip(),
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
    record = get_object_or_404(
        enquiry.objects.select_related('created_by', 'assigned_to', 'PROJECT').prefetch_related(
            'attachments', 'comments__author', 'project_documents__verified_by',
            Prefetch('quotations', queryset=quotation.objects.select_related(
                'created_by', 'manager_approved_by', 'accountant_approved_by',
                'costing', 'costing__approved_by',
            )),
        ), pk=enquiry_id,
    )
    role = request.workflow_account.usertype
    if not _can_access_enquiry(request, record):
        return HttpResponseForbidden('You do not have permission to view this enquiry.')
    return _render(request, 'Workflow/enquiry_detail.html', {
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
    })


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
    record = get_object_or_404(enquiry, pk=enquiry_id, assigned_to=request.workflow_staff)
    upload = request.FILES.get('file')
    if upload:
        try:
            _validate_upload(upload)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect('workflow_detail', enquiry_id=enquiry_id)
    try:
        amount = _non_negative_decimal(request, 'amount', 'Quotation amount')
        material_amount = _non_negative_decimal(request, 'material_cost', 'Material cost')
        labour_amount = _non_negative_decimal(request, 'labour_cost', 'Labour cost')
        other_amount = _non_negative_decimal(request, 'other_cost', 'Other cost')
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect('workflow_detail', enquiry_id=enquiry_id)
    if amount <= 0:
        messages.error(request, 'Quotation amount must be greater than zero.')
        return redirect('workflow_detail', enquiry_id=enquiry_id)
    with transaction.atomic():
        version = (quotation.objects.filter(ENQUIRY=record).aggregate(v=Max('version'))['v'] or 0) + 1
        quote = quotation.objects.create(
            ENQUIRY=record, version=version, amount=amount,
            details=request.POST.get('details', '').strip(), file=upload or '', created_by=request.workflow_staff,
        )
        costing.objects.create(
            QUOTATION=quote,
            material_cost=material_amount,
            labour_cost=labour_amount,
            other_cost=other_amount,
            notes=request.POST.get('costing_notes', '').strip(),
        )
        record.status = 'quoted'
        record.save(update_fields=('status', 'updated_at'))
    messages.success(request, 'Quotation and costing sent for Marketing Manager approval.')
    return redirect('workflow_detail', enquiry_id=enquiry_id)


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
    upload = request.FILES.get('file')
    if not upload:
        messages.error(request, 'Select a document to upload.')
    else:
        try:
            _validate_upload(upload)
            project_document.objects.create(
                ENQUIRY=record, file=upload, document_type=request.POST.get('document_type', 'client'),
                collected_by=request.workflow_account,
            )
            messages.success(request, 'Client project document collected.')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
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
