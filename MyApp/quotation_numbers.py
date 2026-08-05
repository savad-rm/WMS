from .models import quotation_counter


def assign_quotation_reference(quote, first_quote=None):
    """Assign a base reference or the next revision reference inside a transaction."""
    if first_quote:
        base_number = (first_quote.quotation_number or '').split('-R', 1)[0]
        sequence = first_quote.sequence_number or first_quote.pk
        if not base_number:
            base_number = f'QTN/{sequence:04d}/ETC/{first_quote.issue_date:%m/%y}'
        quote.sequence_number = sequence
        quote.quotation_number = f'{base_number}-R{quote.revision}'
    else:
        counter, _ = quotation_counter.objects.select_for_update().get_or_create(
            pk=1, defaults={'next_value': 1},
        )
        sequence = counter.next_value
        counter.next_value += 1
        counter.save(update_fields=('next_value',))
        quote.sequence_number = sequence
        quote.quotation_number = f'QTN/{sequence:04d}/ETC/{quote.issue_date:%m/%y}'
    quote.save(update_fields=('sequence_number', 'quotation_number'))
    return quote.quotation_number
