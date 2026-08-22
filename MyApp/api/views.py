from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password as validate_django_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from MyApp.models import (
    CAD_FILE_EXTENSIONS,
    chat,
    enquiry,
    enquiry_attachment,
    enquiry_comment,
    login,
    material,
    material_issued,
    material_request,
    material_required,
    material_usage,
    notification,
    photo,
    project,
    quotation,
    quotation_line,
    costing,
    schedule,
    staff,
    supervisor_allocation,
    work,
    work_progress,
    worker_entry,
    workflow_notification,
)
from MyApp.quotation_document import (
    quotation_internal_review, quotation_tracking, unpack_document,
    update_quotation_internal_review, update_quotation_tracking,
)
from MyApp.quotation_activity import publish_client_response, publish_quotation_message
from MyApp.quotation_email import QuotationDeliveryError, send_quotation_to_client

from .authentication import issue_token
from MyApp.deadline_notifications import ensure_quotation_deadline_notifications
from MyApp.quotation_numbers import assign_quotation_reference


MANAGEMENT_ROLES = frozenset(('Admin', 'Operation Manager', 'Accountant'))
GLOBAL_PROJECT_ROLES = frozenset((
    'Admin', 'Operation Manager', 'Accountant', 'Marketing Executive', 'Marketing Manager',
    'Estimator', 'Document Controller',
))
WORKFLOW_ROLES = frozenset((
    'Admin', 'Marketing Executive', 'Marketing Manager', 'Estimator',
    'Document Controller', 'Project Manager', 'Project Engineer', 'Operation Manager', 'Accountant',
))
CLIENT_RESPONSE_STATUSES = {
    'under_review': 'Under Review',
    'under_revision': 'Under Revision',
    'approved': 'Approved',
    'rejected': 'Rejected',
}
SITE_WRITE_ROLES = frozenset(('Supervisor',))


class LoginThrottle(AnonRateThrottle):
    scope = 'login'


def _person(account):
    return staff.objects.filter(LOGIN=account).first()


def _effective_role(account):
    if account.usertype in ('Project Engineer', 'Operation Manager'):
        return 'Project Manager'
    return account.usertype


def _user_payload(account):
    person = _person(account)
    return {
        'id': account.pk,
        'username': account.username,
        'email': person.email if person else '',
        'role': account.usertype,
        'staff_id': person.pk if person else None,
        'name': person.name if person else account.username,
        'phone': person.phone if person else '',
        'photo': person.photo if person else '',
        'place': person.place if person else '',
    }


def _project_queryset(account):
    queryset = project.objects.all()
    if account.usertype in GLOBAL_PROJECT_ROLES:
        return queryset
    person = _person(account)
    if not person:
        return queryset.none()
    if account.usertype in ('Project Manager', 'Project Engineer'):
        return queryset.filter(project_manager_allocation__STAFF=person)
    if account.usertype == 'Supervisor':
        return queryset.filter(supervisor_allocation__STAFF=person)
    if account.usertype == 'Purchaser':
        return queryset.filter(purchaser_project_allocation__STAFF=person)
    return queryset.none()


def _project_for(account, project_id):
    try:
        return _project_queryset(account).distinct().get(pk=project_id)
    except project.DoesNotExist:
        raise NotFound('Project not found.') from None


def _project_payload(record):
    latest = record.work_progress_set.order_by('-date', '-id').first()
    return {
        'id': record.pk,
        'project_no': record.project_no,
        'name': record.project_name,
        'client_name': record.client_name,
        'place': record.place,
        'status': record.status,
        'start_date': record.start_date,
        'handout_date': record.handout_date,
        'duration': record.project_duration,
        'area': record.project_area,
        'type': record.project_type,
        'value': record.project_value,
        'description': record.description,
        'latest_progress': latest.progress if latest else '',
        'latest_progress_status': latest.status if latest else '',
    }


def _iso(value):
    return value.isoformat() if value else None


def _enquiry_allowed(account, record):
    if account.usertype not in WORKFLOW_ROLES:
        return False
    if account.usertype == 'Marketing Executive':
        return record.created_by_id == account.pk
    if account.usertype == 'Estimator':
        person = _person(account)
        return bool(person and record.assigned_to_id == person.pk)
    return True


def _quotation_payload(quote, account=None):
    tracking = quotation_tracking(quote.details, quote.validity_days)
    document = unpack_document(quote.details, quote.validity_days)
    client = document.get('client') or {}
    submitted = bool(tracking['submitted_at'])
    internal_stage = quotation_internal_review(quote.details, quote.validity_days)
    restricted_for_marketing = bool(
        account and account.usertype == 'Marketing Executive'
        and (
            quote.status in ('manager_review', 'accountant_review')
            or (quote.status == 'under_revision' and not quote.accountant_approved_at)
        )
    )
    return {
        'id': quote.pk,
        'version': quote.version,
        'quotation_number': quote.display_number,
        'revision': quote.revision,
        'amount': str(quote.amount),
        'status': quote.status,
        'details': '' if restricted_for_marketing else quote.details,
        'content_available': not restricted_for_marketing,
        'submitted_at': tracking['submitted_at'] or None,
        'client_remarks': tracking['client_remarks'] if submitted else '',
        'client_status': tracking['client_status'] if submitted else None,
        'internal_revision_stage': internal_stage or None,
        'client': {
            'name': client.get('name', quote.ENQUIRY.client_name),
            'phone': client.get('phone', quote.ENQUIRY.client_phone),
            'email': client.get('email', quote.ENQUIRY.client_email),
            'address': quote.client_address,
        },
        'created_at': _iso(quote.created_at),
    }


def _enquiry_payload(record, detailed=False, account=None):
    payload = {
        'id': record.pk,
        'title': record.title,
        'client_name': record.client_name,
        'client_email': record.client_email,
        'client_phone': record.client_phone,
        'status': record.status,
        'assigned_to': record.assigned_to.name if record.assigned_to else None,
        'quotation_deadline': _iso(record.quotation_deadline),
        'created_at': _iso(record.created_at),
        'updated_at': _iso(record.updated_at),
    }
    if account and account.usertype == 'Marketing Executive':
        payload['quotation_statuses'] = [
            {
                'id': quote.pk, 'number': quote.display_number,
                'issue_date': _iso(quote.issue_date), 'status': quote.status,
            }
            for quote in record.quotations.all()
            if quote.status in ('manager_review', 'accountant_review', 'under_revision')
        ]
    if detailed:
        quotations = record.quotations.all()
        if account and account.usertype == 'Marketing Executive':
            quotations = quotations.filter(
                status__in=(
                    'manager_review', 'accountant_review', 'approved', 'submitted',
                    'accepted', 'rejected', 'under_revision',
                )
            )
        payload.update({
            'description': record.description,
            'project_id': record.PROJECT_id,
            'attachments': [{
                'id': item.pk,
                'name': item.original_name,
                'url': item.file.url,
                'is_cad': Path(item.original_name).suffix.lower() in CAD_FILE_EXTENSIONS,
            } for item in record.attachments.all()],
            'comments': [{
                'id': item.pk,
                'author': item.author.usertype,
                'comment': item.comment,
                'created_at': _iso(item.created_at),
            } for item in record.comments.select_related('author')],
            'quotations': [_quotation_payload(quote, account=account) for quote in quotations],
        })
    return payload


class LoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (LoginThrottle,)

    def post(self, request):
        # Keep accepting the legacy ``email`` key so already-installed mobile
        # clients continue to work while new clients send ``username``.
        username = str(
            request.data.get('username') or request.data.get('email') or ''
        ).strip().lower()
        password = str(request.data.get('password', ''))
        account = login.objects.filter(username__iexact=username).first()
        if not account or not check_password(password, account.password):
            raise ValidationError({'credentials': ['Invalid username or password.']})
        return Response({'token': issue_token(account), 'user': _user_payload(account)})


class LogoutView(APIView):
    def post(self, request):
        request.user.api_token_version += 1
        request.user.save(update_fields=('api_token_version',))
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response({'user': _user_payload(request.user)})

    def patch(self, request):
        current = str(request.data.get('current_password', ''))
        new = str(request.data.get('new_password', ''))
        if not check_password(current, request.user.password):
            raise ValidationError({'current_password': ['The current password is incorrect.']})
        try:
            validate_django_password(new, request.user)
        except DjangoValidationError as exc:
            raise ValidationError({'new_password': exc.messages}) from exc
        request.user.password = make_password(new)
        request.user.api_token_version += 1
        request.user.save(update_fields=('password', 'api_token_version'))
        return Response({'message': 'Password changed. Please sign in again.'})


class DashboardView(APIView):
    def get(self, request):
        ensure_quotation_deadline_notifications()
        projects = _project_queryset(request.user).distinct()
        person = _person(request.user)
        pending_requests = material_request.objects.filter(PROJECT__in=projects, status__iexact='pending')
        notices = notification.objects.filter(STAFF=person) if person else notification.objects.none()
        enquiries = enquiry.objects.none()
        if request.user.usertype in WORKFLOW_ROLES:
            enquiries = enquiry.objects.all()
            if request.user.usertype == 'Marketing Executive':
                enquiries = enquiries.filter(created_by=request.user)
            elif request.user.usertype == 'Estimator' and person:
                enquiries = enquiries.filter(assigned_to=person)
        return Response({
            'user': _user_payload(request.user),
            'metrics': {
                'projects': projects.count(),
                'ongoing_projects': projects.filter(status__iexact='ongoing').count(),
                'pending_material_requests': pending_requests.count(),
                'unread_notifications': (
                    notices.exclude(status__iexact='read').count()
                    + workflow_notification.objects.filter(
                        recipient=request.user, read_at__isnull=True,
                    ).count()
                ),
                'open_enquiries': enquiries.exclude(status__in=('closed', 'awarded')).count(),
            },
            'recent_projects': [_project_payload(item) for item in projects.order_by('-id')[:5]],
        })


class MaterialListView(APIView):
    def get(self, request):
        items = material.objects.order_by('name').values('id', 'name', 'unit')
        return Response({'results': list(items)})


class ProjectListView(APIView):
    def get(self, request):
        queryset = _project_queryset(request.user).distinct().order_by('-id')
        query = str(request.query_params.get('q', '')).strip()
        project_status = str(request.query_params.get('status', '')).strip()
        if query:
            queryset = queryset.filter(
                Q(project_name__icontains=query) | Q(project_no__icontains=query)
                | Q(client_name__icontains=query) | Q(place__icontains=query)
            )
        if project_status:
            queryset = queryset.filter(status__iexact=project_status)
        return Response({'results': [_project_payload(item) for item in queryset]})


class ProjectDetailView(APIView):
    def get(self, request, project_id):
        record = _project_for(request.user, project_id)
        works = work.objects.filter(PROJECT=record).order_by('category', 'workname')
        return Response({
            'project': _project_payload(record),
            'works': [{
                'id': item.pk, 'category': item.category, 'name': item.workname,
                'schedules': [{
                    'id': row.pk, 'from_date': _iso(row.from_date), 'to_date': _iso(row.to_date),
                } for row in schedule.objects.filter(PROJECT=record, WORK=item)],
            } for item in works],
            'progress': list(work_progress.objects.filter(PROJECT=record).order_by('-date', '-id').values(
                'id', 'date', 'status', 'progress', 'WORK_id', 'WORK__workname'
            )),
            'materials_required': list(material_required.objects.filter(PROJECT=record).values(
                'id', 'quantity', 'price', 'category', 'MATERIAL_id', 'MATERIAL__name', 'MATERIAL__unit'
            )),
            'material_requests': list(material_request.objects.filter(PROJECT=record).order_by('-id').values(
                'id', 'quantity', 'status', 'date', 'MATERIAL_id', 'MATERIAL__name', 'MATERIAL__unit', 'STAFF__name'
            )),
            'material_issues': list(material_issued.objects.filter(PROJECT=record).order_by('-id').values(
                'id', 'date', 'quantity_issued', 'status', 'MATERIAL__name', 'MATERIAL__unit', 'STAFF__name'
            )),
            'team': {
                'project_managers': list(staff.objects.filter(project_manager_allocation__PROJECT=record).values('id', 'name', 'phone', 'email')),
                'supervisors': list(staff.objects.filter(supervisor_allocation__PROJECT=record).values('id', 'name', 'phone', 'email')),
                'purchasers': list(staff.objects.filter(purchaser_project_allocation__PROJECT=record).values('id', 'name', 'phone', 'email')),
            },
            'capabilities': {
                'site_updates': request.user.usertype in SITE_WRITE_ROLES,
                'approve_material_requests': request.user.usertype in ('Admin', 'Operation Manager', 'Project Manager', 'Project Engineer'),
                'chat': True,
            },
        })


class ProjectChatView(APIView):
    def get(self, request, project_id):
        record = _project_for(request.user, project_id)
        people = dict(staff.objects.values_list('LOGIN_id', 'name'))
        results = [{
            'id': item.pk,
            'message': item.message,
            'date': item.date,
            'time': item.time,
            'sender_id': item.LOGIN_id,
            'sender_name': people.get(item.LOGIN_id, item.LOGIN.usertype),
            'mine': item.LOGIN_id == request.user.pk,
        } for item in chat.objects.filter(PROJECT=record).select_related('LOGIN').order_by('id')]
        return Response({'results': results})

    def post(self, request, project_id):
        record = _project_for(request.user, project_id)
        message = str(request.data.get('message', '')).strip()
        if not message:
            raise ValidationError({'message': ['A message is required.']})
        now = timezone.localtime()
        item = chat.objects.create(
            type=request.user.usertype,
            message=message[:500],
            date=now.date().isoformat(),
            time=now.strftime('%H:%M'),
            PROJECT=record,
            LOGIN=request.user,
        )
        return Response({'id': item.pk, 'message': item.message}, status=status.HTTP_201_CREATED)


class SiteUpdateView(APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def post(self, request, project_id):
        record = _project_for(request.user, project_id)
        if request.user.usertype not in SITE_WRITE_ROLES:
            raise PermissionDenied('Only an allocated supervisor can submit site updates.')
        person = _person(request.user)
        update_type = str(request.data.get('type', '')).strip()
        update_date = str(request.data.get('date') or date.today().isoformat())
        with transaction.atomic():
            if update_type == 'material_usage':
                item = material_usage.objects.create(
                    date=update_date,
                    quantity=str(request.data.get('quantity', '')).strip(),
                    PROJECT=record,
                    STAFF=person,
                    MATERIAL_id=request.data.get('material_id'),
                )
            elif update_type == 'workers':
                item = worker_entry.objects.create(
                    date=update_date,
                    work_type=str(request.data.get('work_type', '')).strip(),
                    worker_count=str(request.data.get('worker_count', '')).strip(),
                    PROJECT=record,
                )
            elif update_type == 'progress':
                item = work_progress.objects.create(
                    date=update_date,
                    status=str(request.data.get('status', '')).strip(),
                    progress=str(request.data.get('progress', '')).strip(),
                    PROJECT=record,
                    WORK_id=request.data.get('work_id'),
                )
            elif update_type == 'material_request':
                item = material_request.objects.create(
                    date=update_date,
                    quantity=str(request.data.get('quantity', '')).strip(),
                    status='pending',
                    PROJECT=record,
                    STAFF=person,
                    MATERIAL_id=request.data.get('material_id'),
                )
            elif update_type == 'photo':
                upload = request.FILES.get('photo')
                if not upload or not str(upload.content_type).startswith('image/'):
                    raise ValidationError({'photo': ['Select a valid image.']})
                allocation = supervisor_allocation.objects.filter(PROJECT=record, STAFF=person).first()
                if not allocation:
                    raise PermissionDenied('You are not allocated to this project.')
                stored = default_storage.save(f'site_photos/{record.pk}/{Path(upload.name).name}', upload)
                item = photo.objects.create(
                    date=update_date, photo=default_storage.url(stored),
                    ALLOCATION=allocation, PROJECT=record,
                )
            else:
                raise ValidationError({'type': ['Unsupported site update type.']})
        return Response({'id': item.pk, 'message': 'Site update saved.'}, status=status.HTTP_201_CREATED)


class MaterialRequestDecisionView(APIView):
    def post(self, request, request_id, decision):
        if request.user.usertype not in ('Admin', 'Operation Manager', 'Project Manager', 'Project Engineer'):
            raise PermissionDenied('Only a project manager can review material requests.')
        if decision not in ('approve', 'reject'):
            raise ValidationError({'decision': ['Use approve or reject.']})
        try:
            item = material_request.objects.select_related('PROJECT').get(pk=request_id)
        except material_request.DoesNotExist:
            raise NotFound('Material request not found.') from None
        _project_for(request.user, item.PROJECT_id)
        item.status = 'approved' if decision == 'approve' else 'rejected'
        item.save(update_fields=('status',))
        return Response({'id': item.pk, 'status': item.status})


class NotificationListView(APIView):
    def get(self, request):
        ensure_quotation_deadline_notifications()
        person = _person(request.user)
        queryset = notification.objects.filter(STAFF=person).select_related('PROJECT').order_by('-id') if person else notification.objects.none()
        project_notices = [{
            'id': f'project:{item.pk}', 'date': item.date, 'message': item.notification,
            'status': item.status, 'type': item.type,
            'project_id': item.PROJECT_id, 'project_name': item.PROJECT.project_name,
            'enquiry_id': None, 'link': None,
        } for item in queryset]
        workflow_notices = [{
            'id': f'workflow:{item.pk}',
            'date': _iso(item.created_at),
            'message': item.message,
            'status': item.status,
            'type': {
                'enquiry_comment': 'Enquiry discussion',
                'quotation_comment': 'Quotation discussion',
                'quotation_deadline': 'Quotation deadline',
            }.get(item.event, 'Workflow alert'),
            'event': item.event,
            'project_id': None,
            'project_name': item.ENQUIRY.title if item.ENQUIRY else 'Enquiry workflow',
            'enquiry_id': item.ENQUIRY_id,
            'link': item.link,
        } for item in workflow_notification.objects.filter(
            recipient=request.user,
        ).select_related('ENQUIRY')]
        results = workflow_notices + project_notices
        return Response({'results': results})


class NotificationReadView(APIView):
    def post(self, request, notification_id):
        try:
            source, raw_id = notification_id.split(':', 1)
            item_id = int(raw_id)
        except (AttributeError, TypeError, ValueError):
            source, item_id = 'project', notification_id
        if source not in ('project', 'workflow') or not str(item_id).isdigit():
            raise ValidationError({'notification_id': ['Use project:<id> or workflow:<id>.']})
        item_id = int(item_id)
        if source == 'workflow':
            updated = workflow_notification.objects.filter(
                pk=item_id, recipient=request.user,
            ).update(read_at=timezone.now())
        else:
            person = _person(request.user)
            updated = notification.objects.filter(pk=item_id, STAFF=person).update(status='read')
        if not updated:
            raise NotFound('Notification not found.')
        return Response({'id': notification_id, 'status': 'read'})


class EnquiryListView(APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def get(self, request):
        if request.user.usertype not in WORKFLOW_ROLES:
            raise PermissionDenied('This role does not use the enquiry workflow.')
        queryset = enquiry.objects.select_related('assigned_to').order_by('-created_at')
        if request.user.usertype == 'Marketing Executive':
            queryset = queryset.filter(created_by=request.user)
        elif request.user.usertype == 'Estimator':
            queryset = queryset.filter(assigned_to=_person(request.user))
        return Response({'results': [_enquiry_payload(item, account=request.user) for item in queryset]})

    def post(self, request):
        if request.user.usertype not in ('Admin', 'Marketing Executive', 'Marketing Manager'):
            raise PermissionDenied('Only the marketing team can create an enquiry.')
        title = str(request.data.get('title', '')).strip()
        client_name = str(request.data.get('client_name', '')).strip()
        if not title or not client_name:
            raise ValidationError({'title': ['Title and client name are required.']})
        deadline_value = str(request.data.get('quotation_deadline', '')).strip()
        deadline = parse_datetime(deadline_value)
        if not deadline:
            deadline_date = parse_date(deadline_value)
            if deadline_date:
                deadline = timezone.make_aware(
                    datetime.combine(deadline_date, time.max), timezone.get_current_timezone(),
                )
        if not deadline:
            raise ValidationError({'quotation_deadline': ['A quotation submission deadline is required.']})
        if timezone.is_naive(deadline):
            deadline = timezone.make_aware(deadline, timezone.get_current_timezone())
        if deadline <= timezone.now():
            raise ValidationError({'quotation_deadline': ['The deadline must be in the future.']})
        with transaction.atomic():
            record = enquiry.objects.create(
                title=title,
                client_name=client_name,
                client_email=str(request.data.get('client_email', '')).strip(),
                client_phone=str(request.data.get('client_phone', '')).strip(),
                description=str(request.data.get('description', '')).strip(),
                quotation_deadline=deadline,
                created_by=request.user,
            )
            for upload in request.FILES.getlist('files'):
                enquiry_attachment.objects.create(ENQUIRY=record, file=upload, original_name=Path(upload.name).name)
        return Response({'enquiry': _enquiry_payload(record, account=request.user)}, status=status.HTTP_201_CREATED)


class EnquiryDetailView(APIView):
    def get(self, request, enquiry_id):
        try:
            record = enquiry.objects.select_related('assigned_to').prefetch_related(
                'attachments', 'comments__author', 'quotations'
            ).get(pk=enquiry_id)
        except enquiry.DoesNotExist:
            raise NotFound('Enquiry not found.') from None
        if not _enquiry_allowed(request.user, record):
            raise PermissionDenied('You cannot access this enquiry.')
        result = _enquiry_payload(record, detailed=True, account=request.user)
        result['available_actions'] = _enquiry_actions(request.user, record)
        if _effective_role(request.user) in ('Marketing Manager', 'Project Manager'):
            result['estimators'] = list(staff.objects.filter(designation='Estimator').values('id', 'name'))
        return Response({'enquiry': result})


class EnquiryCommentView(APIView):
    def post(self, request, enquiry_id):
        try:
            record = enquiry.objects.get(pk=enquiry_id)
        except enquiry.DoesNotExist:
            raise NotFound('Enquiry not found.') from None
        if not _enquiry_allowed(request.user, record):
            raise PermissionDenied('You cannot access this enquiry.')
        value = str(request.data.get('comment', '')).strip()
        if not value:
            raise ValidationError({'comment': ['A comment is required.']})
        parent_id = str(request.data.get('parent_id', '')).strip()
        parent_prefix = ''
        if parent_id:
            if not parent_id.isdigit() or not record.comments.filter(pk=int(parent_id)).exists():
                raise ValidationError({'parent_id': ['The message being replied to is unavailable.']})
            parent_prefix = f'[REPLY:{parent_id}] '
        item = enquiry_comment.objects.create(
            ENQUIRY=record, author=request.user,
            comment=f'[ENQ:{record.pk}] {parent_prefix}{value}',
        )
        recipient_ids = {record.created_by_id}
        if record.assigned_to_id and record.assigned_to.LOGIN_id:
            recipient_ids.add(record.assigned_to.LOGIN_id)
        recipient_ids.update(login.objects.filter(
            usertype__in=('Marketing Manager', 'Accountant'),
        ).values_list('id', flat=True))
        for recipient_id in recipient_ids - {request.user.pk}:
            workflow_notification.objects.get_or_create(
                dedupe_key=f'enquiry-comment:{item.pk}:{recipient_id}',
                defaults={
                    'recipient_id': recipient_id, 'ENQUIRY': record,
                    'event': 'enquiry_comment', 'level': 'info',
                    'message': f'New discussion message on enquiry {record.title}.',
                    'link': f'/WMS/workflow/enquiries/{record.pk}/discussion/',
                },
            )
        return Response({
            'id': item.pk, 'comment': value, 'parent_id': int(parent_id) if parent_id else None,
            'author': request.user.usertype, 'created_at': _iso(item.created_at),
        }, status=status.HTTP_201_CREATED)


def _enquiry_actions(account, record):
    actions = []
    role = _effective_role(account)
    latest = record.quotations.first()
    if role in ('Marketing Manager', 'Project Manager'):
        actions.append('assign')
    if role == 'Estimator' and record.assigned_to_id == getattr(_person(account), 'pk', None):
        if latest and latest.status == 'draft' and latest.created_by_id == getattr(_person(account), 'pk', None):
            actions.append('submit_for_approval')
        else:
            actions.append('quote')
    if latest:
        if role == 'Marketing Manager' and latest.status == 'manager_review':
            actions.append('manager_approve')
            actions.append('request_revision')
        if role == 'Accountant' and latest.status == 'accountant_review':
            actions.append('accountant_approve')
            actions.append('request_revision')
        if role == 'Project Manager' and hasattr(latest, 'costing') and not latest.costing.approved_at:
            actions.append('costing_approve')
        if role in ('Document Controller', 'Marketing Executive', 'Marketing Manager') and latest.status == 'approved':
            actions.append('submit')
        if role in ('Marketing Executive', 'Marketing Manager') and latest.status == 'submitted':
            actions.append('award')
        if role in ('Admin', 'Marketing Executive', 'Marketing Manager') and latest.status in ('submitted', 'rejected', 'under_revision'):
            actions.append('client_response')
    return actions


def _decimal(data, key):
    try:
        value = Decimal(str(data.get(key, '0')))
    except (InvalidOperation, TypeError):
        raise ValidationError({key: ['Enter a valid amount.']}) from None
    if not value.is_finite():
        raise ValidationError({key: ['Enter a finite amount.']})
    if value < 0:
        raise ValidationError({key: ['Amount cannot be negative.']})
    return value


class EnquiryActionView(APIView):
    """Execute state transitions while preserving the web workflow's approval order."""

    def post(self, request, enquiry_id, action):
        try:
            record = enquiry.objects.prefetch_related('quotations__costing').get(pk=enquiry_id)
        except enquiry.DoesNotExist:
            raise NotFound('Enquiry not found.') from None
        if not _enquiry_allowed(request.user, record):
            raise PermissionDenied('You cannot access this enquiry.')
        person = _person(request.user)
        workflow_message = 'Workflow updated.'
        with transaction.atomic():
            effective_role = _effective_role(request.user)
            if action == 'assign' and effective_role in ('Marketing Manager', 'Project Manager'):
                estimator = staff.objects.filter(pk=request.data.get('estimator_id'), designation='Estimator').first()
                if not estimator:
                    raise ValidationError({'estimator_id': ['Select a valid estimator.']})
                record.assigned_to = estimator
                record.status = 'assigned'
                record.save(update_fields=('assigned_to', 'status', 'updated_at'))
            elif action == 'quote' and request.user.usertype == 'Estimator' and record.assigned_to_id == getattr(person, 'pk', None):
                amount = _decimal(request.data, 'amount')
                if amount <= 0:
                    raise ValidationError({'amount': ['Quotation amount must be greater than zero.']})
                existing_quotes = quotation.objects.select_for_update().filter(ENQUIRY=record)
                latest = existing_quotes.order_by('-version').first()
                is_internal_return = bool(
                    latest and latest.status == 'under_revision'
                    and latest.created_by_id == getattr(person, 'pk', None)
                    and quotation_internal_review(latest.details, latest.validity_days)
                )
                if is_internal_return:
                    quote = latest
                    quote.amount = amount
                    quote.subject = str(request.data.get('subject', '')).strip() or f'Quotation for {record.title}'
                    quote.details = str(request.data.get('details', '')).strip()
                    quote.status = 'draft'
                    quote.save(update_fields=('amount', 'subject', 'details', 'status', 'updated_at'))
                    quote.lines.all().delete()
                else:
                    version = (existing_quotes.aggregate(value=Max('version'))['value'] or 0) + 1
                    first_quote = existing_quotes.order_by('version', 'id').first()
                    revision = (existing_quotes.aggregate(value=Max('revision'))['value'] or 0) + 1 if first_quote else 0
                    quote = quotation.objects.create(
                        ENQUIRY=record, version=version, revision=revision, amount=amount,
                        subject=str(request.data.get('subject', '')).strip() or f'Quotation for {record.title}',
                        details=str(request.data.get('details', '')).strip(), created_by=person,
                        status='draft',
                    )
                    assign_quotation_reference(quote, first_quote)
                quotation_line.objects.create(
                    QUOTATION=quote,
                    description=quote.details or 'Quotation total',
                    unit='lot', quantity=1, unit_rate=amount, amount=amount, position=1,
                )
                costing.objects.update_or_create(
                    QUOTATION=quote,
                    defaults={
                        'material_cost': _decimal(request.data, 'material_cost'),
                        'labour_cost': _decimal(request.data, 'labour_cost'),
                        'other_cost': _decimal(request.data, 'other_cost'),
                        'notes': str(request.data.get('costing_notes', '')).strip(),
                    },
                )
            else:
                latest = quotation.objects.select_for_update().filter(ENQUIRY=record).order_by('-version').first()
                if not latest:
                    raise ValidationError({'action': ['No quotation is available for this action.']})
                if action == 'submit_for_approval' and request.user.usertype == 'Estimator' and latest.status == 'draft' and latest.created_by_id == getattr(person, 'pk', None):
                    latest.status = 'manager_review'
                    latest.save(update_fields=('status', 'updated_at'))
                    record.status = 'quoted'
                    record.save(update_fields=('status', 'updated_at'))
                elif action == 'request_revision' and request.user.usertype in ('Marketing Manager', 'Accountant') and latest.status in ('manager_review', 'accountant_review'):
                    remarks = str(request.data.get('remarks', '')).strip()
                    if not remarks:
                        raise ValidationError({'remarks': ['Explain what the estimator must correct.']})
                    if len(remarks) > 2000:
                        raise ValidationError({'remarks': ['Revision request cannot exceed 2,000 characters.']})
                    latest.status = 'under_revision'
                    latest.details = update_quotation_internal_review(
                        latest.details, latest.validity_days,
                        stage='manager' if request.user.usertype == 'Marketing Manager' else 'accountant',
                    )
                    update_fields = ['status', 'details', 'updated_at']
                    if request.user.usertype == 'Marketing Manager':
                        latest.manager_approved_by = None
                        latest.manager_approved_at = None
                        update_fields.extend(['manager_approved_by', 'manager_approved_at'])
                    else:
                        latest.accountant_approved_by = None
                        latest.accountant_approved_at = None
                        update_fields.extend(['accountant_approved_by', 'accountant_approved_at'])
                    latest.save(update_fields=update_fields)
                    record.status = 'quoted'
                    record.save(update_fields=('status', 'updated_at'))
                    publish_quotation_message(
                        latest, request.user,
                        f'{request.user.usertype} requested quotation revision.\nRevision request: {remarks}',
                    )
                    workflow_message = 'Revision request sent to the estimator.'
                elif action == 'manager_approve' and request.user.usertype == 'Marketing Manager' and latest.status == 'manager_review':
                    latest.status = 'accountant_review'
                    latest.manager_approved_by = person
                    latest.manager_approved_at = timezone.now()
                    latest.save(update_fields=('status', 'manager_approved_by', 'manager_approved_at', 'updated_at'))
                elif action == 'accountant_approve' and request.user.usertype == 'Accountant' and latest.status == 'accountant_review':
                    latest.status = 'approved'
                    latest.accountant_approved_by = person
                    latest.accountant_approved_at = timezone.now()
                    latest.save(update_fields=('status', 'accountant_approved_by', 'accountant_approved_at', 'updated_at'))
                    record.status = 'approved'
                    record.save(update_fields=('status', 'updated_at'))
                elif action == 'costing_approve' and effective_role == 'Project Manager':
                    cost = costing.objects.filter(QUOTATION=latest).first()
                    if not cost:
                        raise ValidationError({'action': ['No costing is attached.']})
                    cost.approved_by = person
                    cost.approved_at = timezone.now()
                    cost.save(update_fields=('approved_by', 'approved_at', 'updated_at'))
                elif action == 'submit' and request.user.usertype in ('Document Controller', 'Marketing Executive', 'Marketing Manager') and latest.status == 'approved':
                    try:
                        recipient = send_quotation_to_client(latest)
                    except QuotationDeliveryError as exc:
                        raise ValidationError({'email': [str(exc)]}) from exc
                    latest.status = 'submitted'
                    latest.details = update_quotation_tracking(
                        latest.details, latest.validity_days,
                        submitted_at=timezone.now().isoformat(), client_status='under_review',
                    )
                    latest.save(update_fields=('status', 'details', 'updated_at'))
                    record.status = 'submitted'
                    record.save(update_fields=('status', 'updated_at'))
                    workflow_message = (
                        f'Quotation emailed successfully to {recipient}; '
                        'client status is now Under Review.'
                    )
                elif action == 'client_response' and request.user.usertype in ('Admin', 'Marketing Executive', 'Marketing Manager') and latest.status in ('submitted', 'rejected', 'under_revision'):
                    if latest.status == 'under_revision' and quotation_internal_review(
                        latest.details, latest.validity_days,
                    ):
                        raise ValidationError({'action': ['Internal revisions do not change client response details.']})
                    client_status = str(request.data.get('client_status', 'under_review')).strip()
                    if client_status not in CLIENT_RESPONSE_STATUSES:
                        raise ValidationError({'client_status': ['Select a valid client response status.']})
                    if client_status == 'under_revision' and request.user.usertype not in ('Admin', 'Marketing Manager'):
                        raise PermissionDenied('Only a Marketing Manager or Admin can request a client revision.')
                    client_remarks = str(request.data.get('client_remarks', '')).strip()
                    if len(client_remarks) > 2000:
                        raise ValidationError({'client_remarks': ['Client remarks cannot exceed 2,000 characters.']})
                    latest.details = update_quotation_tracking(
                        latest.details, latest.validity_days,
                        client_status=client_status, client_remarks=client_remarks,
                    )
                    latest.status = {
                        'under_review': 'submitted', 'under_revision': 'under_revision',
                        'approved': 'accepted', 'rejected': 'rejected',
                    }[client_status]
                    latest.save(update_fields=('details', 'status', 'updated_at'))
                    record.status = 'awarded' if client_status == 'approved' else (
                        'submitted' if client_status in ('under_review', 'under_revision') else 'quoted'
                    )
                    record.save(update_fields=('status', 'updated_at'))
                    publish_client_response(latest, request.user, client_status, client_remarks)
                    workflow_message = f'Client response recorded as {CLIENT_RESPONSE_STATUSES[client_status]}.'
                elif action == 'award' and request.user.usertype in ('Marketing Executive', 'Marketing Manager') and latest.status == 'submitted':
                    latest.status = 'accepted'
                    latest.details = update_quotation_tracking(
                        latest.details, latest.validity_days, client_status='approved',
                    )
                    latest.save(update_fields=('status', 'details', 'updated_at'))
                    record.status = 'awarded'
                    record.save(update_fields=('status', 'updated_at'))
                    publish_client_response(latest, request.user, 'approved')
                else:
                    raise PermissionDenied('This action is not available at the current workflow stage.')
        return Response({
            'enquiry': _enquiry_payload(record, detailed=True, account=request.user),
            'message': workflow_message,
        })
