import logging
import re
import time

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


def quotation_email_content(quote):
    subject = f'{quote.display_number} - {quote.subject or "Quotation"}'
    body = (
        f'Dear {quote.ENQUIRY.client_name},\n\n'
        'Please find our quotation attached for your review.\n\n'
        f'Quotation number: {quote.display_number}\n'
        f'Subject: {quote.subject or quote.ENQUIRY.title}\n\n'
        'With Best Regards,\n'
        'Exalter Trading & Contracting'
    )
    return subject, body


def _parse_addresses(value, label):
    addresses = [item.strip().lower() for item in re.split(r'[,;\s]+', value or '') if item.strip()]
    for address in addresses:
        try:
            validate_email(address)
        except ValidationError as exc:
            raise QuotationDeliveryError(f'Correct the {label} email address: {address}.') from exc
    return addresses


def send_quotation_to_client(quote, *, to='', cc='', subject=None, body=None):
    """Email the generated client PDF and return the confirmed recipient address."""
    recipients = (
        _parse_addresses(to, 'To')
        if str(to or '').strip()
        else [quotation_recipient_email(quote)]
    )
    if not recipients:
        raise QuotationDeliveryError('Enter at least one recipient email address.')
    default_subject, default_body = quotation_email_content(quote)
    subject = (subject or default_subject).strip()[:255]
    body = (body or default_body).strip()
    if not subject or not body:
        raise QuotationDeliveryError('Enter both an email subject and message before sending.')
    cc_addresses = _parse_addresses(cc, 'CC')
    started = time.monotonic()
    logger.info(
        'Starting quotation email: quote=%s to=%s cc=%s subject=%r',
        quote.display_number, recipients, cc_addresses, subject,
    )
    try:
        pdf = build_quotation_pdf(quote).getvalue()
        message = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
            cc=cc_addresses,
        )
        message.attach(f'{quote.display_number.replace("/", "-")}.pdf', pdf, 'application/pdf')
        if message.send(fail_silently=False) != 1:
            raise RuntimeError('The email backend did not confirm delivery.')
        logger.info(
            'Quotation email accepted by SMTP backend: quote=%s elapsed_ms=%d',
            quote.display_number, round((time.monotonic() - started) * 1000),
        )
    except QuotationDeliveryError:
        raise
    except Exception as exc:
        logger.exception(
            'Quotation email delivery failed: quote=%s to=%s cc=%s elapsed_ms=%d',
            quote.display_number, recipients, cc_addresses,
            round((time.monotonic() - started) * 1000),
        )
        raise QuotationDeliveryError(
            'The quotation email could not be sent. Check the mail configuration and try again.'
        ) from exc
    return ', '.join(recipients)
