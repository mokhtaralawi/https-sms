import logging
import uuid

from django.utils import timezone
from rest_framework import authentication, exceptions

from api_keys.models import APIKey

logger = logging.getLogger("httpsms.api_keys")


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Authenticate requests using an API key in the Authorization header:

        Authorization: Bearer sk_live_xxxxxxxxx
    """

    keyword = "Bearer"

    def authenticate(self, request):
        auth = authentication.get_authorization_header(request).split()
        if not auth or not auth[0].lower() == self.keyword.lower().encode():
            return None

        if len(auth) != 2:
            raise exceptions.AuthenticationFailed("Invalid authorization header.")

        raw_key = auth[1].decode()
        return self.authenticate_key(raw_key)

    def authenticate_key(self, raw_key: str):
        api_key = APIKey.find_by_raw_key(raw_key)
        if api_key is None:
            raise exceptions.AuthenticationFailed("Invalid API key.")

        if not api_key.is_active:
            raise exceptions.AuthenticationFailed("API key is not active or expired.")

        # Update last_used_at and customer status check
        customer = api_key.customer
        if customer and customer.status != customer.ACTIVE:
            raise exceptions.AuthenticationFailed("Customer account is not active.")

        api_key.touch_used()

        # Create a lightweight principal carrying customer info
        principal = APIKeyPrincipal(api_key)
        return (principal, api_key)

    def authenticate_header(self, request):
        return self.keyword


class APIKeyPrincipal:
    """
    A principal representing an authenticated API key.
    Exposes an interface compatible with DRF permission checks:
      .is_authenticated, .customer, .api_key
    """

    is_authenticated = True
    is_anonymous = False

    def __init__(self, api_key: APIKey):
        self.api_key = api_key
        self.customer = api_key.customer
        self.id = uuid.uuid4()

    def __str__(self):
        return f"APIKey({self.api_key.key_prefix}{self.api_key.name})"
