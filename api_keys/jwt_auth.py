from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


class FlexibleJWTAuthentication(JWTAuthentication):
    """
    JWT authentication that plays nicely with API key authentication.

    If the Authorization header does not carry a JWT (e.g. it is an API key
    such as ``sk_live_...``), return None so later authentication backends
    (APIKeyAuthentication) get a chance to authenticate the request.
    """

    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        # API keys use the same "Bearer" scheme; if it looks like an API key,
        # defer to the API key authentication backend.
        token_text = raw_token.decode("utf-8")
        if token_text.startswith("sk_"):
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
        except InvalidToken:
            # Let other backends try (e.g. API key auth) instead of failing hard.
            return None

        return self.get_user(validated_token), validated_token