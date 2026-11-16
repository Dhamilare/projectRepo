import logging
import msal
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from .models import (
    Article,
    Attachment,
    AuditLog,
    Comment,
    Project,
    ProjectActivity,
    ProjectDocument,
)

User = get_user_model()
logger = logging.getLogger("projectRepo")


def _get_ms_config() -> dict:
    return getattr(settings, "MICROSOFT_AUTH", {})


def _get_client_ip(request) -> str | None:
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class MicrosoftEntraBackend(BaseBackend):
    """
    Authenticate users via Microsoft Entra ID (Azure AD) OAuth 2.0.
    Exchanges authorization codes for tokens, validates tenant boundaries,
    syncs Graph profile attributes, respects local user deactivation, and
    records enterprise login audit events.
    """

    def authenticate(self, request, auth_code: str = None, **kwargs):
        if not auth_code:
            return None

        token_response = self._exchange_code_for_token(auth_code)
        if not token_response or "access_token" not in token_response:
            logger.warning("Entra token exchange failed: %s", token_response)
            return None

        id_claims = token_response.get("id_token_claims") or {}
        if not self._is_allowed_tenant(id_claims):
            logger.warning(
                "Entra login rejected: tenant %s not in ALLOWED_TENANT_IDS",
                id_claims.get("tid"),
            )
            return None

        access_token = token_response["access_token"]
        profile = self._get_graph_profile(access_token)
        if not profile:
            return None

        user = self._get_or_create_user(profile, id_claims)
        if not user:
            return None

        if not user.is_active:
            logger.warning("Blocked Entra login for deactivated user: %s", user.email)
            return None

        ip_address = _get_client_ip(request)
        user_agent = (request.META.get("HTTP_USER_AGENT", "") if request else "")[:300]
        user.record_login(ip_address=ip_address)

        AuditLog.objects.create(
            actor=user,
            action=AuditLog.Action.USER_LOGIN,
            target_type="User",
            target_id=str(user.pk),
            target_repr=user.email,
            details={"method": "microsoft_entra", "tenant_id": user.azure_tenant_id},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return user

    def get_user(self, user_id: int):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    # ── Private helpers ──────────────────────────────────────────────────────

    def _exchange_code_for_token(self, code: str) -> dict:
        ms_cfg = _get_ms_config()
        app = msal.ConfidentialClientApplication(
            client_id=ms_cfg["CLIENT_ID"],
            client_credential=ms_cfg["CLIENT_SECRET"],
            authority=ms_cfg["AUTHORITY"],
        )
        return app.acquire_token_by_authorization_code(
            code=code,
            scopes=ms_cfg["SCOPES"],
            redirect_uri=ms_cfg["REDIRECT_URI"],
        )

    def _is_allowed_tenant(self, id_claims: dict) -> bool:
        ms_cfg = _get_ms_config()
        allowed_tenants = ms_cfg.get("ALLOWED_TENANT_IDS")
        if not allowed_tenants:
            return True
        tid = (id_claims.get("tid") or "").strip()
        return tid in allowed_tenants

    def _get_graph_profile(self, access_token: str) -> dict | None:
        ms_cfg = _get_ms_config()
        headers = {"Authorization": f"Bearer {access_token}"}
        select_fields = (
            "id,mail,userPrincipalName,givenName,surname,"
            "jobTitle,department,businessPhones,mobilePhone"
        )
        endpoint = f"{ms_cfg['GRAPH_ENDPOINT']}/me?$select={select_fields}"

        try:
            resp = requests.get(endpoint, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("Microsoft Graph API error: %s", exc)
            return None

    def _sync_role_from_claims(self, user: User, id_claims: dict):
        """
        Optionally maps Entra App Roles (e.g., 'Repository.Admin', 'Repository.Lead',
        'Repository.Engineer') if MICROSOFT_AUTH['ROLE_MAPPING'] is configured.
        Otherwise preserves the user's locally assigned role.
        """
        ms_cfg = _get_ms_config()
        role_mapping = ms_cfg.get("ROLE_MAPPING") or {}
        if not role_mapping:
            return

        token_roles = id_claims.get("roles") or []
        priority_order = [
            User.Role.ADMIN,
            User.Role.LEAD,
            User.Role.ENGINEER,
            User.Role.VIEWER,
        ]
        mapped_roles = [role_mapping[r] for r in token_roles if r in role_mapping]
        for candidate in priority_order:
            if candidate in mapped_roles:
                user.role = candidate
                break

    def _get_or_create_user(self, profile: dict, id_claims: dict) -> User | None:
        email = (
            profile.get("mail") or profile.get("userPrincipalName", "")
        ).lower().strip()

        if not email:
            logger.error("No email found in Graph profile: %s", profile)
            return None

        azure_oid = (profile.get("id") or "").strip() or None
        tenant_id = (id_claims.get("tid") or "").strip()

        user = None
        if azure_oid:
            user = User.objects.filter(azure_object_id=azure_oid).first()
        if user is None:
            user = User.objects.filter(email=email).first()

        is_new = user is None
        if is_new:
            user = User(email=email, is_active=True)
            user.set_unusable_password()

        # Respect deactivated users immediately without overwriting is_active
        if not is_new and not user.is_active:
            return user

        if azure_oid:
            user.azure_object_id = azure_oid
        if tenant_id:
            user.azure_tenant_id = tenant_id

        user.email = email
        user.first_name = profile.get("givenName") or user.first_name or ""
        user.last_name = profile.get("surname") or user.last_name or ""
        user.job_title = profile.get("jobTitle") or user.job_title or ""
        user.department = profile.get("department") or user.department or "IT"

        business_phones = profile.get("businessPhones") or []
        first_biz_phone = (
            business_phones[0]
            if isinstance(business_phones, list) and business_phones
            else ""
        )
        user.phone = (
            profile.get("mobilePhone")
            or first_biz_phone
            or user.phone
            or ""
        )

        if not user.username:
            user.username = User.objects._unique_username(email.split("@")[0])

        self._sync_role_from_claims(user, id_claims)

        # Ensure Admins have staff flag; keep superuser status intact
        if user.is_superuser:
            user.role = User.Role.ADMIN
        user.is_staff = user.role == User.Role.ADMIN or user.is_superuser

        user.save()
        logger.info(
            "Entra login authenticated: %s (oid=%s, role=%s, dept=%s)",
            user.email,
            user.azure_object_id,
            user.role,
            user.department,
        )
        return user


class RepositoryPermissionBackend(BaseBackend):
    """
    Object-level authorization backend enforcing scoped access across
    Projects, Project Documents (SOW, Requirements, As-Built, Admin Guide),
    Project Activities, Support Articles, Attachments, and Comments.
    Administrators always retain full system rights.
    """

    def authenticate(self, request, **kwargs):
        return None  # Authorization only

    def has_perm(self, user_obj, perm: str, obj=None) -> bool:
        if not user_obj or not user_obj.is_authenticated or not user_obj.is_active:
            return False

        # Admins have full rights across the entire platform
        if user_obj.is_admin:
            return True

        if obj is None:
            return False

        action = perm.split(".")[-1]

        # ── Project Permissions ──────────────────────────────────────────────
        if isinstance(obj, Project):
            return self._check_project_perm(user_obj, action, obj)

        # ── Project Document Permissions ─────────────────────────────────────
        if isinstance(obj, ProjectDocument):
            if action in ("view_projectdocument",):
                return obj.project.can_view(user_obj)
            if action in ("add_projectdocument", "change_projectdocument"):
                return obj.project.can_upload_documents(user_obj)
            if action in ("approve_projectdocument",):
                return obj.project.can_approve_documents(user_obj)
            if action in ("delete_projectdocument",):
                return False  # Admin only
            return False

        # ── Project Activity Permissions ─────────────────────────────────────
        if isinstance(obj, ProjectActivity):
            if action in ("view_projectactivity",):
                return obj.project.can_view(user_obj)
            if action in ("add_projectactivity", "change_projectactivity"):
                return obj.project.can_edit(user_obj)
            if action in ("delete_projectactivity",):
                return obj.project.can_manage_members(user_obj)
            return False

        # ── Article (Support Resolution / Guide) Permissions ─────────────────
        if isinstance(obj, Article):
            if action in ("view_article",):
                return obj.can_view(user_obj)
            if action in ("change_article",):
                return obj.can_edit(user_obj)
            if action in ("publish_article",):
                return obj.can_publish(user_obj)
            if action in ("delete_article",):
                return obj.can_delete(user_obj)
            return False

        # ── Attachment Permissions ───────────────────────────────────────────
        if isinstance(obj, Attachment):
            if action == "view_attachment":
                if obj.project:
                    return obj.project.can_view(user_obj)
                if obj.activity:
                    return obj.activity.project.can_view(user_obj)
                if obj.article:
                    return obj.article.can_view(user_obj)
                return True
            if action == "delete_attachment":
                return obj.uploaded_by_id == user_obj.id and user_obj.is_engineer
            return False

        # ── Comment Permissions ──────────────────────────────────────────────
        if isinstance(obj, Comment):
            if action in ("change_comment", "delete_comment"):
                return obj.author_id == user_obj.id
            return False

        return False

    @staticmethod
    def _check_project_perm(user, action: str, project: Project) -> bool:
        if action == "view_project":
            return project.can_view(user)
        if action in ("change_project", "collaborate_project"):
            return project.can_edit(user)
        if action == "upload_projectdocument":
            return project.can_upload_documents(user)
        if action == "approve_projectdocument":
            return project.can_approve_documents(user)
        if action == "manage_project_members":
            return project.can_manage_members(user)
        if action == "delete_project":
            return project.can_delete(user)
        return False


def build_auth_url(state: str) -> str:
    """Generate the Microsoft OAuth2 authorization URL."""
    ms_cfg = _get_ms_config()
    app = msal.ConfidentialClientApplication(
        client_id=ms_cfg["CLIENT_ID"],
        client_credential=ms_cfg["CLIENT_SECRET"],
        authority=ms_cfg["AUTHORITY"],
    )
    return app.get_authorization_request_url(
        scopes=ms_cfg["SCOPES"],
        state=state,
        redirect_uri=ms_cfg["REDIRECT_URI"],
    )