import logging
import os
import secrets
from django.conf import settings
from django.contrib import auth, messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Max, Prefetch, Q
from django.http import FileResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .backends import build_auth_url
from .forms import (
    ArticleForm,
    AttachmentForm,
    CategoryForm,
    CommentForm,
    ProjectActivityForm,
    ProjectDocumentReviewForm,
    ProjectDocumentUploadForm,
    ProjectForm,
    ProjectMemberForm,
    ResolutionStepFormSet,
    SearchForm,
    TeamForm,
)
from .models import (
    Article,
    ArticleFeedback,
    ArticleRevision,
    Attachment,
    AuditLog,
    Bookmark,
    Category,
    Comment,
    Notification,
    Project,
    ProjectActivity,
    ProjectDocument,
    ProjectMember,
    SearchLog,
    Tag,
    Team,
    User,
)

logger = logging.getLogger("projectRepo")


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


def _log_audit(
    request,
    action: str,
    obj=None,
    target_type: str = "",
    target_id: str = "",
    target_repr: str = "",
    details: dict = None,
):
    if obj is not None:
        target_type = target_type or obj.__class__.__name__
        target_id = target_id or str(obj.pk)
        target_repr = target_repr or str(obj)[:300]
    AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_repr=target_repr,
        details=details or {},
        ip_address=_get_client_ip(request) or None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
    )


def _paginate(request, qs, per_page=None):
    per_page = per_page or getattr(settings, "ARTICLES_PER_PAGE", 15)
    paginator = Paginator(qs, per_page)
    page_num = request.GET.get("page", 1)
    try:
        return paginator.page(page_num)
    except (PageNotAnInteger, EmptyPage):
        return paginator.page(1)


def _infer_attachment_kind(file_obj) -> str:
    content_type = (getattr(file_obj, "content_type", "") or "").lower()
    ext = os.path.splitext(file_obj.name)[1].lower()
    if content_type.startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return Attachment.AttachmentKind.SCREENSHOT
    if ext in {".log", ".evtx", ".txt"}:
        return Attachment.AttachmentKind.LOG
    if ext in {".ps1", ".py", ".sh", ".bat", ".cmd", ".json", ".yaml", ".yml", ".reg"}:
        return Attachment.AttachmentKind.SCRIPT
    if ext in {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}:
        return Attachment.AttachmentKind.DOCUMENT
    return Attachment.AttachmentKind.OTHER


def _save_multi_attachments(request, *, article=None, project=None, activity=None, comment=None):
    files = request.FILES.getlist("attachments")
    if not files:
        return
    max_bytes = getattr(settings, "MAX_ATTACHMENT_SIZE_MB", 25) * 1024 * 1024
    for file_obj in files:
        if file_obj.size > max_bytes:
            messages.warning(request, f'Skipped "{file_obj.name}" (exceeds size limit).')
            continue
        Attachment.objects.create(
            article=article,
            project=project,
            activity=activity,
            comment=comment,
            attachment_kind=_infer_attachment_kind(file_obj),
            file=file_obj,
            original_name=file_obj.name[:255],
            file_size_bytes=file_obj.size,
            file_type=(file_obj.content_type or "")[:100],
            uploaded_by=request.user,
        )


def _notify_project_team(project: Project, actor: User, notif_type: str, title: str, message: str):
    recipient_ids = set(project.memberships.values_list("user_id", flat=True))
    if project.project_lead_id:
        recipient_ids.add(project.project_lead_id)
    recipient_ids.discard(actor.id)
    if not recipient_ids:
        return
    Notification.objects.bulk_create([
        Notification(
            user_id=uid,
            notification_type=notif_type,
            title=title[:200],
            message=message[:500],
            project=project,
        )
        for uid in recipient_ids
    ])


# ─────────────────────────────────────────────────────────────────────────────
# IDENTITY MANAGEMENT & MICROSOFT ENTRA ID OAUTH
# ─────────────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "accounts/login.html", {
        "page_title": "Sign In",
        "error": request.GET.get("error"),
    })


@require_http_methods(["GET"])
def microsoft_login(request):
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    return redirect(build_auth_url(state))


@require_http_methods(["GET"])
def oauth_callback(request):
    received_state = request.GET.get("state", "")
    expected_state = request.session.pop("oauth_state", None)

    if not expected_state or received_state != expected_state:
        logger.warning("OAuth state mismatch. IP: %s", _get_client_ip(request))
        messages.error(request, "Authentication failed: invalid state token.")
        return redirect("login")

    error = request.GET.get("error")
    if error:
        error_desc = request.GET.get("error_description", error)
        logger.warning("OAuth failure: %s", error_desc)
        messages.error(request, f"Microsoft sign-in failed: {error_desc}")
        return redirect("login")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "No authorization code received from Microsoft.")
        return redirect("login")

    user = auth.authenticate(request, auth_code=code)
    if user is None:
        messages.error(request, "Authentication failed or your account is inactive. Contact your administrator.")
        return redirect("login")

    auth.login(request, user)
    next_url = request.session.pop("next", None) or settings.LOGIN_REDIRECT_URL
    return redirect(next_url)


@login_required
@require_http_methods(["POST"])
def logout_view(request):
    logger.info("SSO Session closing for: %s", request.user.email)
    auth.logout(request)
    ms_cfg = getattr(settings, "MICROSOFT_AUTH", {})
    tenant_id = ms_cfg.get("TENANT_ID", "common")
    post_logout_uri = request.build_absolute_uri(settings.LOGOUT_REDIRECT_URL)
    ms_logout = (
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={post_logout_uri}"
    )
    return redirect(ms_logout)


@login_required
def profile_view(request):
    user = request.user
    authored_articles = (
        Article.objects.visible_to(user)
        .filter(author=user)
        .select_related("category", "related_project")
        .order_by("-updated_at")[:10]
    )
    my_projects = (
        Project.objects.visible_to(user)
        .filter(Q(project_lead=user) | Q(memberships__user=user) | Q(created_by=user))
        .distinct()
        .select_related("category")
        .order_by("-updated_at")[:10]
    )
    return render(request, "accounts/profile.html", {
        "page_title": f"{user.full_name} — Profile",
        "authored_articles": authored_articles,
        "my_projects": my_projects,
        "total_articles": Article.objects.filter(author=user).count(),
        "total_projects": my_projects.count(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# WORKSPACE DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    user = request.user
    visible_projects = Project.objects.visible_to(user).exclude(status=Project.Status.ARCHIVED)
    visible_published_articles = Article.objects.visible_to(user).filter(status=Article.Status.PUBLISHED)

    active_projects_list = list(
        visible_projects.select_related("category", "project_lead")
        .prefetch_related("documents", "activities")
        .order_by("-updated_at")[:6]
    )

    stats = {
        "total_projects": visible_projects.count(),
        "active_projects": visible_projects.exclude(status=Project.Status.COMPLETED).count(),
        "total_support": visible_published_articles.filter(article_type=Article.ArticleType.SUPPORT).count(),
        "total_runbooks": visible_published_articles.filter(article_type=Article.ArticleType.RUNBOOK).count(),
        "total_software": visible_published_articles.filter(article_type=Article.ArticleType.SOFTWARE).count(),
        "my_drafts": Article.objects.filter(author=user, status=Article.Status.DRAFT).count(),
        "pending_doc_reviews": ProjectDocument.objects.filter(
            project__in=visible_projects,
            is_latest=True,
            status=ProjectDocument.Status.IN_REVIEW,
        ).count() if user.can_approve() else 0,
    }

    recent_articles = (
        visible_published_articles
        .select_related("author", "category", "related_project")
        .prefetch_related("tags")
        .order_by("-published_at")[:getattr(settings, "RECENT_ARTICLES_COUNT", 6)]
    )

    featured_articles = (
        visible_published_articles
        .filter(is_featured=True)
        .select_related("author", "category")
        .order_by("-updated_at")[:4]
    )

    my_assigned_activities = (
        ProjectActivity.objects
        .filter(project__in=visible_projects, assigned_to=user)
        .exclude(status__in=[ProjectActivity.Status.COMPLETED, ProjectActivity.Status.SKIPPED])
        .select_related("project")
        .order_by("due_date", "step_number")[:6]
    )

    my_bookmarks = (
        Bookmark.objects.filter(user=user)
        .select_related("project", "article")[:6]
    )

    return render(request, "knowledge/dashboard.html", {
        "page_title": "Engineering Workspace",
        "stats": stats,
        "active_projects": active_projects_list,
        "recent_articles": recent_articles,
        "featured_articles": featured_articles,
        "my_assigned_activities": my_assigned_activities,
        "my_bookmarks": my_bookmarks,
    })


# ─────────────────────────────────────────────────────────────────────────────
# PROJECTS, MANDATORY DELIVERABLES & ACTION PLAN CHECKLISTS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def project_list(request):
    user = request.user
    qs = (
        Project.objects.visible_to(user)
        .select_related("category", "project_lead", "created_by")
        .prefetch_related("tags", "documents", "activities")
    )

    status_filter = request.GET.get("status", "")
    category_param = request.GET.get("category", "")
    priority_filter = request.GET.get("priority", "")
    compliance_filter = request.GET.get("compliance", "")
    q = request.GET.get("q", "").strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    else:
        qs = qs.exclude(status=Project.Status.ARCHIVED)

    if category_param:
        cat = (
            Category.objects.filter(pk=int(category_param)).first()
            if category_param.isdigit()
            else Category.objects.filter(slug=category_param).first()
        )
        if cat:
            qs = qs.filter(Q(category=cat) | Q(category__parent=cat))

    if priority_filter:
        qs = qs.filter(priority=priority_filter)

    if q:
        qs = qs.filter(
            Q(project_code__icontains=q)
            | Q(title__icontains=q)
            | Q(client_or_unit__icontains=q)
            | Q(microsoft_products__icontains=q)
            | Q(tech_stack__icontains=q)
        ).distinct()

    if compliance_filter == "incomplete":
        projects_list = [p for p in qs if p.document_compliance_percent < 100]
        page_obj = _paginate(request, projects_list)
        total_results = len(projects_list)
    elif compliance_filter == "complete":
        projects_list = [p for p in qs if p.document_compliance_percent == 100]
        page_obj = _paginate(request, projects_list)
        total_results = len(projects_list)
    else:
        total_results = qs.count()
        page_obj = _paginate(request, qs)

    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(request, "projects/project_list.html", {
        "page_title": "Project Repository",
        "page_obj": page_obj,
        "total_results": total_results,
        "status_filter": status_filter,
        "category_param": category_param,
        "priority_filter": priority_filter,
        "compliance_filter": compliance_filter,
        "q": q,
        "query_string": query_params.urlencode(),
        "categories": Category.objects.filter(is_active=True, parent=None).order_by("sort_order"),
        "status_choices": Project.Status.choices,
        "priority_choices": Project.Priority.choices,
    })


@login_required
def project_detail(request, slug: str):
    project = get_object_or_404(
        Project.objects.select_related("category", "project_lead", "created_by")
        .prefetch_related(
            "tags",
            "allowed_teams",
            "memberships__user",
            "attachments",
            "activities__assigned_to",
            "activities__completed_by",
            "activities__attachments",
            Prefetch(
                "comments",
                queryset=Comment.objects.filter(is_approved=True, parent=None)
                .select_related("author")
                .prefetch_related(
                    "attachments",
                    Prefetch("replies", queryset=Comment.objects.filter(is_approved=True).select_related("author")),
                ),
            ),
        ),
        slug=slug,
    )

    if not project.can_view(request.user):
        return render(request, "403.html", status=403)

    mandatory_slots = [
        {
            "type": ProjectDocument.DocumentType.SOW,
            "label": "Statement of Work (SOW)",
            "phase": "Pre-Implementation",
            "description": "Scope, out-of-scope, requirements, and project timelines.",
            "latest": project.get_latest_document(ProjectDocument.DocumentType.SOW),
            "history": project.documents.filter(document_type=ProjectDocument.DocumentType.SOW).select_related("uploaded_by", "reviewed_by"),
        },
        {
            "type": ProjectDocument.DocumentType.REQUIREMENTS,
            "label": "Requirements Document",
            "phase": "Pre-Implementation",
            "description": "Technical and business requirements scoped to project title.",
            "latest": project.get_latest_document(ProjectDocument.DocumentType.REQUIREMENTS),
            "history": project.documents.filter(document_type=ProjectDocument.DocumentType.REQUIREMENTS).select_related("uploaded_by", "reviewed_by"),
        },
        {
            "type": ProjectDocument.DocumentType.AS_BUILT,
            "label": "As-Built Document",
            "phase": "Post-Implementation",
            "description": "Final implemented architecture, configuration, and tenant records.",
            "latest": project.get_latest_document(ProjectDocument.DocumentType.AS_BUILT),
            "history": project.documents.filter(document_type=ProjectDocument.DocumentType.AS_BUILT).select_related("uploaded_by", "reviewed_by"),
        },
        {
            "type": ProjectDocument.DocumentType.ADMIN_GUIDE,
            "label": "Admin Guide",
            "phase": "Post-Implementation",
            "description": "Day-2 operations, administration procedures, and maintenance handbook.",
            "latest": project.get_latest_document(ProjectDocument.DocumentType.ADMIN_GUIDE),
            "history": project.documents.filter(document_type=ProjectDocument.DocumentType.ADMIN_GUIDE).select_related("uploaded_by", "reviewed_by"),
        },
    ]

    supporting_docs = project.documents.filter(
        document_type=ProjectDocument.DocumentType.SUPPORTING, is_latest=True
    ).select_related("uploaded_by", "reviewed_by")

    related_support_articles = (
        Article.objects.visible_to(request.user)
        .filter(related_project=project)
        .select_related("category", "author")
        .order_by("-updated_at")
    )

    is_bookmarked = Bookmark.objects.filter(user=request.user, project=project).exists()

    return render(request, "projects/project_detail.html", {
        "page_title": f"{project.project_code} — {project.title}",
        "project": project,
        "mandatory_slots": mandatory_slots,
        "supporting_docs": supporting_docs,
        "related_support_articles": related_support_articles,
        "is_bookmarked": is_bookmarked,
        "can_edit": project.can_edit(request.user),
        "can_upload_docs": project.can_upload_documents(request.user),
        "can_approve_docs": project.can_approve_documents(request.user),
        "can_manage_members": project.can_manage_members(request.user),
        "can_delete": project.can_delete(request.user),
        "doc_upload_form": ProjectDocumentUploadForm(project=project, user=request.user),
        "activity_form": ProjectActivityForm(project=project),
        "comment_form": CommentForm(),
        "attachment_form": AttachmentForm(),
        "member_form": ProjectMemberForm(),
    })


@login_required
def project_create(request):
    if not request.user.can_edit_content():
        messages.error(request, "Access Denied: Only Engineers, Leads, and Administrators can create projects.")
        return redirect("project_list")

    if request.method == "POST":
        form = ProjectForm(request.POST, user=request.user)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            if not project.project_lead:
                project.project_lead = request.user
            project.save()
            form.save_m2m()
            form._save_tags(project)

            ProjectMember.objects.get_or_create(
                project=project,
                user=project.project_lead,
                defaults={
                    "role": ProjectMember.Role.LEAD,
                    "can_upload_docs": True,
                    "can_approve_docs": True,
                    "added_by": request.user,
                },
            )
            _save_multi_attachments(request, project=project)
            _log_audit(request, AuditLog.Action.PROJECT_CREATED, obj=project)

            messages.success(request, f'Project "{project.project_code}: {project.title}" created successfully.')
            return redirect(project.get_absolute_url())
        messages.error(request, "Please correct the errors below.")
    else:
        form = ProjectForm(user=request.user, initial={"project_lead": request.user})

    return render(request, "projects/project_form.html", {
        "page_title": "Create New Project",
        "form": form,
        "is_create": True,
    })


@login_required
def project_edit(request, slug: str):
    project = get_object_or_404(Project, slug=slug)
    if not project.can_edit(request.user):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project, user=request.user)
        if form.is_valid():
            project = form.save()
            _save_multi_attachments(request, project=project)
            _log_audit(request, AuditLog.Action.PROJECT_UPDATED, obj=project)
            messages.success(request, "Project updated successfully.")
            return redirect(project.get_absolute_url())
        messages.error(request, "Please correct the errors below.")
    else:
        form = ProjectForm(instance=project, user=request.user)

    return render(request, "projects/project_form.html", {
        "page_title": f"Edit — {project.title}",
        "form": form,
        "project": project,
        "is_create": False,
    })


@login_required
@require_POST
def project_delete(request, slug: str):
    project = get_object_or_404(Project, slug=slug)
    if not project.can_delete(request.user):
        return HttpResponseForbidden("Only Administrators can delete projects.")

    code, title = project.project_code, project.title
    _log_audit(
        request,
        AuditLog.Action.PROJECT_DELETED,
        target_type="Project",
        target_id=str(project.pk),
        target_repr=f"[{code}] {title}",
    )
    project.delete()
    messages.success(request, f'Project "{code}: {title}" has been deleted.')
    return redirect("project_list")


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT DOCUMENTS (SOW, REQUIREMENTS, AS-BUILT, ADMIN GUIDE)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def project_document_upload(request, slug: str):
    project = get_object_or_404(Project, slug=slug)
    if not project.can_upload_documents(request.user):
        return render(request, "403.html", status=403)

    form = ProjectDocumentUploadForm(request.POST, request.FILES, project=project, user=request.user)
    if form.is_valid():
        doc = form.save(commit=False)
        doc.project = project
        doc.uploaded_by = request.user
        file_obj = request.FILES["file"]
        doc.original_name = file_obj.name[:255]
        doc.file_size_bytes = file_obj.size
        doc.mime_type = (file_obj.content_type or "")[:120]

        if doc.status == ProjectDocument.Status.APPROVED and project.can_approve_documents(request.user):
            doc.reviewed_by = request.user
            doc.reviewed_at = timezone.now()

        doc.save()

        _log_audit(
            request,
            AuditLog.Action.DOCUMENT_UPLOADED,
            obj=doc,
            details={"project": project.project_code, "type": doc.document_type, "version": doc.version},
        )
        _notify_project_team(
            project=project,
            actor=request.user,
            notif_type=Notification.NotificationType.DOCUMENT_UPLOADED,
            title=f"{doc.get_document_type_display()} v{doc.version} uploaded",
            message=f"{request.user.full_name} uploaded {doc.original_name} to {project.project_code}.",
        )
        messages.success(request, f'{doc.get_document_type_display()} (v{doc.version}) uploaded successfully.')
    else:
        for err in form.errors.values():
            messages.error(request, err.as_text())

    return redirect(f"{project.get_absolute_url()}#documents")


@login_required
@require_POST
def project_document_review(request, slug: str, doc_id: int):
    project = get_object_or_404(Project, slug=slug)
    doc = get_object_or_404(ProjectDocument, pk=doc_id, project=project)

    if not project.can_approve_documents(request.user):
        return HttpResponseForbidden("You do not have permission to approve or reject project documents.")

    form = ProjectDocumentReviewForm(request.POST)
    if form.is_valid():
        decision = form.cleaned_data["decision"]
        doc.status = decision
        doc.review_notes = form.cleaned_data["review_notes"]
        doc.reviewed_by = request.user
        doc.reviewed_at = timezone.now()
        doc.save(update_fields=["status", "review_notes", "reviewed_by", "reviewed_at", "updated_at"])

        _log_audit(
            request,
            AuditLog.Action.DOCUMENT_APPROVED if decision == ProjectDocument.Status.APPROVED else AuditLog.Action.PROJECT_UPDATED,
            obj=doc,
            details={"decision": decision, "notes": doc.review_notes},
        )
        if doc.uploaded_by and doc.uploaded_by != request.user:
            Notification.objects.create(
                user=doc.uploaded_by,
                notification_type=(
                    Notification.NotificationType.DOCUMENT_APPROVED
                    if decision == ProjectDocument.Status.APPROVED
                    else Notification.NotificationType.DOCUMENT_REJECTED
                ),
                title=f"{doc.get_document_type_display()} v{doc.version} {doc.get_status_display()}",
                message=doc.review_notes or f"Reviewed by {request.user.full_name}.",
                project=project,
            )
        messages.success(request, f'Document marked as "{doc.get_status_display()}".')
    else:
        messages.error(request, "Invalid review submission.")

    return redirect(f"{project.get_absolute_url()}#documents")


@login_required
def project_document_download(request, slug: str, doc_id: int):
    project = get_object_or_404(Project, slug=slug)
    if not project.can_view(request.user):
        return render(request, "403.html", status=403)

    doc = get_object_or_404(ProjectDocument, pk=doc_id, project=project)
    _log_audit(
        request,
        AuditLog.Action.DOCUMENT_DOWNLOADED,
        obj=doc,
        details={"project": project.project_code, "version": doc.version},
    )
    return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.original_name)


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT ACTIVITIES (ACTION PLAN / STEPS / CHECKLIST)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def project_activity_create(request, slug: str):
    project = get_object_or_404(Project, slug=slug)
    if not project.can_edit(request.user):
        return render(request, "403.html", status=403)

    form = ProjectActivityForm(request.POST, project=project)
    if form.is_valid():
        with transaction.atomic():
            activity = form.save(commit=False)
            activity.project = project
            activity.updated_by = request.user
            if not activity.step_number:
                max_step = (
                    ProjectActivity.objects.select_for_update()
                    .filter(project=project)
                    .aggregate(Max("step_number"))["step_number__max"]
                    or 0
                )
                activity.step_number = max_step + 1
            if activity.status == ProjectActivity.Status.COMPLETED:
                activity.completed_by = request.user
                activity.completed_at = timezone.now()
            activity.save()

        _save_multi_attachments(request, activity=activity)
        if activity.assigned_to and activity.assigned_to != request.user:
            Notification.objects.create(
                user=activity.assigned_to,
                notification_type=Notification.NotificationType.ACTIVITY_ASSIGNED,
                title=f"Assigned Step {activity.step_number}: {activity.title}",
                message=f"Assigned by {request.user.full_name} on project {project.project_code}.",
                project=project,
            )
        messages.success(request, f"Activity step #{activity.step_number} added.")
    else:
        for err in form.errors.values():
            messages.error(request, err.as_text())

    return redirect(f"{project.get_absolute_url()}#activities")


@login_required
def project_activity_edit(request, slug: str, activity_id: int):
    project = get_object_or_404(Project, slug=slug)
    activity = get_object_or_404(ProjectActivity, pk=activity_id, project=project)
    if not project.can_edit(request.user):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = ProjectActivityForm(request.POST, instance=activity, project=project)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.updated_by = request.user
            if updated.status == ProjectActivity.Status.COMPLETED and not updated.completed_at:
                updated.completed_by = request.user
                updated.completed_at = timezone.now()
            elif updated.status != ProjectActivity.Status.COMPLETED:
                updated.completed_by = None
                updated.completed_at = None
            updated.save()
            _save_multi_attachments(request, activity=updated)
            messages.success(request, f"Activity step #{updated.step_number} updated.")
            return redirect(f"{project.get_absolute_url()}#activities")
    else:
        form = ProjectActivityForm(instance=activity, project=project)

    return render(request, "projects/activity_form.html", {
        "page_title": f"Edit Step #{activity.step_number} — {project.project_code}",
        "project": project,
        "activity": activity,
        "form": form,
    })


@login_required
@require_POST
def project_activity_toggle(request, slug: str, activity_id: int):
    project = get_object_or_404(Project, slug=slug)
    activity = get_object_or_404(ProjectActivity, pk=activity_id, project=project)
    if not project.can_edit(request.user):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
        return render(request, "403.html", status=403)

    if activity.status == ProjectActivity.Status.COMPLETED:
        activity.status = ProjectActivity.Status.PENDING
        activity.completed_by = None
        activity.completed_at = None
    else:
        activity.status = ProjectActivity.Status.COMPLETED
        activity.completed_by = request.user
        activity.completed_at = timezone.now()

    activity.updated_by = request.user
    activity.save(update_fields=["status", "completed_by", "completed_at", "updated_by", "updated_at"])

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "status": activity.status,
            "status_label": activity.get_status_display(),
            "completed_by": activity.completed_by.full_name if activity.completed_by else None,
            "checklist_progress": project.checklist_progress_percent,
        })

    return redirect(f"{project.get_absolute_url()}#activities")


@login_required
@require_POST
def project_activity_delete(request, slug: str, activity_id: int):
    project = get_object_or_404(Project, slug=slug)
    activity = get_object_or_404(ProjectActivity, pk=activity_id, project=project)
    if not project.can_manage_members(request.user):
        return HttpResponseForbidden("Only Project Leads or Administrators can remove activity steps.")
    activity.delete()
    messages.success(request, "Activity step removed.")
    return redirect(f"{project.get_absolute_url()}#activities")


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT MEMBERS & SCOPED ACCESS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def project_member_manage(request, slug: str):
    project = get_object_or_404(Project, slug=slug)
    if not project.can_manage_members(request.user):
        return HttpResponseForbidden("Only Project Leads or Administrators can manage project access.")

    form = ProjectMemberForm(request.POST)
    if form.is_valid():
        member, created = ProjectMember.objects.update_or_create(
            project=project,
            user=form.cleaned_data["user"],
            defaults={
                "role": form.cleaned_data["role"],
                "can_upload_docs": form.cleaned_data["can_upload_docs"],
                "can_approve_docs": form.cleaned_data["can_approve_docs"],
                "added_by": request.user,
            },
        )
        _log_audit(
            request,
            AuditLog.Action.PERMISSION_CHANGED,
            obj=project,
            details={"member": member.user.email, "role": member.role},
        )
        if created and member.user != request.user:
            Notification.objects.create(
                user=member.user,
                notification_type=Notification.NotificationType.PROJECT_ASSIGNED,
                title=f"Added to project {project.project_code}",
                message=f"You were assigned as {member.get_role_display()} on {project.title}.",
                project=project,
            )
        messages.success(request, f"Access updated for {member.user.full_name}.")
    else:
        messages.error(request, "Could not update project member.")

    return redirect(f"{project.get_absolute_url()}#access")


@login_required
@require_POST
def project_member_remove(request, slug: str, member_id: int):
    project = get_object_or_404(Project, slug=slug)
    if not project.can_manage_members(request.user):
        return HttpResponseForbidden("Permission denied.")
    member = get_object_or_404(ProjectMember, pk=member_id, project=project)
    email = member.user.email
    member.delete()
    _log_audit(request, AuditLog.Action.PERMISSION_CHANGED, obj=project, details={"removed_member": email})
    messages.success(request, f"Removed {email} from project access list.")
    return redirect(f"{project.get_absolute_url()}#access")


@login_required
@require_POST
def add_project_comment(request, slug: str):
    project = get_object_or_404(Project, slug=slug)
    if not project.can_view(request.user):
        return render(request, "403.html", status=403)
    if request.user.role == User.Role.VIEWER:
        return HttpResponseForbidden("Viewers cannot post comments.")

    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.project = project
        comment.author = request.user
        parent_id = request.POST.get("parent_id")
        if parent_id:
            comment.parent = Comment.objects.filter(pk=parent_id, project=project).first()
        activity_id = request.POST.get("activity_id")
        if activity_id:
            comment.activity = ProjectActivity.objects.filter(pk=activity_id, project=project).first()
        comment.save()
        _save_multi_attachments(request, comment=comment)
        messages.success(request, "Update posted to project collaboration feed.")
    else:
        messages.error(request, "Your comment could not be saved.")

    return redirect(f"{project.get_absolute_url()}#comments")


# ─────────────────────────────────────────────────────────────────────────────
# SUPPORT RESOLUTIONS & KNOWLEDGE BASE ARTICLES
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def article_list(request):
    form = SearchForm(request.GET or None)
    qs = (
        Article.objects.visible_to(request.user)
        .filter(status=Article.Status.PUBLISHED)
        .select_related("author", "category", "related_project")
        .prefetch_related("tags")
    )

    article_type = request.GET.get("type")
    category_param = request.GET.get("category")
    severity = request.GET.get("severity")
    tag_slug = request.GET.get("tag")
    project_slug = request.GET.get("project")
    sort = request.GET.get("sort", "-updated_at")

    if article_type:
        qs = qs.filter(article_type=article_type)
    if category_param:
        cat = (
            Category.objects.filter(pk=int(category_param)).first()
            if category_param.isdigit()
            else Category.objects.filter(slug=category_param).first()
        )
        if cat:
            qs = qs.filter(Q(category=cat) | Q(category__parent=cat))
    if severity and severity != "all":
        qs = qs.filter(severity=severity)
    if tag_slug:
        qs = qs.filter(tags__slug=tag_slug)
    if project_slug:
        qs = qs.filter(related_project__slug=project_slug)

    valid_sort = ["-updated_at", "-published_at", "-views_count", "-helpful_votes", "title"]
    if sort in valid_sort:
        qs = qs.order_by("-is_pinned", sort)

    total_results = qs.count()
    page_obj = _paginate(request, qs)

    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(request, "knowledge/article_list.html", {
        "page_title": "Support Resolutions & Knowledge Base",
        "page_obj": page_obj,
        "form": form,
        "article_type": article_type,
        "category_param": category_param,
        "severity": severity,
        "tag_slug": tag_slug,
        "sort": sort,
        "query_string": query_params.urlencode(),
        "categories": Category.objects.filter(is_active=True, parent=None).order_by("sort_order"),
        "popular_tags": Tag.objects.order_by("-usage_count")[:20],
        "total_results": total_results,
    })


@login_required
def article_detail(request, slug: str):
    article = get_object_or_404(
        Article.objects.select_related("author", "category", "reviewed_by", "related_project")
        .prefetch_related(
            "tags",
            "contributors",
            "attachments",
            "steps",
            "revisions__edited_by",
            Prefetch(
                "comments",
                queryset=Comment.objects.filter(is_approved=True, parent=None)
                .select_related("author")
                .prefetch_related(
                    "attachments",
                    Prefetch("replies", queryset=Comment.objects.filter(is_approved=True).select_related("author")),
                ),
            ),
        ),
        slug=slug,
    )

    if not article.can_view(request.user):
        return render(request, "403.html", status=403)

    session_key = f"viewed_{article.pk}"
    if not request.session.get(session_key):
        article.increment_view(
            user=request.user,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        request.session[session_key] = True

    user_feedback = ArticleFeedback.objects.filter(article=article, user=request.user).first()
    is_bookmarked = Bookmark.objects.filter(user=request.user, article=article).exists()

    related_articles = (
        Article.objects.visible_to(request.user)
        .filter(pk__in=article.related_articles.values_list("pk", flat=True), status=Article.Status.PUBLISHED)
        .select_related("category")[:4]
    )

    return render(request, "knowledge/article_detail.html", {
        "page_title": article.title,
        "article": article,
        "comment_form": CommentForm(),
        "attachment_form": AttachmentForm(),
        "user_feedback": user_feedback,
        "is_bookmarked": is_bookmarked,
        "related_articles": related_articles,
        "can_edit": article.can_edit(request.user),
        "can_delete": article.can_delete(request.user),
    })


@login_required
def article_create(request):
    if not request.user.can_edit_content():
        messages.error(request, "Access Denied: Your role does not permit authoring articles.")
        return redirect("dashboard")

    initial_type = request.GET.get("type", Article.ArticleType.SUPPORT)
    initial_project = None
    project_slug = request.GET.get("project")
    if project_slug:
        candidate = Project.objects.filter(slug=project_slug).first()
        if candidate and candidate.can_view(request.user):
            initial_project = candidate

    if request.method == "POST":
        form = ArticleForm(request.POST, user=request.user)
        step_formset = ResolutionStepFormSet(request.POST)

        if form.is_valid() and step_formset.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            form.save_m2m()
            form._save_tags(article)

            step_formset.instance = article
            step_formset.save()

            _save_multi_attachments(request, article=article)
            _log_audit(request, AuditLog.Action.ARTICLE_CREATED, obj=article)

            messages.success(request, f'Article "{article.title}" saved successfully.')
            return redirect(article.get_absolute_url())
        messages.error(request, "Please correct the errors below.")
    else:
        form = ArticleForm(
            user=request.user,
            initial={"article_type": initial_type, "related_project": initial_project},
        )
        step_formset = ResolutionStepFormSet()

    categories_list = list(Category.objects.filter(is_active=True).order_by("name").values("id", "name", "category_type"))
    return render(request, "knowledge/article_form.html", {
        "page_title": "Create Support Resolution / Guide",
        "form": form,
        "step_formset": step_formset,
        "categories_json": categories_list,
        "is_create": True,
    })


@login_required
def article_edit(request, slug: str):
    article = get_object_or_404(Article, slug=slug)
    if not article.can_edit(request.user):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        prev_title = article.title
        prev_summary = article.summary
        prev_content = article.content
        prev_version = article.version

        form = ArticleForm(request.POST, instance=article, user=request.user)
        step_formset = ResolutionStepFormSet(request.POST, instance=article)

        if form.is_valid() and step_formset.is_valid():
            ArticleRevision.objects.get_or_create(
                article=article,
                version=prev_version,
                defaults={
                    "title": prev_title,
                    "summary": prev_summary,
                    "content": prev_content,
                    "change_summary": form.cleaned_data.get("change_summary", ""),
                    "edited_by": request.user,
                },
            )

            article = form.save(commit=False)
            article.version = prev_version + 1
            article.save()
            form.save_m2m()
            form._save_tags(article)

            if request.user != article.author:
                article.contributors.add(request.user)

            step_formset.save()
            _save_multi_attachments(request, article=article)
            _log_audit(
                request,
                AuditLog.Action.ARTICLE_UPDATED,
                obj=article,
                details={"version": article.version, "summary": form.cleaned_data.get("change_summary", "")},
            )

            messages.success(request, f"Article updated (v{article.version}).")
            return redirect(article.get_absolute_url())
        messages.error(request, "Please correct the errors below.")
    else:
        form = ArticleForm(instance=article, user=request.user)
        step_formset = ResolutionStepFormSet(instance=article)

    categories_list = list(Category.objects.filter(is_active=True).order_by("name").values("id", "name", "category_type"))
    return render(request, "knowledge/article_form.html", {
        "page_title": f"Edit — {article.title}",
        "form": form,
        "step_formset": step_formset,
        "article": article,
        "categories_json": categories_list,
        "is_create": False,
    })


@login_required
def article_revisions(request, slug: str):
    article = get_object_or_404(Article, slug=slug)
    if not article.can_view(request.user):
        return render(request, "403.html", status=403)
    revisions = article.revisions.select_related("edited_by").order_by("-version")
    return render(request, "knowledge/article_revisions.html", {
        "page_title": f"Revision History — {article.title}",
        "article": article,
        "revisions": revisions,
    })


@login_required
@require_POST
def article_delete(request, slug: str):
    article = get_object_or_404(Article, slug=slug)
    if not article.can_delete(request.user):
        return HttpResponseForbidden("Only Administrators can delete articles.")

    title = article.title
    _log_audit(
        request,
        AuditLog.Action.ARTICLE_DELETED,
        target_type="Article",
        target_id=str(article.pk),
        target_repr=title,
    )
    article.delete()
    messages.success(request, f'Article "{title}" has been deleted.')
    return redirect("article_list")


# ─────────────────────────────────────────────────────────────────────────────
# ATTACHMENTS, COLLABORATION, FEEDBACK & BOOKMARKS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def download_attachment(request, pk: int):
    attachment = get_object_or_404(Attachment, pk=pk)
    perm_name = f"{Attachment._meta.app_label}.view_attachment"
    if not request.user.has_perm(perm_name, attachment):
        return render(request, "403.html", status=403)

    return FileResponse(
        attachment.file.open("rb"),
        as_attachment=not attachment.is_image,
        filename=attachment.original_name,
    )


@login_required
@require_POST
def delete_attachment(request, pk: int):
    attachment = get_object_or_404(Attachment, pk=pk)
    allowed = request.user.is_admin or (
        attachment.uploaded_by_id == request.user.id and request.user.is_engineer
    )
    if not allowed and attachment.project:
        allowed = attachment.project.can_manage_members(request.user)
    if not allowed and attachment.activity:
        allowed = attachment.activity.project.can_manage_members(request.user)
    if not allowed and attachment.article:
        allowed = attachment.article.author_id == request.user.id

    if allowed:
        attachment.file.delete(save=False)
        attachment.delete()
        return JsonResponse({"success": True})
    return JsonResponse({"success": False, "error": "Permission denied."}, status=403)


@login_required
@require_POST
def add_comment(request, slug: str):
    article = get_object_or_404(Article, slug=slug)
    if not article.can_view(request.user):
        return render(request, "403.html", status=403)
    if request.user.role == User.Role.VIEWER:
        return HttpResponseForbidden("Viewers cannot post comments.")

    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.article = article
        comment.author = request.user
        parent_id = request.POST.get("parent_id")
        if parent_id:
            comment.parent = Comment.objects.filter(pk=parent_id, article=article).first()
        comment.save()
        _save_multi_attachments(request, comment=comment)
        if article.author != request.user:
            Notification.objects.create(
                user=article.author,
                notification_type=Notification.NotificationType.COMMENT,
                title=f"New update on: {article.title}",
                message=f"{request.user.full_name} commented on your article.",
                article=article,
            )
        messages.success(request, "Collaboration update added.")
    else:
        messages.error(request, "Your comment could not be saved.")

    return redirect(f"{article.get_absolute_url()}#comments")


@login_required
@require_POST
def article_feedback(request, slug: str):
    article = get_object_or_404(Article, slug=slug, status=Article.Status.PUBLISHED)
    if not article.can_view(request.user):
        return JsonResponse({"success": False, "error": "Permission denied."}, status=403)

    is_helpful = request.POST.get("is_helpful") == "true"
    ArticleFeedback.objects.update_or_create(
        article=article,
        user=request.user,
        defaults={"is_helpful": is_helpful, "feedback_text": request.POST.get("feedback_text", "")},
    )

    helpful = ArticleFeedback.objects.filter(article=article, is_helpful=True).count()
    not_helpful = ArticleFeedback.objects.filter(article=article, is_helpful=False).count()
    Article.objects.filter(pk=article.pk).update(helpful_votes=helpful, not_helpful_votes=not_helpful)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "helpful_votes": helpful,
            "not_helpful_votes": not_helpful,
            "score": round((helpful / (helpful + not_helpful)) * 100) if (helpful + not_helpful) else 0,
        })

    messages.success(request, "Thank you for your feedback!")
    return redirect(article.get_absolute_url())


@login_required
@require_POST
def toggle_article_bookmark(request, slug: str):
    article = get_object_or_404(Article, slug=slug)
    if not article.can_view(request.user):
        return JsonResponse({"success": False}, status=403)
    bm = Bookmark.objects.filter(user=request.user, article=article).first()
    if bm:
        bm.delete()
        bookmarked = False
    else:
        Bookmark.objects.create(user=request.user, article=article)
        bookmarked = True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "bookmarked": bookmarked})
    return redirect(article.get_absolute_url())


@login_required
@require_POST
def toggle_project_bookmark(request, slug: str):
    project = get_object_or_404(Project, slug=slug)
    if not project.can_view(request.user):
        return JsonResponse({"success": False}, status=403)
    bm = Bookmark.objects.filter(user=request.user, project=project).first()
    if bm:
        bm.delete()
        bookmarked = False
    else:
        Bookmark.objects.create(user=request.user, project=project)
        bookmarked = True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "bookmarked": bookmarked})
    return redirect(project.get_absolute_url())


@login_required
def bookmark_list(request):
    bookmarks = Bookmark.objects.filter(user=request.user).select_related(
        "article__category", "project__category"
    )
    return render(request, "knowledge/bookmarks.html", {
        "page_title": "My Saved Bookmarks",
        "bookmarks": bookmarks,
    })


# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED SEARCH & REAL-TIME SUGGESTIONS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def search_view(request):
    form = SearchForm(request.GET or None)
    q = request.GET.get("q", "").strip()
    scope = request.GET.get("scope", "all")

    project_results = Project.objects.none()
    article_results = None
    total_count = 0

    if q and len(q) >= 2:
        if scope in ("all", "projects"):
            p_qs = Project.objects.visible_to(request.user).select_related("category", "project_lead").filter(
                Q(project_code__icontains=q)
                | Q(title__icontains=q)
                | Q(client_or_unit__icontains=q)
                | Q(summary__icontains=q)
                | Q(scope_notes__icontains=q)
                | Q(microsoft_products__icontains=q)
                | Q(tech_stack__icontains=q)
                | Q(documents__title__icontains=q)
                | Q(documents__original_name__icontains=q)
                | Q(activities__title__icontains=q)
                | Q(tags__name__icontains=q)
            ).distinct()
            if form.is_valid() and form.cleaned_data.get("category"):
                p_qs = p_qs.filter(category=form.cleaned_data["category"])
            project_results = p_qs.order_by("-updated_at")[:20]

        if scope in ("all", "articles"):
            a_qs = (
                Article.objects.visible_to(request.user)
                .filter(status=Article.Status.PUBLISHED)
                .select_related("author", "category", "related_project")
                .prefetch_related("tags")
                .filter(
                    Q(title__icontains=q)
                    | Q(summary__icontains=q)
                    | Q(symptoms__icontains=q)
                    | Q(root_cause__icontains=q)
                    | Q(content__icontains=q)
                    | Q(search_keywords__icontains=q)
                    | Q(error_codes__icontains=q)
                    | Q(microsoft_products__icontains=q)
                    | Q(affected_systems__icontains=q)
                    | Q(tech_stack__icontains=q)
                    | Q(tags__name__icontains=q)
                    | Q(steps__code_snippet__icontains=q)
                )
                .distinct()
            )
            if form.is_valid():
                if form.cleaned_data.get("article_type"):
                    a_qs = a_qs.filter(article_type=form.cleaned_data["article_type"])
                if form.cleaned_data.get("category"):
                    a_qs = a_qs.filter(category=form.cleaned_data["category"])
                if form.cleaned_data.get("severity"):
                    a_qs = a_qs.filter(severity=form.cleaned_data["severity"])
                a_qs = a_qs.order_by(form.cleaned_data.get("sort") or "-updated_at")

            article_results = _paginate(request, a_qs)

        art_count = article_results.paginator.count if article_results else 0
        total_count = project_results.count() + art_count

        SearchLog.objects.create(
            query=q,
            user=request.user,
            results_count=min(total_count, 32767),
            ip_address=_get_client_ip(request),
        )

    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(request, "knowledge/search_results.html", {
        "page_title": f'Search: "{q}"' if q else "Search Repository",
        "form": form,
        "query": q,
        "scope": scope,
        "project_results": project_results,
        "results": article_results,
        "results_count": total_count,
        "query_string": query_params.urlencode(),
    })


@login_required
@require_GET
def search_suggestions(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"suggestions": []})

    user = request.user
    limit = getattr(settings, "SEARCH_SUGGESTIONS_LIMIT", 6)
    cache_ttl = getattr(settings, "SEARCH_SUGGESTIONS_CACHE_TTL", 180)
    cache_key = f"search_sug:u{user.pk}:{q.lower()}"

    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"suggestions": cached, "query": q})

    suggestions = []

    proj_qs = (
        Project.objects.visible_to(user)
        .filter(
            Q(project_code__icontains=q)
            | Q(title__icontains=q)
            | Q(client_or_unit__icontains=q)
            | Q(microsoft_products__icontains=q)
        )
        .select_related("category")
        .order_by("-updated_at")[:3]
    )
    for proj in proj_qs:
        suggestions.append({
            "type": "project",
            "label": f"[{proj.project_code}] {proj.title}",
            "url": proj.get_absolute_url(),
            "meta": proj.get_status_display(),
            "icon": "briefcase",
        })

    art_qs = (
        Article.objects.visible_to(user)
        .filter(status=Article.Status.PUBLISHED)
        .filter(
            Q(title__icontains=q)
            | Q(error_codes__icontains=q)
            | Q(microsoft_products__icontains=q)
        )
        .select_related("category")
        .order_by("-views_count")[:limit]
    )
    for art in art_qs:
        suggestions.append({
            "type": "article",
            "label": art.title,
            "url": art.get_absolute_url(),
            "meta": art.category.name if art.category else "General",
            "article_type": art.article_type,
            "icon": "wrench-screwdriver" if art.article_type == Article.ArticleType.SUPPORT else "document-text",
        })

    for cat in Category.objects.filter(is_active=True, name__icontains=q).order_by("name")[:2]:
        suggestions.append({
            "type": "category",
            "label": cat.name,
            "url": cat.get_absolute_url(),
            "meta": cat.get_category_type_display(),
            "icon": "folder",
        })

    for tag in Tag.objects.filter(name__icontains=q).order_by("-usage_count")[:2]:
        suggestions.append({
            "type": "tag",
            "label": f"#{tag.name}",
            "url": tag.get_absolute_url(),
            "meta": "Tag",
            "icon": "tag",
        })

    cache.set(cache_key, suggestions, cache_ttl)
    return JsonResponse({"suggestions": suggestions, "query": q})


# ─────────────────────────────────────────────────────────────────────────────
# TAXONOMIES, NOTIFICATIONS & ENTERPRISE GOVERNANCE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def manage_categories(request):
    if not request.user.is_admin:
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            cat = form.save(commit=False)
            cat.created_by = request.user
            cat.save()
            form.save_m2m()
            messages.success(request, f'Category "{cat.name}" created.')
            return redirect("manage_categories")
        messages.error(request, "Please correct the category form errors.")
    else:
        form = CategoryForm()

    categories = Category.objects.annotate(
        total_articles=Count("articles", distinct=True),
        total_projects=Count("projects", distinct=True),
    ).order_by("-is_active", "sort_order", "name")

    return render(request, "knowledge/manage_categories.html", {
        "page_title": "Taxonomy Management",
        "categories": categories,
        "form": form,
    })


@login_required
def category_detail(request, slug: str):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    child_ids = list(category.children.values_list("pk", flat=True))
    all_cat_ids = [category.pk] + child_ids

    projects = (
        Project.objects.visible_to(request.user)
        .filter(category__in=all_cat_ids)
        .exclude(status=Project.Status.ARCHIVED)
        .select_related("category", "project_lead")
        .order_by("-updated_at")[:8]
    )
    articles_qs = (
        Article.objects.visible_to(request.user)
        .filter(status=Article.Status.PUBLISHED, category__in=all_cat_ids)
        .select_related("author", "category")
        .prefetch_related("tags")
        .order_by("-updated_at")
    )

    return render(request, "knowledge/category_detail.html", {
        "page_title": category.name,
        "category": category,
        "projects": projects,
        "page_obj": _paginate(request, articles_qs),
        "subcategories": category.children.filter(is_active=True),
    })


@login_required
def tag_articles(request, slug: str):
    tag = get_object_or_404(Tag, slug=slug)
    projects = Project.objects.visible_to(request.user).filter(tags=tag).order_by("-updated_at")[:8]
    articles_qs = (
        Article.objects.visible_to(request.user)
        .filter(tags=tag, status=Article.Status.PUBLISHED)
        .select_related("author", "category")
        .order_by("-updated_at")
    )
    return render(request, "knowledge/tag_articles.html", {
        "page_title": f"#{tag.name}",
        "tag": tag,
        "projects": projects,
        "page_obj": _paginate(request, articles_qs),
    })


@login_required
def notifications_view(request):
    notifs = (
        Notification.objects.filter(user=request.user)
        .select_related("article", "project")
        .order_by("-created_at")
    )
    notifs.filter(is_read=False).update(is_read=True, read_at=timezone.now())
    return render(request, "knowledge/notifications.html", {
        "page_title": "Notifications",
        "notifications": _paginate(request, notifs, per_page=30),
    })


@login_required
def access_control_matrix(request):
    if not request.user.is_admin:
        return render(request, "403.html", status=403)

    if request.method == "POST":
        target_user = get_object_or_404(User, id=request.POST.get("user_id"))
        new_role = request.POST.get("role")
        is_active = request.POST.get("is_active") == "on"

        valid_roles = {choice[0] for choice in User.Role.choices}
        if new_role not in valid_roles:
            messages.error(request, "Invalid role specified.")
            return redirect("access_control_matrix")

        if target_user == request.user and (new_role != User.Role.ADMIN or not is_active):
            messages.error(request, "Security protection: You cannot demote or deactivate your own account.")
        else:
            old_role = target_user.role
            target_user.role = new_role
            target_user.is_active = is_active
            target_user.is_staff = (new_role == User.Role.ADMIN or target_user.is_superuser)
            target_user.save(update_fields=["role", "is_active", "is_staff"])

            _log_audit(
                request,
                AuditLog.Action.USER_ROLE_CHANGED,
                obj=target_user,
                details={"old_role": old_role, "new_role": new_role, "is_active": is_active},
            )
            messages.success(request, f"Updated access clearances for {target_user.full_name}.")
        return redirect("access_control_matrix")

    engineers = User.objects.prefetch_related("teams").order_by("first_name", "last_name", "email")
    return render(request, "accounts/access_control.html", {
        "page_title": "Access Control Matrix",
        "engineers": engineers,
        "role_choices": User.Role.choices,
    })


@login_required
def manage_teams(request):
    if not request.user.is_admin:
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = TeamForm(request.POST)
        if form.is_valid():
            team = form.save()
            _log_audit(request, AuditLog.Action.PERMISSION_CHANGED, obj=team)
            messages.success(request, f'Team "{team.name}" created.')
            return redirect("manage_teams")
    else:
        form = TeamForm()

    teams = Team.objects.select_related("lead").prefetch_related("members").order_by("name")
    return render(request, "accounts/manage_teams.html", {
        "page_title": "Engineering Teams",
        "teams": teams,
        "form": form,
    })


@login_required
def audit_log_list(request):
    if not request.user.is_admin:
        return render(request, "403.html", status=403)

    qs = AuditLog.objects.select_related("actor").order_by("-created_at")
    action_filter = request.GET.get("action", "")
    if action_filter:
        qs = qs.filter(action=action_filter)

    return render(request, "accounts/audit_logs.html", {
        "page_title": "Enterprise Audit Logs",
        "page_obj": _paginate(request, qs, per_page=40),
        "action_filter": action_filter,
        "action_choices": AuditLog.Action.choices,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

def error_403(request, exception=None):
    return render(request, "403.html", status=403)


def error_404(request, exception=None):
    return render(request, "404.html", status=404)


def error_500(request):
    return render(request, "500.html", status=500)