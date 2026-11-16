from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import (
    Article,
    ArticleFeedback,
    ArticleRevision,
    ArticleView,
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
    ResolutionStep,
    SearchLog,
    Tag,
    Team,
    User,
)


# =============================================================================
# INLINES
# =============================================================================

class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 1
    autocomplete_fields = ("user", "added_by")
    fields = ("user", "role", "can_upload_docs", "can_approve_docs")


class ProjectDocumentInline(admin.TabularInline):
    model = ProjectDocument
    extra = 0
    readonly_fields = (
        "version",
        "is_latest",
        "file_size_bytes",
        "sha256_checksum",
        "uploaded_by",
        "created_at",
    )
    fields = (
        "document_type",
        "phase",
        "title",
        "version",
        "is_latest",
        "status",
        "file",
        "uploaded_by",
    )


class ProjectActivityInline(admin.TabularInline):
    model = ProjectActivity
    extra = 1
    fields = (
        "step_number",
        "phase",
        "title",
        "status",
        "assigned_to",
        "estimated_minutes",
        "is_optional",
    )


class ResolutionStepInline(admin.TabularInline):
    model = ResolutionStep
    extra = 1
    fields = ("step_number", "title", "estimated_minutes", "is_optional")


class ArticleRevisionInline(admin.TabularInline):
    model = ArticleRevision
    extra = 0
    can_delete = False
    readonly_fields = ("version", "title", "change_summary", "edited_by", "created_at")
    fields = ("version", "title", "change_summary", "edited_by", "created_at")


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ("attachment_kind", "file", "original_name", "description", "uploaded_by")
    readonly_fields = ("uploaded_by",)


# =============================================================================
# IDENTITY & ACCESS CONTROL ADMINS
# =============================================================================

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "first_name",
        "last_name",
        "role",
        "department",
        "is_staff",
        "is_active",
        "last_seen",
        "is_online_status",
    )
    list_filter = ("role", "is_staff", "is_superuser", "is_active", "department")
    search_fields = ("email", "first_name", "last_name", "job_title", "azure_object_id")
    ordering = ("first_name", "last_name", "email")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "email", "avatar_url", "bio")}),
        ("Corporate Structure & Role", {"fields": ("role", "department", "job_title", "phone")}),
        ("Microsoft Entra ID Sync", {"fields": ("azure_object_id", "azure_tenant_id")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Telemetry & Preferences", {"fields": ("last_seen", "last_login_ip", "login_count", "notification_preferences")}),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )

    readonly_fields = ("login_count", "last_seen", "last_login_ip", "azure_object_id", "azure_tenant_id")

    @admin.display(description="Status")
    def is_online_status(self, obj):
        if obj.is_online:
            return format_html('<span style="color: #10B981; font-weight: bold;">● Online</span>')
        return format_html('<span style="color: #94A3B8;">○ Offline</span>')


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "lead", "member_count", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("members",)

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj.members.count()


# =============================================================================
# TAXONOMY ADMINS
# =============================================================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category_type", "parent", "sort_order", "is_active", "color_badge")
    list_filter = ("category_type", "is_active", "parent")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("allowed_teams",)
    ordering = ("sort_order", "name")

    @admin.display(description="Color")
    def color_badge(self, obj):
        return format_html(
            '<span style="background-color: {}; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            obj.color_hex,
            obj.color_hex,
        )


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "usage_count", "color_preview")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("usage_count",)

    @admin.display(description="Color")
    def color_preview(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; border-radius: 50%; background-color: {}; border: 1px solid #cbd5e1;"></div>',
            obj.color_hex,
        )


# =============================================================================
# PROJECT & DELIVERABLES ADMINS
# =============================================================================

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "project_code",
        "title",
        "client_or_unit",
        "status",
        "priority",
        "visibility",
        "project_lead",
        "compliance_badge",
        "updated_at",
    )
    list_filter = ("status", "priority", "visibility", "category")
    search_fields = ("project_code", "title", "client_or_unit", "microsoft_products", "tech_stack")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("tags", "allowed_teams")
    readonly_fields = ("project_code", "created_at", "updated_at", "completed_at")
    inlines = [ProjectMemberInline, ProjectDocumentInline, ProjectActivityInline]

    fieldsets = (
        ("Project Identity", {
            "fields": ("project_code", "title", "slug", "client_or_unit", "category", "tags")
        }),
        ("Technical Scope", {
            "fields": ("summary", "scope_notes", "microsoft_products", "tech_stack", "prerequisites")
        }),
        ("Lifecycle & Timeline", {
            "fields": ("status", "priority", "start_date", "target_end_date", "completed_at")
        }),
        ("Governance & Access Control", {
            "fields": ("project_lead", "created_by", "visibility", "allowed_teams", "allow_open_collaboration")
        }),
        ("System Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Docs Compliance")
    def compliance_badge(self, obj):
        pct = obj.document_compliance_percent
        color = "#10B981" if pct == 100 else ("#F59E0B" if pct >= 50 else "#EF4444")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}%</span>',
            color,
            pct,
        )

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "document_type",
        "phase",
        "title",
        "version",
        "is_latest",
        "status",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("document_type", "phase", "status", "is_latest")
    search_fields = ("title", "original_name", "project__title", "project__project_code")
    readonly_fields = ("version", "file_size_bytes", "sha256_checksum", "created_at", "updated_at")


@admin.register(ProjectActivity)
class ProjectActivityAdmin(admin.ModelAdmin):
    list_display = ("project", "step_number", "phase", "title", "status", "assigned_to", "due_date")
    list_filter = ("phase", "status", "is_optional")
    search_fields = ("title", "description", "project__title", "project__project_code")


# =============================================================================
# KNOWLEDGE BASE & SUPPORT RESOLUTION ADMINS
# =============================================================================

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "article_type",
        "category",
        "related_project",
        "status",
        "visibility",
        "author",
        "views_count",
        "is_verified",
    )
    list_filter = ("article_type", "status", "visibility", "severity", "category", "is_verified", "is_featured", "is_pinned")
    search_fields = (
        "title",
        "summary",
        "content",
        "symptoms",
        "root_cause",
        "error_codes",
        "microsoft_products",
        "affected_systems",
        "search_keywords",
    )
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("views_count", "helpful_votes", "not_helpful_votes", "version")
    filter_horizontal = ("tags", "contributors", "allowed_teams", "allowed_users", "related_articles")
    inlines = [ResolutionStepInline, AttachmentInline, ArticleRevisionInline]

    fieldsets = (
        ("Core Metadata", {
            "fields": ("title", "slug", "article_type", "category", "related_project", "tags", "summary", "content", "search_keywords")
        }),
        ("Support Resolution Details", {
            "fields": (
                "severity",
                "symptoms",
                "root_cause",
                "verification_steps",
                "affected_systems",
                "error_codes",
                "microsoft_products",
                "resolution_type",
                "time_to_resolve_minutes",
            ),
        }),
        ("Runbook & Guide Metadata", {
            "fields": ("tech_stack", "difficulty_level", "estimated_duration", "prerequisites"),
            "classes": ("collapse",),
        }),
        ("Governance, Workflow & Access", {
            "fields": (
                "status",
                "visibility",
                "allowed_teams",
                "allowed_users",
                "allow_engineer_collaboration",
                "author",
                "contributors",
                "reviewed_by",
                "review_notes",
                "version",
            )
        }),
        ("Metrics & Curation", {
            "fields": ("views_count", "helpful_votes", "not_helpful_votes", "is_featured", "is_pinned", "needs_review", "is_verified")
        }),
        ("System Timestamps", {
            "fields": ("published_at", "last_reviewed_at"),
            "classes": ("collapse",),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)


# =============================================================================
# COLLABORATION, TELEMETRY & AUDIT ADMINS
# =============================================================================

@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "attachment_kind", "file_size_human", "article", "project", "activity", "uploaded_by", "uploaded_at")
    list_filter = ("attachment_kind", "uploaded_at")
    search_fields = ("original_name", "description", "uploaded_by__email")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("author", "article", "project", "activity", "is_resolution_note", "is_approved", "is_pinned", "created_at")
    list_filter = ("is_approved", "is_pinned", "is_resolution_note", "created_at")
    search_fields = ("content", "author__email", "article__title", "project__title")


@admin.register(ArticleFeedback)
class ArticleFeedbackAdmin(admin.ModelAdmin):
    list_display = ("article", "user", "is_helpful", "created_at")
    list_filter = ("is_helpful", "created_at")
    search_fields = ("feedback_text", "user__email", "article__title")


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ("user", "article", "project", "created_at")
    search_fields = ("user__email", "article__title", "project__title")


@admin.register(ArticleView)
class ArticleViewAdmin(admin.ModelAdmin):
    list_display = ("article", "user", "ip_address", "viewed_at")
    list_filter = ("viewed_at",)
    search_fields = ("ip_address", "user__email", "article__title")
    readonly_fields = ("article", "user", "ip_address", "user_agent", "viewed_at")


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    list_display = ("query", "user", "results_count", "ip_address", "created_at")
    list_filter = ("created_at", "results_count")
    search_fields = ("query", "user__email")
    readonly_fields = ("query", "user", "results_count", "ip_address", "created_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "notification_type", "title", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("title", "message", "user__email")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target_type", "target_repr", "ip_address")
    list_filter = ("action", "target_type", "created_at")
    search_fields = ("actor__email", "target_repr", "target_id", "ip_address")
    readonly_fields = (
        "actor",
        "action",
        "target_type",
        "target_id",
        "target_repr",
        "details",
        "ip_address",
        "user_agent",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False