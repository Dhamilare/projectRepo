import json
import logging
import secrets
from django.conf import settings
from django.contrib import auth, messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, F, Count, Prefetch
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from .backends import build_auth_url
from .forms import ArticleForm, ProjectStepFormSet, CommentForm, AttachmentForm, SearchForm
from .models import (
    User, Article, Category, Tag, Comment,
    ArticleFeedback, Notification, SearchLog, Attachment
)

logger = logging.getLogger("projectRepo")
_MS = settings.MICROSOFT_AUTH


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE UTILITY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_client_ip(request) -> str:
    """Safely extracts client IP passing upstream proxy environments."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


def _can_view_article(user, article: Article) -> bool:
    """Enforces role-based visibility control filters across technical articles."""
    if article.status != Article.Status.PUBLISHED:
        return user.is_authenticated and (
            article.author == user
            or user.can_edit_content()
        )
    if article.visibility == Article.Visibility.RESTRICTED:
        return user.is_authenticated and user.can_publish()
    if article.visibility == Article.Visibility.PRIVATE:
        return user.is_authenticated and article.author == user
    return True


def _paginate(request, qs, per_page=None):
    """Paginates records safely, handling fallback options for missing indexes."""
    per_page = per_page or settings.ARTICLES_PER_PAGE
    paginator = Paginator(qs, per_page)
    page_num = request.GET.get("page", 1)
    try:
        return paginator.page(page_num)
    except (PageNotAnInteger, EmptyPage):
        return paginator.page(1)


def _article_type_icon(article_type: str) -> str:
    """Maps custom article types directly onto frontend icon string styles."""
    return {
        "support": "wrench-screwdriver",
        "project": "clipboard-document-list",
        "software": "code-bracket",
        "general": "document-text",
    }.get(article_type, "document-text")


def _handle_attachment_upload(request, article):
    if "attachments" not in request.FILES:
        return
        
    uploaded_files = request.FILES.getlist("attachments")
    
    for file_obj in uploaded_files:
        Attachment.objects.create(
            article=article,
            file=file_obj,
            uploaded_by=request.user,
            file_name=file_obj.name,  
            file_size=file_obj.size, 
            file_type=file_obj.content_type or ""
        )

@login_required
@require_POST
def delete_attachment(request, pk: int):
    """Deletes an uploaded attachment node via an asynchronous request."""
    attachment = get_object_or_404(Attachment, pk=pk)
    
    if request.user == attachment.article.author or request.user.can_edit_content():
        attachment.file.delete(save=False) 
        attachment.delete()                
        return JsonResponse({"success": True})
    
    return JsonResponse({"success": False, "error": "Permission denied."}, status=403)

# ─────────────────────────────────────────────────────────────────────────────
# IDENTITY MANAGEMENT & MICROSOFT ENTRA OAUTH FLOWS
# ─────────────────────────────────────────────────────────────────────────────

def login_view(request):
    """Render the login window. If already authenticated, forward directly to workspace."""
    if request.user.is_authenticated:
        return redirect("dashboard")

    error = request.GET.get("error")
    return render(request, "accounts/login.html", {
        "page_title": "Sign In",
        "error": error,
    })


@require_http_methods(["GET"])
def microsoft_login(request):
    """
    Kicks off the interactive Microsoft Identity provider flow.
    Injects cryptographically secure state tokens to prevent CSRF injection.
    """
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    auth_url = build_auth_url(state)
    return redirect(auth_url)


@require_http_methods(["GET"])
def oauth_callback(request):
    """
    Processes token returns from Microsoft.
    Verifies state footprints and hooks identity mappings to local profiles.
    """
    received_state = request.GET.get("state", "")
    expected_state = request.session.pop("oauth_state", None)

    if not expected_state or received_state != expected_state:
        logger.warning("OAuth state mismatch — possible CSRF attack vector intercepted. IP: %s", _get_client_ip(request))
        messages.error(request, "Authentication failed: invalid state token.")
        return redirect("login")

    error = request.GET.get("error")
    if error:
        error_desc = request.GET.get("error_description", error)
        logger.warning("OAuth identity management failure: %s", error_desc)
        messages.error(request, f"Microsoft sign-in failed: {error_desc}")
        return redirect("login")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "No authorization code received from Microsoft.")
        return redirect("login")

    user = auth.authenticate(request, auth_code=code)

    if user is None:
        messages.error(request, "Authentication failed. Please try again or contact support.")
        return redirect("login")

    if not user.is_active:
        messages.error(request, "Your account is inactive. Please contact your administrator.")
        return redirect("login")

    auth.login(request, user, backend="projectRepo.backends.MicrosoftEntraBackend")
    user.record_login(ip_address=_get_client_ip(request))

    logger.info("Successful authenticated corporate session established for: %s", user.email)
    next_url = request.session.pop("next", None) or settings.LOGIN_REDIRECT_URL
    return redirect(next_url)


@login_required
@require_http_methods(["POST"])
def logout_view(request):
    """Logs out from the active session and invokes remote SSO clearance."""
    logger.info("SSO Session closing for identity: %s", request.user.email)
    auth.logout(request)
    
    post_logout_uri = request.build_absolute_uri(settings.LOGOUT_REDIRECT_URL)
    ms_logout = (
        f"https://login.microsoftonline.com/{_MS['TENANT_ID']}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={post_logout_uri}"
    )
    return redirect(ms_logout)


@login_required
def profile_view(request):
    """Renders user identity profiles along with author telemetry summaries."""
    user = request.user
    authored_articles = (
        Article.objects.filter(author=user, status=Article.Status.PUBLISHED)
        .select_related("category")
        .order_by("-updated_at")[:10]
    )
    return render(request, "accounts/profile.html", {
        "page_title": f"{user.full_name} — Profile",
        "authored_articles": authored_articles,
        "total_articles": Article.objects.filter(author=user).count(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# CORE OPERATIONS WORKSPACE (DASHBOARD)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    """Aggregates metrics counters and feeds isolated strictly by the engineer's Azure department."""
    user = request.user
    
    # DEPARTMENT ISOLATION: Superusers see everything; otherwise filter content to match user's technical domain
    if user.is_superuser or user.role == "admin":
        base_published_qs = Article.objects.filter(status=Article.Status.PUBLISHED)
        base_all_qs = Article.objects.all()
    else:
        # Matches user's exact department string (case-insensitive) or pulls general institutional posts
        base_published_qs = Article.objects.filter(
            status=Article.Status.PUBLISHED
        ).filter(Q(author__department__iexact=user.department) | Q(visibility=Article.Visibility.PUBLIC))
        
        base_all_qs = Article.objects.filter(Q(author__department__iexact=user.department) | Q(author=user))

    stats = {
        "total_support": base_published_qs.filter(article_type=Article.ArticleType.SUPPORT).count(),
        "total_project": base_published_qs.filter(article_type=Article.ArticleType.PROJECT).count(),
        "total_software": base_published_qs.filter(article_type=Article.ArticleType.SOFTWARE).count(),
        "total_general": base_published_qs.filter(article_type=Article.ArticleType.GENERAL).count(),
        "my_drafts": base_all_qs.filter(author=user, status=Article.Status.DRAFT).count(),
        "needs_review": base_all_qs.filter(needs_review=True, status=Article.Status.IN_REVIEW).count(),
    }

    recent_articles = (
        base_published_qs
        .select_related("author", "category")
        .prefetch_related("tags")
        .order_by("-published_at")[:settings.RECENT_ARTICLES_COUNT]
    )

    featured_articles = (
        base_published_qs
        .filter(is_featured=True)
        .select_related("author", "category")
        .order_by("-updated_at")[:4]
    )

    my_recent_activity = (
        Article.objects
        .filter(Q(author=user) | Q(contributors=user))
        .distinct()
        .select_related("category")
        .order_by("-updated_at")[:5]
    )

    popular_articles = (
        base_published_qs
        .order_by("-views_count")
        .select_related("category")[:5]
    )

    categories = (
        Category.objects
        .filter(is_active=True, parent=None)
        .annotate(pub_count=Count(
            "articles",
            filter=Q(articles__status=Article.Status.PUBLISHED, articles__author__department__iexact=user.department) if not (user.is_superuser or user.role == "admin") else Q(articles__status=Article.Status.PUBLISHED)
        ))
        .order_by("sort_order")
    )

    notifications = (
        Notification.objects
        .filter(user=user, is_read=False)
        .select_related("article")
        .order_by("-created_at")[:5]
    )

    return render(request, "knowledge/dashboard.html", {
        "page_title": "Dashboard",
        "stats": stats,
        "recent_articles": recent_articles,
        "featured_articles": featured_articles,
        "my_recent_activity": my_recent_activity,
        "popular_articles": popular_articles,
        "categories": categories,
        "notifications": notifications,
        "unread_count": notifications.count(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE BASE ARTICLE RECORD MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def article_list(request):
    """Displays knowledge articles matching filters, bounded by departmental permissions."""
    form = SearchForm(request.GET or None)
    user = request.user
    
    if user.is_superuser or user.role == "admin":
        qs = Article.objects.filter(status=Article.Status.PUBLISHED).select_related("author", "category").prefetch_related("tags")
    else:
        qs = Article.objects.filter(
            status=Article.Status.PUBLISHED
        ).filter(
            Q(author__department__iexact=user.department) | Q(visibility=Article.Visibility.PUBLIC)
        ).select_related("author", "category").prefetch_related("tags")

    if not request.user.can_publish():
        qs = qs.exclude(visibility=Article.Visibility.RESTRICTED)

    article_type = request.GET.get("type")
    category_param = request.GET.get("category")
    severity = request.GET.get("severity")
    tag_slug = request.GET.get("tag")
    sort = request.GET.get("sort", "-updated_at")

    if article_type:
        qs = qs.filter(article_type=article_type)

    if category_param:
        if category_param.isdigit():
            cat = Category.objects.filter(pk=int(category_param)).first()
        else:
            cat = Category.objects.filter(slug=category_param).first()
            
        if cat:
            qs = qs.filter(Q(category=cat) | Q(category__parent=cat))

    if severity and severity != "all":
        qs = qs.filter(severity=severity)

    if tag_slug:
        qs = qs.filter(tags__slug=tag_slug)

    valid_sort = ["-updated_at", "-published_at", "-views_count", "-helpful_votes", "title"]
    if sort in valid_sort:
        qs = qs.order_by(sort)

    total_results = qs.count()
    page_obj = _paginate(request, qs)

    query_params = request.GET.copy()
    if "page" in query_params:
        del query_params["page"]

    return render(request, "knowledge/article_list.html", {
        "page_title": "Knowledge Base",
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
    """Renders comprehensive documentation assets along with feedback controls."""
    article = get_object_or_404(
        Article.objects.select_related("author", "category", "reviewed_by")
        .prefetch_related(
            "tags", "contributors", "attachments",
            "steps",
            Prefetch(
                "comments",
                queryset=Comment.objects
                    .filter(is_approved=True, parent=None)
                    .select_related("author")
                    .prefetch_related(
                        Prefetch("replies", queryset=Comment.objects.filter(is_approved=True).select_related("author"))
                    ),
            ),
        ),
        slug=slug,
    )

    if not _can_view_article(request.user, article):
        return render(request, "403.html", status=403)

    # Track distinct session view actions
    session_key = f"viewed_{article.pk}"
    if not request.session.get(session_key):
        article.increment_view(user=request.user, ip_address=_get_client_ip(request))
        request.session[session_key] = True

    user_feedback = None
    if request.user.is_authenticated:
        user_feedback = ArticleFeedback.objects.filter(
            article=article, user=request.user
        ).first()

    comment_form = CommentForm()

    related_articles = (
        article.related_articles
        .filter(status=Article.Status.PUBLISHED)
        .select_related("category")[:4]
    )

    return render(request, "knowledge/article_detail.html", {
        "page_title": article.title,
        "article": article,
        "comment_form": comment_form,
        "user_feedback": user_feedback,
        "related_articles": related_articles,
        "can_edit": (request.user == article.author or request.user.can_edit_content()),
        "can_delete": request.user.can_delete_content(),
    })


@login_required
def article_create(request):
    # CONSTRAINT: Only Administrators and Engineers are allowed to build documents
    if request.user.role == "technician" or not request.user.can_edit_content():
        messages.error(request, "Access Denied: Your technical profile classification does not grant item authoring privileges.")
        return redirect("dashboard")
    
    """Builds structural asset profiles mapping input steps cleanly onto database models."""
    if not request.user.can_edit_content():
        messages.error(request, "You don't have permission to create articles.")
        return redirect("dashboard")

    initial_type = request.GET.get("type", Article.ArticleType.SUPPORT)

    if request.method == "POST":
        form = ArticleForm(request.POST, user=request.user)
        step_formset = ProjectStepFormSet(request.POST)

        if form.is_valid() and step_formset.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            form.save_m2m()
            form._save_tags(article)

            if article.article_type == Article.ArticleType.PROJECT:
                step_formset.instance = article
                step_formset.save()

            _handle_attachment_upload(request, article)

            messages.success(request, f'Article "{article.title}" saved successfully.')
            logger.info("Article created: %s by %s", article.pk, request.user.email)
            return redirect(article.get_absolute_url())
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ArticleForm(user=request.user, initial={"article_type": initial_type})
        step_formset = ProjectStepFormSet()

    categories_queryset = Category.objects.filter(is_active=True).order_by("name")
    categories_list = list(categories_queryset.values("id", "name", "category_type"))

    return render(request, "knowledge/article_form.html", {
        "page_title": "Create New Article",
        "form": form,
        "step_formset": step_formset,
        "categories_json": categories_list,
        "is_create": True,
    })


@login_required
def article_edit(request, slug: str):
    """Alters structural documentation parameters, parsing modifications securely."""
    article = get_object_or_404(Article, slug=slug)

    can_edit = (request.user == article.author or request.user.can_edit_content())
    if not can_edit:
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = ArticleForm(request.POST, instance=article, user=request.user)
        step_formset = ProjectStepFormSet(request.POST, instance=article)

        if form.is_valid() and step_formset.is_valid():
            article = form.save()

            if article.article_type == Article.ArticleType.PROJECT:
                step_formset.save()

            _handle_attachment_upload(request, article)

            messages.success(request, "Article updated successfully.")
            logger.info("Article updated: %s by %s", article.pk, request.user.email)
            return redirect(article.get_absolute_url())
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ArticleForm(instance=article, user=request.user)
        step_formset = ProjectStepFormSet(instance=article)

    categories_queryset = Category.objects.filter(is_active=True).order_by("name")
    categories_list = list(categories_queryset.values("id", "name", "category_type"))

    return render(request, "knowledge/article_form.html", {
        "page_title": f"Edit — {article.title}",
        "form": form,
        "step_formset": step_formset,
        "article": article,
        "categories_json": categories_list,
        "is_create": False,
    })


@login_required
@require_POST
def article_delete(request, slug: str):
    """Deletes reference rows cleanly, logging out structural lifecycle parameters."""
    article = get_object_or_404(Article, slug=slug)

    if not request.user.can_delete_content() and request.user != article.author:
        return HttpResponseForbidden("You don't have permission to delete this article.")

    title = article.title
    article.delete()
    messages.success(request, f'Article "{title}" has been deleted.')
    logger.info("Article deleted: '%s' by %s", title, request.user.email)
    return redirect("article_list")


# ─────────────────────────────────────────────────────────────────────────────
# COLLABORATION & TELEMETRY TRACKERS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def add_comment(request, slug: str):
    """Appends collaborative entries directly onto active engineering articles."""
    article = get_object_or_404(Article, slug=slug, status=Article.Status.PUBLISHED)
    form = CommentForm(request.POST)

    if form.is_valid():
        comment = form.save(commit=False)
        comment.article = article
        comment.author = request.user
        comment.is_approved = True 
        
        parent_id = request.POST.get("parent_id")
        if parent_id:
            comment.parent = Comment.objects.filter(pk=parent_id, article=article).first()
        comment.save()
        messages.success(request, "Engineering collaboration node added to matrix feed.")
    else:
        messages.error(request, "Your comment could not be saved due to validation constraints.")

    return redirect(f"{article.get_absolute_url()}#comments")


@login_required
@require_POST
def article_feedback(request, slug: str):
    """Calculates helpfulness ratios, outputting clean updates back to clients via JSON."""
    article = get_object_or_404(Article, slug=slug, status=Article.Status.PUBLISHED)
    is_helpful = request.POST.get("is_helpful") == "true"

    feedback, created = ArticleFeedback.objects.update_or_create(
        article=article, user=request.user,
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


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH ENGINES & REAL-TIME AUTO-SUGGESTIONS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def search_view(request):
    """Executes thorough keyword scanning against technical records and error tables."""
    form = SearchForm(request.GET or None)
    q = request.GET.get("q", "").strip()
    results = None
    results_count = 0

    if q and len(q) >= 2:
        qs = (
            Article.objects.filter(status=Article.Status.PUBLISHED)
            .select_related("author", "category")
            .prefetch_related("tags")
        )

        if not (request.user.is_superuser or request.user.role == "admin"):
            qs = qs.filter(
                Q(author__department__iexact=request.user.department)
                | Q(visibility=Article.Visibility.PUBLIC)
            )

        if not request.user.can_publish():
            qs = qs.exclude(visibility=Article.Visibility.RESTRICTED)

        qs = qs.filter(
            Q(title__icontains=q)
            | Q(summary__icontains=q)
            | Q(content__icontains=q)
            | Q(search_keywords__icontains=q)
            | Q(error_codes__icontains=q)
            | Q(microsoft_products__icontains=q)  
            | Q(affected_systems__icontains=q)
            | Q(tech_stack__icontains=q)
            | Q(project_type__icontains=q)
            | Q(tags__name__icontains=q)
            | Q(steps__code_snippet__icontains=q)  
        ).distinct()

        if form.is_valid():
            if form.cleaned_data.get("article_type"):
                qs = qs.filter(article_type=form.cleaned_data["article_type"])
            if form.cleaned_data.get("category"):
                qs = qs.filter(category=form.cleaned_data["category"])
            if form.cleaned_data.get("severity"):
                qs = qs.filter(severity=form.cleaned_data["severity"])

            sort = form.cleaned_data.get("sort") or "-updated_at"
            qs = qs.order_by(sort)

        results = _paginate(request, qs)
        results_count = results.paginator.count if hasattr(results, "paginator") else 0

        SearchLog.objects.create(
            query=q,
            user=request.user,
            results_count=results_count,
            ip_address=_get_client_ip(request),
        )

    query_params = request.GET.copy()
    if "page" in query_params:
        del query_params["page"]

    return render(
        request,
        "knowledge/search_results.html",
        {
            "page_title": f'Search: "{q}"' if q else "Search System Vault",
            "form": form,
            "query": q,
            "results": results,
            "results_count": results_count,
            "query_string": query_params.urlencode(),
        },
    )


@login_required
@require_GET
def search_suggestions(request):
    """
    Asynchronous lookup channel grouping type-ahead results live as engineers type.
    Enforces strict access control and utilizes role-scoped caching strategies.
    """
    q = request.GET.get("q", "").strip()

    if len(q) < 2:
        return JsonResponse({"suggestions": []})

    user = request.user
    limit = getattr(settings, "SEARCH_SUGGESTIONS_LIMIT", 5)
    cache_ttl = getattr(settings, "SEARCH_SUGGESTIONS_CACHE_TTL", 300)

    # Scopes cache keys per user role & department to prevent authorization data leaks
    dept_key = user.department.lower().replace(" ", "_") if user.department else "noddept"
    role_key = user.role if hasattr(user, "role") else "user"
    cache_key = f"search_sug:{dept_key}:{role_key}:{q.lower()}"

    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"suggestions": cached, "query": q})

    suggestions = []

    # 1. ARTICLE QUERYSET WITH DEPARTMENT ACCESS ISOLATION
    article_qs = Article.objects.filter(status=Article.Status.PUBLISHED)

    if not (user.is_superuser or user.role == "admin"):
        article_qs = article_qs.filter(
            Q(author__department__iexact=user.department)
            | Q(visibility=Article.Visibility.PUBLIC)
        )

    if not user.can_publish():
        article_qs = article_qs.exclude(visibility=Article.Visibility.RESTRICTED)

    # Expanded type-ahead lookup: Title, Error Codes, and Microsoft Product lines
    article_qs = (
        article_qs.filter(
            Q(title__icontains=q)
            | Q(error_codes__icontains=q)
            | Q(microsoft_products__icontains=q)
        )
        .select_related("category")
        .order_by("-views_count")[:limit]
    )

    for art in article_qs:
        suggestions.append({
            "type": "article",
            "label": art.title,
            "url": art.get_absolute_url(),
            "meta": art.category.name if art.category else "General",
            "article_type": art.article_type,
            "icon": _article_type_icon(art.article_type),
        })

    # 2. CATEGORY MATCHES
    cat_qs = Category.objects.filter(
        is_active=True, 
        name__icontains=q
    ).order_by("name")[:3]
    
    for cat in cat_qs:
        suggestions.append({
            "type": "category",
            "label": cat.name,
            "url": cat.get_absolute_url(),
            "meta": cat.get_category_type_display(),
            "icon": "folder",
        })

    # 3. TAG MATCHES
    tag_qs = Tag.objects.filter(name__icontains=q).order_by("-usage_count")[:3]
    for tag in tag_qs:
        suggestions.append({
            "type": "tag",
            "label": f"#{tag.name}",
            "url": tag.get_absolute_url(),
            "meta": f"{tag.usage_count} record{'s' if tag.usage_count != 1 else ''}",
            "icon": "tag",
        })
        
    cache.set(cache_key, suggestions, cache_ttl)

    return JsonResponse({"suggestions": suggestions, "query": q})


# ─────────────────────────────────────────────────────────────────────────────
# TAXONOMIES AND COMMUNICATIONS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def manage_categories(request):
    if request.user.role != "admin" and not request.user.is_superuser:
        return render(request, "403.html", status=403)
        
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category_type = request.POST.get("category_type", "general")
        color_hex = request.POST.get("color_hex", "#2563EB").strip()
        description = request.POST.get("description", "").strip()
        
        if not name:
            messages.error(request, "Validation Error: Category name identifier cannot be blank.")
        else:
            from django.utils.text import slugify
            slug = slugify(name)
            
            # Check for duplicate slugs to prevent URL routing collisions
            if Category.objects.filter(slug=slug).exists():
                messages.error(request, f"Conflict: A taxonomy node matching the identifier '{name}' already exists.")
            else:
                Category.objects.create(
                    name=name,
                    slug=slug,
                    category_type=category_type,
                    color_hex=color_hex,
                    description=description,
                    created_by=request.user,
                    is_active=True
                )
                messages.success(request, f"Successfully committed taxonomy branch node '{name}' to the central vault.")
                logger.info("Taxonomy Configuration Altered: %s created category %s", request.user.email, name)
                return redirect("manage_categories")

    categories = Category.objects.all().annotate(
        total_articles=Count("articles")
    ).order_by("-is_active", "sort_order", "name")
    
    return render(request, "knowledge/manage_categories.html", {
        "page_title": "Taxonomy Management Console",
        "categories": categories,
        "type_choices": [('support', 'Support Fixes focus'), ('project', 'Project Playbooks focus'), ('general', 'General Infrastructure Scope')]
    })


@login_required
def category_detail(request, slug: str):
    """Displays category components alongside child pathways."""
    category = get_object_or_404(Category, slug=slug, is_active=True)

    child_ids = list(category.children.values_list("pk", flat=True))
    all_cat_ids = [category.pk] + child_ids

    qs = (
        Article.objects
        .filter(status=Article.Status.PUBLISHED, category__in=all_cat_ids)
        .select_related("author", "category")
        .prefetch_related("tags")
        .order_by("-updated_at")
    )

    return render(request, "knowledge/category_detail.html", {
        "page_title": category.name,
        "category": category,
        "page_obj": _paginate(request, qs),
        "subcategories": category.children.filter(is_active=True).annotate(
            pub_count=Count("articles", filter=Q(articles__status=Article.Status.PUBLISHED))
        ),
    })


@login_required
def tag_articles(request, slug: str):
    """Displays documentation records that utilize specific matching metadata labels."""
    tag = get_object_or_404(Tag, slug=slug)
    qs = (
        tag.articles
        .filter(status=Article.Status.PUBLISHED)
        .select_related("author", "category")
        .order_by("-updated_at")
    )
    return render(request, "knowledge/tag_articles.html", {
        "page_title": f"#{tag.name}",
        "tag": tag,
        "page_obj": _paginate(request, qs),
    })


@login_required
def notifications_view(request):
    """Renders automated alert indicators, marking records read dynamically."""
    notifs = (
        Notification.objects
        .filter(user=request.user)
        .select_related("article")
        .order_by("-created_at")
    )
    unread = notifs.filter(is_read=False)
    unread.update(is_read=True, read_at=timezone.now())

    return render(request, "knowledge/notifications.html", {
        "page_title": "Notifications",
        "notifications": _paginate(request, notifs, per_page=30),
    })


@login_required
def access_control_matrix(request):
    if request.user.role != "admin" and not request.user.is_superuser:
        return render(request, "403.html", status=403)
        
    if request.method == "POST":
        target_user_id = request.POST.get("user_id")
        new_role = request.POST.get("role")
        
        target_user = get_object_or_404(User, id=target_user_id)
        
        if target_user == request.user and new_role != "admin":
            messages.error(request, "Security protection: You cannot remove your own administrative designation.")
        else:
            target_user.role = new_role
            target_user.is_staff = (new_role == "admin")
            target_user.save()
            messages.success(request, f"Updated clearances for {target_user.full_name}.")
            
        return redirect("access_control_matrix")

    engineers = User.objects.all().order_by("first_name", "last_name")
    
    return render(request, "accounts/access_control.html", {
        "page_title": "Access Control Matrix Hub",
        "engineers": engineers,
        "role_choices": User.Role.choices, 
    })


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM SYSTEM EXCEPTION ERROR HANDLING INTERFACES
# ─────────────────────────────────────────────────────────────────────────────

def error_403(request, exception=None):
    return render(request, "403.html", status=403)


def error_404(request, exception=None):
    return render(request, "404.html", status=404)


def error_500(request):
    return render(request, "500.html", status=500)