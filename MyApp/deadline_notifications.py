from datetime import timedelta

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import enquiry, login, workflow_notification


DEADLINE_RECIPIENT_ROLES = (
    'Admin', 'Operation Manager', 'Marketing Manager', 'Document Controller',
)
INACTIVE_ENQUIRY_STATUSES = ('submitted', 'awarded', 'closed')


def _deadline_stage(deadline, now):
    remaining = deadline - now
    if remaining.total_seconds() < 0:
        return 'overdue', 'danger', 'is overdue'
    if remaining <= timedelta(days=1):
        return 'one_day', 'danger', 'is due within 24 hours'
    if remaining <= timedelta(days=3):
        return 'three_days', 'warning', 'is due within 3 days'
    if remaining <= timedelta(days=7):
        return 'seven_days', 'info', 'is due within 7 days'
    return None


def _recipient_ids(record):
    recipient_ids = {record.created_by_id}
    if record.assigned_to_id and record.assigned_to.LOGIN_id:
        recipient_ids.add(record.assigned_to.LOGIN_id)
    recipient_ids.update(
        login.objects.filter(usertype__in=DEADLINE_RECIPIENT_ROLES)
        .values_list('id', flat=True)
    )
    return recipient_ids


def ensure_quotation_deadline_notifications(now=None):
    """Create each deadline alert once and return the number created."""
    now = now or timezone.now()
    candidates = enquiry.objects.exclude(
        status__in=INACTIVE_ENQUIRY_STATUSES,
    ).filter(
        quotation_deadline__isnull=False,
        quotation_deadline__lte=now + timedelta(days=7),
    ).select_related('assigned_to', 'created_by')

    created_count = 0
    with transaction.atomic():
        for record in candidates:
            stage = _deadline_stage(record.quotation_deadline, now)
            if not stage:
                continue
            stage_name, level, timing = stage
            deadline_label = timezone.localtime(record.quotation_deadline).strftime('%d %b %Y')
            message = (
                f'Quotation for "{record.title}" {timing}. '
                f'Submission deadline: {deadline_label}.'
            )
            deadline_key = record.quotation_deadline.isoformat(timespec='minutes')
            for recipient_id in _recipient_ids(record):
                _, created = workflow_notification.objects.get_or_create(
                    dedupe_key=(
                        f'quotation-deadline:{record.pk}:{deadline_key}:'
                        f'{stage_name}:{recipient_id}'
                    ),
                    defaults={
                        'recipient_id': recipient_id,
                        'ENQUIRY': record,
                        'event': 'quotation_deadline',
                        'level': level,
                        'message': message,
                        'due_at': record.quotation_deadline,
                        'link': reverse('workflow_detail', args=(record.pk,)),
                    },
                )
                created_count += int(created)
    return created_count
