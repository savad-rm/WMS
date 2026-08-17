from django.urls import reverse

from .models import enquiry_comment, login, workflow_notification


CLIENT_STATUS_LABELS = {
    'under_review': 'Under Review',
    'approved': 'Approved',
    'rejected': 'Rejected',
}


def publish_client_response(quote, author, client_status, remarks=''):
    """Add a client response to discussion and notify the other workflow parties."""
    label = CLIENT_STATUS_LABELS.get(client_status, client_status.replace('_', ' ').title())
    value = f'Client response updated to {label}.'
    if remarks:
        value += f'\nRemarks: {remarks}'
    return publish_quotation_message(
        quote, author, value, notification_message=f'Client response on {quote.display_number}: {label}.',
    )


def publish_quotation_message(quote, author, value, notification_message=None, recipient_ids=None):
    if recipient_ids is not None:
        recipient_ids = set(recipient_ids) - {author.pk}
        recipient_prefix = f'[TO:{",".join(str(value) for value in sorted(recipient_ids))}] '
    else:
        recipient_prefix = ''
    item = enquiry_comment.objects.create(
        ENQUIRY=quote.ENQUIRY,
        author=author,
        comment=f'[QID:{quote.pk}] {recipient_prefix}{value}',
    )
    if recipient_ids is None:
        recipient_ids = {quote.ENQUIRY.created_by_id}
        if quote.ENQUIRY.assigned_to_id and quote.ENQUIRY.assigned_to.LOGIN_id:
            recipient_ids.add(quote.ENQUIRY.assigned_to.LOGIN_id)
        recipient_ids.update(login.objects.filter(
            usertype__in=('Marketing Manager', 'Accountant'),
        ).values_list('id', flat=True))
        recipient_ids.discard(author.pk)
    discussion_url = reverse('workflow_quotation_discussion', args=(quote.pk,))
    workflow_notification.objects.bulk_create([
        workflow_notification(
            recipient_id=recipient_id,
            ENQUIRY=quote.ENQUIRY,
            event='quotation_comment',
            level='info',
            message=notification_message or f'New quotation discussion message on {quote.display_number}.',
            link=discussion_url,
            dedupe_key=f'quotation-client-response:{item.pk}:{recipient_id}',
        )
        for recipient_id in recipient_ids
    ])
    return item
