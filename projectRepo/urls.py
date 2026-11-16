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

    # ====================== PROJECTS, DELIVERABLES & CHECKLISTS ======================
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<slug:slug>/", views.project_detail, name="project_detail"),
    path("projects/<slug:slug>/edit/", views.project_edit, name="project_edit"),
    path("projects/<slug:slug>/delete/", views.project_delete, name="project_delete"),
    path("projects/<slug:slug>/bookmark/", views.toggle_project_bookmark, name="toggle_project_bookmark"),

    # Mandatory & Supporting Project Documents (SOW, Requirements, As-Built, Admin Guide)
    path("projects/<slug:slug>/documents/upload/", views.project_document_upload, name="project_document_upload"),
    path("projects/<slug:slug>/documents/<int:doc_id>/review/", views.project_document_review, name="project_document_review"),
    path("projects/<slug:slug>/documents/<int:doc_id>/download/", views.project_document_download, name="project_document_download"),

    # Project Activities (Steps / Action Plan / Checklist)
    path("projects/<slug:slug>/activities/new/", views.project_activity_create, name="project_activity_create"),
    path("projects/<slug:slug>/activities/<int:activity_id>/edit/", views.project_activity_edit, name="project_activity_edit"),
    path("projects/<slug:slug>/activities/<int:activity_id>/toggle/", views.project_activity_toggle, name="project_activity_toggle"),
    path("projects/<slug:slug>/activities/<int:activity_id>/delete/", views.project_activity_delete, name="project_activity_delete"),

    # Scoped Project Members & Project Collaboration
    path("projects/<slug:slug>/members/", views.project_member_manage, name="project_member_manage"),
    path("projects/<slug:slug>/members/<int:member_id>/remove/", views.project_member_remove, name="project_member_remove"),
    path("projects/<slug:slug>/comment/", views.add_project_comment, name="add_project_comment"),

    # ====================== SUPPORT RESOLUTIONS & KNOWLEDGE BASE ======================
    path("articles/", views.article_list, name="article_list"),
    path("articles/new/", views.article_create, name="article_create"),
    path("articles/<slug:slug>/", views.article_detail, name="article_detail"),
    path("articles/<slug:slug>/edit/", views.article_edit, name="article_edit"),
    path("articles/<slug:slug>/delete/", views.article_delete, name="article_delete"),
    path("articles/<slug:slug>/revisions/", views.article_revisions, name="article_revisions"),
    path("articles/<slug:slug>/comment/", views.add_comment, name="add_comment"),
    path("articles/<slug:slug>/feedback/", views.article_feedback, name="article_feedback"),
    path("articles/<slug:slug>/bookmark/", views.toggle_article_bookmark, name="toggle_article_bookmark"),

    # ====================== PROTECTED ATTACHMENTS ======================
    path("attachments/<int:pk>/download/", views.download_attachment, name="download_attachment"),
    path("attachments/<int:pk>/delete/", views.delete_attachment, name="delete_attachment"),

    # ====================== SEARCH ENGINE & API ======================
    path("search/", views.search_view, name="search"),
    path("api/search-suggestions/", views.search_suggestions, name="search_suggestions"),

    # ====================== BOOKMARKS, TAXONOMIES & NOTIFICATIONS ======================
    path("bookmarks/", views.bookmark_list, name="bookmark_list"),
    path("categories/", views.manage_categories, name="manage_categories"),
    path("categories/<slug:slug>/", views.category_detail, name="category_detail"),
    path("tags/<slug:slug>/", views.tag_articles, name="tag_articles"),
    path("notifications/", views.notifications_view, name="notifications"),

    # ====================== ENTERPRISE GOVERNANCE (ADMIN ONLY) ======================
    path("management/access-control/", views.access_control_matrix, name="access_control_matrix"),
    path("management/teams/", views.manage_teams, name="manage_teams"),
    path("management/audit-logs/", views.audit_log_list, name="audit_log_list"),
]