import logging
import msal
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

User = get_user_model()

logger = logging.getLogger("projectRepo")
_MS = settings.MICROSOFT_AUTH


class MicrosoftEntraBackend(BaseBackend):
    """
    Authenticate users via Microsoft Entra ID (Azure AD) OAuth 2.0.
    The backend exchanges an authorization code for tokens, fetches the
    user's profile from Microsoft Graph, then finds-or-creates the
    local Django User record keyed on their email address.
    """

    def authenticate(self, request, auth_code: str = None, **kwargs):
        if not auth_code:
            return None

        token_response = self._exchange_code_for_token(auth_code)
        if not token_response or "access_token" not in token_response:
            logger.warning("Token exchange failed: %s", token_response)
            return None

        access_token = token_response["access_token"]
        profile = self._get_graph_profile(access_token)
        if not profile:
            return None

        return self._get_or_create_user(profile, access_token)

    def get_user(self, user_id: int):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    # ── Private helpers ───────

    def _exchange_code_for_token(self, code: str) -> dict:
        app = msal.ConfidentialClientApplication(
            client_id=_MS["CLIENT_ID"],
            client_credential=_MS["CLIENT_SECRET"],
            authority=_MS["AUTHORITY"],
        )
        result = app.acquire_token_by_authorization_code(
            code=code,
            scopes=_MS["SCOPES"],
            redirect_uri=_MS["REDIRECT_URI"],
        )
        return result

    def _get_graph_profile(self, access_token: str) -> dict | None:
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            resp = requests.get(
                f"{_MS['GRAPH_ENDPOINT']}/me",
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("Graph API error: %s", exc)
            return None

    def _get_or_create_user(self, profile: dict, access_token: str) -> User | None:
        email = (
            profile.get("mail")
            or profile.get("userPrincipalName", "")
        ).lower().strip()

        if not email:
            logger.error("No email in Graph profile: %s", profile)
            return None

        azure_oid = profile.get("id", "")

        try:
            user = User.objects.filter(azure_object_id=azure_oid).first()
            if user is None:
                user = User.objects.get(email=email)
        except User.DoesNotExist:
            user = User(email=email)

        user.azure_object_id = azure_oid
        user.first_name = profile.get("givenName", user.first_name or "")
        user.last_name = profile.get("surname", user.last_name or "")
        user.job_title = profile.get("jobTitle", user.job_title or "")
        user.department = profile.get("department", user.department or "")
        
        business_phones = profile.get("businessPhones", [])
        user.phone = profile.get("mobilePhone") or (business_phones[0] if business_phones else "")
        
        user.username = email
        user.is_active = True
        user.is_staff = True

        user.save()
        logger.info("Entra login successful for: %s (oid=%s)", email, azure_oid)
        return user


def build_auth_url(state: str) -> str:
    """Generate the Microsoft OAuth2 authorization URL."""
    app = msal.ConfidentialClientApplication(
        client_id=_MS["CLIENT_ID"],
        client_credential=_MS["CLIENT_SECRET"],
        authority=_MS["AUTHORITY"],
    )
    return app.get_authorization_request_url(
        scopes=_MS["SCOPES"],
        state=state,
        redirect_uri=_MS["REDIRECT_URI"],
    )