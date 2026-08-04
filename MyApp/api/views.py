from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.auth.hashers import check_password, make_password
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
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
    costing,
    schedule,
    staff,
    supervisor_allocation,
    work,
    work_progress,
    worker_entry,
)

from .authentication import issue_token


MANAGEMENT_ROLES = frozenset(('Admin', 'Operation Manager', 'Accountant'))
GLOBAL_PROJECT_ROLES = frozenset((
    'Admin', 'Operation Manager', 'Accountant', 'Marketing Executive', 'Marketing Manager',
    'Estimator', 'Document Controller',
))
WORKFLOW_ROLES = frozenset((
    'Admin', 'Marketing Executive', 'Marketing Manager', 'Estimator',
    'Document Controller', 'Project Manager', 'Project Engineer', 'Operation Manager', 'Accountant',
))
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
        'email': account.username,
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


def _enquiry_payload(record, detailed=False):
    payload = {
        'id': record.pk,
        'title': record.title,
        'client_name': record.client_name,
        'client_email': record.client_email,
        'client_phone': record.client_phone,
        'status': record.status,
        'assigned_to': record.assigned_to.name if record.assigned_to else None,
        'created_at': _iso(record.created_at),
        'updated_at': _iso(record.updated_at),
    }
    if detailed:
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
            'quotations': [{
                'id': quote.pk,
                'version': quote.version,
                'amount': str(quote.amount),
                'status': quote.status,
                'details': quote.details,
                'created_at': _iso(quote.created_at),
            } for quote in record.quotations.all()],
        })
    return payload


class LoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (LoginThrottle,)

    def post(self, request):
        email = str(request.data.get('email', '')).strip()
        password = str(request.data.get('password', ''))
        account = login.objects.filter(username__iexact=email).first()
        if not account or not check_password(password, account.password):
            raise ValidationError({'credentials': ['Invalid email or password.']})
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
        if len(new) < 8:
            raise ValidationError({'new_password': ['Use at least 8 characters.']})
        request.user.password = make_password(new)
        request.user.api_token_version += 1
        request.user.save(update_fields=('password', 'api_token_version'))
        return Response({'message': 'Password changed. Please sign in again.'})


class DashboardView(APIView):
    def get(self, request):
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
                'unread_notifications': notices.exclude(status__iexact='read').count(),
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
        person = _person(request.user)
        queryset = notification.objects.filter(STAFF=person).select_related('PROJECT').order_by('-id') if person else notification.objects.none()
        return Response({'results': [{
            'id': item.pk, 'date': item.date, 'message': item.notification,
            'status': item.status, 'type': item.type,
            'project_id': item.PROJECT_id, 'project_name': item.PROJECT.project_name,
        } for item in queryset]})


class NotificationReadView(APIView):
    def post(self, request, notification_id):
        person = _person(request.user)
        updated = notification.objects.filter(pk=notification_id, STAFF=person).update(status='read')
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
        return Response({'results': [_enquiry_payload(item) for item in queryset]})

    def post(self, request):
        if request.user.usertype not in ('Admin', 'Marketing Executive'):
            raise PermissionDenied('Only a marketing executive can create an enquiry.')
        title = str(request.data.get('title', '')).strip()
        client_name = str(request.data.get('client_name', '')).strip()
        if not title or not client_name:
            raise ValidationError({'title': ['Title and client name are required.']})
        with transaction.atomic():
            record = enquiry.objects.create(
                title=title,
                client_name=client_name,
                client_email=str(request.data.get('client_email', '')).strip(),
                client_phone=str(request.data.get('client_phone', '')).strip(),
                description=str(request.data.get('description', '')).strip(),
                created_by=request.user,
            )
            for upload in request.FILES.getlist('files'):
                enquiry_attachment.objects.create(ENQUIRY=record, file=upload, original_name=Path(upload.name).name)
        return Response({'enquiry': _enquiry_payload(record)}, status=status.HTTP_201_CREATED)


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
        result = _enquiry_payload(record, detailed=True)
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
        item = enquiry_comment.objects.create(ENQUIRY=record, author=request.user, comment=value)
        return Response({
            'id': item.pk, 'comment': item.comment,
            'author': request.user.usertype, 'created_at': _iso(item.created_at),
        }, status=status.HTTP_201_CREATED)


def _enquiry_actions(account, record):
    actions = []
    role = _effective_role(account)
    latest = record.quotations.first()
    if role in ('Marketing Manager', 'Project Manager'):
        actions.append('assign')
    if role == 'Estimator' and record.assigned_to_id == getattr(_person(account), 'pk', None):
        actions.append('quote')
    if latest:
        if role == 'Marketing Manager' and latest.status == 'manager_review':
            actions.append('manager_approve')
        if role == 'Accountant' and latest.status == 'accountant_review':
            actions.append('accountant_approve')
        if role == 'Project Manager' and hasattr(latest, 'costing') and not latest.costing.approved_at:
            actions.append('costing_approve')
        if role == 'Document Controller' and latest.status == 'approved' and hasattr(latest, 'costing') and latest.costing.approved_at:
            actions.append('submit')
        if role == 'Marketing Executive' and record.created_by_id == account.pk and latest.status == 'submitted':
            actions.append('award')
    return actions


def _decimal(data, key):
    try:
        value = Decimal(str(data.get(key, '0')))
    except (InvalidOperation, TypeError):
        raise ValidationError({key: ['Enter a valid amount.']}) from None
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
                version = (quotation.objects.filter(ENQUIRY=record).aggregate(value=Max('version'))['value'] or 0) + 1
                quote = quotation.objects.create(
                    ENQUIRY=record, version=version, amount=amount,
                    details=str(request.data.get('details', '')).strip(), created_by=person,
                )
                costing.objects.create(
                    QUOTATION=quote,
                    material_cost=_decimal(request.data, 'material_cost'),
                    labour_cost=_decimal(request.data, 'labour_cost'),
                    other_cost=_decimal(request.data, 'other_cost'),
                    notes=str(request.data.get('costing_notes', '')).strip(),
                )
                record.status = 'quoted'
                record.save(update_fields=('status', 'updated_at'))
            else:
                latest = quotation.objects.select_for_update().filter(ENQUIRY=record).order_by('-version').first()
                if not latest:
                    raise ValidationError({'action': ['No quotation is available for this action.']})
                if action == 'manager_approve' and request.user.usertype == 'Marketing Manager' and latest.status == 'manager_review':
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
                elif action == 'submit' and request.user.usertype == 'Document Controller' and latest.status == 'approved' and costing.objects.filter(QUOTATION=latest, approved_at__isnull=False).exists():
                    latest.status = 'submitted'
                    latest.save(update_fields=('status', 'updated_at'))
                    record.status = 'submitted'
                    record.save(update_fields=('status', 'updated_at'))
                elif action == 'award' and request.user.usertype == 'Marketing Executive' and record.created_by_id == request.user.pk and latest.status == 'submitted':
                    latest.status = 'accepted'
                    latest.save(update_fields=('status', 'updated_at'))
                    record.status = 'awarded'
                    record.save(update_fields=('status', 'updated_at'))
                else:
                    raise PermissionDenied('This action is not available at the current workflow stage.')
        return Response({'enquiry': _enquiry_payload(record, detailed=True), 'message': 'Workflow updated.'})
