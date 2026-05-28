from django.db.models import Count, Q
from .models import Category, Notification, Article


def global_context(request):
    """
    Injects site-wide context into every template safely,
    ensuring unauthenticated routes do not trigger property faults.
    """
    if not request.user.is_authenticated:
        return {
            "nav_categories": Category.objects.none(),
            "unread_notifications": 0,
            "pending_review": 0,
            "ARTICLE_TYPES": Article.ArticleType,
        }

    nav_categories = (
        Category.objects
        .filter(is_active=True, parent=None)
        .annotate(
            pub_count=Count(
                "articles",
                filter=Q(articles__status=Article.Status.PUBLISHED)
            )
        )
        .order_by("sort_order", "name")
    )

    unread_notifications = (
        Notification.objects
        .filter(user=request.user, is_read=False)
        .count()
    )
    pending_review = 0
    if request.user.can_publish():
        pending_review = Article.objects.filter(
            status=Article.Status.IN_REVIEW
        ).count()

    return {
        "nav_categories": nav_categories,
        "unread_notifications": unread_notifications,
        "pending_review": pending_review,
        "ARTICLE_TYPES": Article.ArticleType,
    }