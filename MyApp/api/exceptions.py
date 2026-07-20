from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response
    detail = response.data.get('detail') if isinstance(response.data, dict) else None
    response.data = {
        'error': {
            'code': getattr(exc, 'default_code', 'request_error'),
            'message': str(detail or 'The request could not be completed.'),
            'fields': response.data if not detail else {},
        }
    }
    return response
