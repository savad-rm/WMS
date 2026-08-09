from django import template
from django.utils.safestring import mark_safe

from MyApp.quotation_document import line_kind, rich_text_to_html


register = template.Library()


@register.filter
def quotation_line_kind(value):
    return line_kind(value)


@register.filter
def quotation_rich_text(value):
    return mark_safe(rich_text_to_html(value))


@register.filter
def quotation_client_name(value):
    return value if value.strip().lower().startswith('m/s') else f'M/s {value}'
