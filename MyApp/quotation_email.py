import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email

from .quotation_document import unpack_document
from .quotation_exports import build_quotation_pdf


logger = logging.getLogger(__name__)


class QuotationDeliveryError(Exception):
    """A client-safe quotation delivery failure."""


def quotation_recipient_email(quote):
    document = unpack_document(quote.details, quote.validity_days)
    client = document.get('client') or {}
    recipient = str(client.get('email', quote.ENQUIRY.client_email) or '').strip().lower()
    if not recipient:
        raise QuotationDeliveryError(
            'Add the client email address to the quotation before submitting it.'
        )
    try:
        validate_email(recipient)
    except ValidationError as exc:
        raise QuotationDeliveryError(
            'Correct the client email address on the quotation before submitting it.'
        ) from exc
    return recipient


def send_quotation_to_client(quote):
    """Email the generated client PDF and return the confirmed recipient address."""
    recipient = quotation_recipient_email(quote)
    subject = f'{quote.display_number} - {quote.subject or "Quotation"}'
    body = (
        f'Dear {quote.ENQUIRY.client_name},\n\n'
        'Please find our quotation attached for your review.\n\n'
        f'Quotation number: {quote.display_number}\n'
        f'Subject: {quote.subject or quote.ENQUIRY.title}\n\n'
        'With Best Regards,\n'
        'Exalter Trading & Contracting'
    )
    try:
        pdf = build_quotation_pdf(quote).getvalue()
        message = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        message.attach(f'{quote.display_number.replace("/", "-")}.pdf', pdf, 'application/pdf')
        if message.send(fail_silently=False) != 1:
            raise RuntimeError('The email backend did not confirm delivery.')
    except QuotationDeliveryError:
        raise
    except Exception as exc:
        logger.exception('Quotation email delivery failed for quotation %s.', quote.pk)
        raise QuotationDeliveryError(
            'The quotation email could not be sent. Check the mail configuration and try again.'
        ) from exc
    return recipient
