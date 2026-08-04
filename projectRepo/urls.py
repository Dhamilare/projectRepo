from django.urls import path
from . import views

urlpatterns = [
    # ====================== AUTHENTICATION (MICROSOFT ENTRA ID) ======================
    path("auth/login/", views.login_view, name="login"),
    path("auth/microsoft/", views.microsoft_login, name="microsoft_login"),
    path("auth/callback/", views.oauth_callback, name="callback"),
    path("auth/logout/", views.logout_view, name="logout"),
    path("auth/profile/", views.profile_view, name="profile"),

    # ====================== CORE OPERATIONS WORKSPACE ======================
    path("", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard, name="dashboard"), 

    # ====================== ARTICLES (SUPPORT & PROJECTS) ======================
    path("articles/", views.article_list, name="article_list"),
    path("articles/new/", views.article_create, name="article_create"),
    path("articles/<slug:slug>/", views.article_detail, name="article_detail"),
    path("articles/<slug:slug>/edit/", views.article_edit, name="article_edit"),
    path("articles/<slug:slug>/delete/", views.article_delete, name="article_delete"),
    path("attachments/<int:pk>/delete/", views.delete_attachment, name="delete_attachment"),

    # ====================== ENGAGEMENT, TELEMETRY & FEEDBACK ======================
    path("articles/<slug:slug>/comment/", views.add_comment, name="add_comment"),
    path("articles/<slug:slug>/feedback/", views.article_feedback, name="article_feedback"),

    # ====================== SEARCH ENGINE AND DATA ENDPOINTS ======================
    path("search/", views.search_view, name="search"),
    path("api/search-suggestions/", views.search_suggestions, name="search_suggestions"),

    # ====================== TAXONOMIES & NOTIFICATIONS ======================
    path("categories/", views.manage_categories, name="manage_categories"),
    path("categories/<slug:slug>/", views.category_detail, name="category_detail"),
    path("tags/<slug:slug>/", views.tag_articles, name="tag_articles"),
    path("notifications/", views.notifications_view, name="notifications"),

    path("management/access-control/", views.access_control_matrix, name="access_control_matrix"),
]