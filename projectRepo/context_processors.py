from django.db.models import Count
from .models import Article, Category, Notification, Project, ProjectDocument, User


def global_context(request):
    """
    Injects permission-scoped, site-wide navigation, notification, review,
    and enum metadata into every template safely.
    """
    base_enums = {
        "ARTICLE_TYPES": Article.ArticleType,
        "PROJECT_STATUSES": Project.Status,
        "DOCUMENT_TYPES": ProjectDocument.DocumentType,
        "USER_ROLES": User.Role,
    }

    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "nav_categories": Category.objects.none(),
            "unread_notifications": 0,
            "recent_notifications": Notification.objects.none(),
            "pending_review": 0,
            "pending_doc_reviews": 0,
            "my_projects_count": 0,
            **base_enums,
        }

    user = request.user

    # 1. Permission-scoped counts per category (prevents leaking restricted items)
    visible_articles = Article.objects.visible_to(user).filter(
        status=Article.Status.PUBLISHED
    )
    article_counts = dict(
        visible_articles.values("category_id")
        .annotate(total=Count("id", distinct=True))
        .values_list("category_id", "total")
    )

    visible_projects = Project.objects.visible_to(user).exclude(
        status=Project.Status.ARCHIVED
    )
    project_counts = dict(
        visible_projects.values("category_id")
        .annotate(total=Count("id", distinct=True))
        .values_list("category_id", "total")
    )

    nav_categories = list(
        Category.objects.filter(is_active=True, parent=None).order_by("sort_order", "name")
    )
    for cat in nav_categories:
        cat.pub_count = article_counts.get(cat.id, 0)
        cat.proj_count = project_counts.get(cat.id, 0)

    # 2. Notifications
    unread_qs = Notification.objects.filter(user=user, is_read=False)
    unread_notifications = unread_qs.count()
    recent_notifications = unread_qs.select_related("article", "project")[:5]

    # 3. Scoped Review Queues (Articles & Project Documents)
    pending_review = 0
    pending_doc_reviews = 0
    if user.can_approve():
        pending_review = (
            Article.objects.visible_to(user)
            .filter(status=Article.Status.IN_REVIEW)
            .count()
        )
        pending_doc_reviews = ProjectDocument.objects.filter(
            project__in=visible_projects,
            is_latest=True,
            status=ProjectDocument.Status.IN_REVIEW,
        ).count()
    elif user.can_publish():
        # Engineers see their own items currently waiting in review
        pending_review = Article.objects.filter(
            author=user, status=Article.Status.IN_REVIEW
        ).count()

    # 4. Active Projects accessible to the user
    my_projects_count = visible_projects.exclude(
        status=Project.Status.COMPLETED
    ).count()

    return {
        "nav_categories": nav_categories,
        "unread_notifications": unread_notifications,
        "recent_notifications": recent_notifications,
        "pending_review": pending_review,
        "pending_doc_reviews": pending_doc_reviews,
        "total_pending_reviews": pending_review + pending_doc_reviews,
        "my_projects_count": my_projects_count,
        **base_enums,
    }