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
    ArticleFeedback, Notification, SearchLog,
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
    """Process any file upload submitted alongside an article form."""
    if "attachment_file" not in request.FILES:
        return
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        att = form.save(commit=False)
        att.article = article
        att.uploaded_by = request.user
        att.original_name = request.FILES["attachment_file"].name
        att.file_type = request.FILES["attachment_file"].content_type or ""
        att.file_size_bytes = request.FILES["attachment_file"].size
        att.save()


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
    """Aggregates and metrics counters across support and project environments."""
    user = request.user
    published_qs = Article.objects.filter(status=Article.Status.PUBLISHED)

    stats = {
        "total_support": published_qs.filter(article_type=Article.ArticleType.SUPPORT).count(),
        "total_project": published_qs.filter(article_type=Article.ArticleType.PROJECT).count(),
        "total_software": published_qs.filter(article_type=Article.ArticleType.SOFTWARE).count(),
        "total_general": published_qs.filter(article_type=Article.ArticleType.GENERAL).count(),
        "my_drafts": Article.objects.filter(author=user, status=Article.Status.DRAFT).count(),
        "needs_review": Article.objects.filter(needs_review=True, status=Article.Status.IN_REVIEW).count(),
    }

    recent_articles = (
        published_qs
        .select_related("author", "category")
        .prefetch_related("tags")
        .order_by("-published_at")[:settings.RECENT_ARTICLES_COUNT]
    )

    featured_articles = (
        published_qs
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
        published_qs
        .order_by("-views_count")
        .select_related("category")[:5]
    )

    categories = (
        Category.objects
        .filter(is_active=True, parent=None)
        .annotate(pub_count=Count(
            "articles",
            filter=Q(articles__status=Article.Status.PUBLISHED)
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
    """Displays knowledge articles with filtering capabilities."""
    form = SearchForm(request.GET or None)
    qs = (
        Article.objects
        .filter(status=Article.Status.PUBLISHED)
        .select_related("author", "category")
        .prefetch_related("tags")
    )

    if not request.user.can_publish():
        qs = qs.exclude(visibility=Article.Visibility.RESTRICTED)

    article_type = request.GET.get("type")
    category_slug = request.GET.get("category")
    tag_slug = request.GET.get("tag")
    sort = request.GET.get("sort", "-updated_at")

    if article_type:
        qs = qs.filter(article_type=article_type)
    if category_slug:
        cat = Category.objects.filter(slug=category_slug).first()
        if cat:
            qs = qs.filter(Q(category=cat) | Q(category__parent=cat))
    if tag_slug:
        qs = qs.filter(tags__slug=tag_slug)

    valid_sort = ["-updated_at", "-published_at", "-views_count", "-helpful_votes", "title"]
    if sort in valid_sort:
        qs = qs.order_by(sort)

    page_obj = _paginate(request, qs)

    return render(request, "knowledge/article_list.html", {
        "page_title": "Knowledge Base",
        "page_obj": page_obj,
        "form": form,
        "article_type": article_type,
        "category_slug": category_slug,
        "tag_slug": tag_slug,
        "sort": sort,
        "categories": Category.objects.filter(is_active=True, parent=None).order_by("sort_order"),
        "popular_tags": Tag.objects.order_by("-usage_count")[:20],
        "total_results": qs.count(),
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
    attachment_form = AttachmentForm() if request.user.can_edit_content() else None

    related_articles = (
        article.related_articles
        .filter(status=Article.Status.PUBLISHED)
        .select_related("category")[:4]
    )

    return render(request, "knowledge/article_detail.html", {
        "page_title": article.title,
        "article": article,
        "comment_form": comment_form,
        "attachment_form": attachment_form,
        "user_feedback": user_feedback,
        "related_articles": related_articles,
        "can_edit": (request.user == article.author or request.user.can_edit_content()),
        "can_delete": request.user.can_delete_content(),
    })


@login_required
def article_create(request):
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

    categories = Category.objects.filter(is_active=True).select_related("parent").order_by("name")

    return render(request, "knowledge/article_form.html", {
        "page_title": "Create New Article",
        "form": form,
        "step_formset": step_formset,
        "categories_json": json.dumps(list(categories.values("id", "name", "category_type"))),
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

    categories = Category.objects.filter(is_active=True).select_related("parent").order_by("name")

    return render(request, "knowledge/article_form.html", {
        "page_title": f"Edit — {article.title}",
        "form": form,
        "step_formset": step_formset,
        "article": article,
        "categories_json": json.dumps(list(categories.values("id", "name", "category_type"))),
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
        parent_id = request.POST.get("parent_id")
        if parent_id:
            comment.parent = Comment.objects.filter(pk=parent_id, article=article).first()
        comment.save()
        messages.success(request, "Comment added.")
    else:
        messages.error(request, "Your comment could not be saved.")

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
    results = []

    if q and len(q) >= 2:
        qs = Article.objects.filter(
            status=Article.Status.PUBLISHED
        ).select_related("author", "category").prefetch_related("tags")

        if not request.user.can_publish():
            qs = qs.exclude(visibility=Article.Visibility.RESTRICTED)

        qs = qs.filter(
            Q(title__icontains=q)
            | Q(summary__icontains=q)
            | Q(content__icontains=q)
            | Q(search_keywords__icontains=q)
            | Q(error_codes__icontains=q)
            | Q(microsoft_products__icontains=q)
            | Q(tags__name__icontains=q)
        ).distinct()

        if form.is_valid():
            if form.cleaned_data.get("article_type"):
                qs = qs.filter(article_type=form.cleaned_data["article_type"])
            if form.cleaned_data.get("category"):
                qs = qs.filter(category=form.cleaned_data["category"])
            if form.cleaned_data.get("severity"):
                qs = qs.filter(severity=form.cleaned_data["severity"])
            sort = form.cleaned_data.get("sort", "-updated_at")
            qs = qs.order_by(sort)

        SearchLog.objects.create(
            query=q,
            user=request.user,
            results_count=qs.count(),
            ip_address=_get_client_ip(request),
        )

        results = _paginate(request, qs)

    return render(request, "knowledge/search_results.html", {
        "page_title": f'Search: "{q}"' if q else "Search",
        "form": form,
        "query": q,
        "results": results,
    })


@login_required
@require_GET
def search_suggestions(request):
    """
    Asynchronous lookup channel grouping type-ahead results live as engineers type.
    Utilizes caching strategies to limit database scanning overhead.
    """
    q = request.GET.get("q", "").strip()

    if len(q) < 2:
        return JsonResponse({"suggestions": []})

    cache_key = f"search_suggestions:{q.lower()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"suggestions": cached})

    limit = settings.SEARCH_SUGGESTIONS_LIMIT
    suggestions = []

    article_qs = (
        Article.objects
        .filter(
            status=Article.Status.PUBLISHED,
            title__icontains=q,
        )
        .select_related("category")
        .order_by("-views_count")[:limit]
    )
    if not request.user.can_publish():
        article_qs = article_qs.exclude(visibility=Article.Visibility.RESTRICTED)

    for art in article_qs:
        suggestions.append({
            "type": "article",
            "label": art.title,
            "url": art.get_absolute_url(),
            "meta": art.category.name,
            "article_type": art.article_type,
            "icon": _article_type_icon(art.article_type),
        })

    cat_qs = Category.objects.filter(
        is_active=True, name__icontains=q
    ).order_by("name")[:4]
    for cat in cat_qs:
        suggestions.append({
            "type": "category",
            "label": cat.name,
            "url": cat.get_absolute_url(),
            "meta": cat.get_category_type_display(),
            "icon": "folder",
        })

    tag_qs = Tag.objects.filter(name__icontains=q).order_by("-usage_count")[:4]
    for tag in tag_qs:
        suggestions.append({
            "type": "tag",
            "label": tag.name,
            "url": tag.get_absolute_url(),
            "meta": f"{tag.usage_count} articles",
            "icon": "tag",
        })

    cache.set(cache_key, suggestions, settings.SEARCH_SUGGESTIONS_CACHE_TTL)
    return JsonResponse({"suggestions": suggestions, "query": q})


# ─────────────────────────────────────────────────────────────────────────────
# TAXONOMIES AND COMMUNICATIONS
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM SYSTEM EXCEPTION ERROR HANDLING INTERFACES
# ─────────────────────────────────────────────────────────────────────────────

def error_403(request, exception=None):
    return render(request, "403.html", status=403)


def error_404(request, exception=None):
    return render(request, "404.html", status=404)


def error_500(request):
    return render(request, "500.html", status=500)