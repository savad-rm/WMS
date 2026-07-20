from django.conf import settings
from django.core import signing
from rest_framework import authentication, exceptions

from MyApp.models import login


TOKEN_SALT = 'wms.mobile.api.v1'


def issue_token(account):
    payload = {'uid': account.pk, 'version': account.api_token_version}
    return signing.dumps(payload, key=settings.SECRET_KEY, salt=TOKEN_SALT, compress=True)


class SignedTokenAuthentication(authentication.BaseAuthentication):
    keyword = 'Bearer'

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].decode().lower() != self.keyword.lower():
            raise exceptions.AuthenticationFailed('Use a Bearer authentication token.')
        try:
            token = header[1].decode()
            payload = signing.loads(
                token,
                key=settings.SECRET_KEY,
                salt=TOKEN_SALT,
                max_age=settings.WMS_MOBILE_TOKEN_MAX_AGE,
            )
            account = login.objects.get(pk=payload['uid'])
        except (UnicodeError, signing.BadSignature, signing.SignatureExpired, KeyError, login.DoesNotExist):
            raise exceptions.AuthenticationFailed('The session is invalid or has expired.') from None
        if account.api_token_version != payload.get('version'):
            raise exceptions.AuthenticationFailed('The session has been revoked.')
        return account, token

    def authenticate_header(self, request):
        return self.keyword
