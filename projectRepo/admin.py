from django.contrib import admin
from django.utils.html import format_html
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Category, Tag, Article, ProjectStep, 
    Attachment, Comment, ArticleFeedback, ArticleView, SearchLog, Notification
)

# =============================================================================
# INLINES
# =============================================================================

class ProjectStepInline(admin.TabularInline):
    """Allows engineers to modify sequential steps directly inside the project view."""
    model = ProjectStep
    extra = 1
    sortable_field_name = "step_number"
    fields = ("step_number", "title", "estimated_minutes", "is_optional")


class AttachmentInline(admin.TabularInline):
    """Allows swift document attachments within the central Article record."""
    model = Attachment
    extra = 1
    fields = ("file", "original_name", "file_type", "description")


# =============================================================================
# MODEL ADMINS
# =============================================================================

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom administration panel for your corporate Entra identity blueprint.
    Organizes profile synchronizations and access privileges.
    """
    list_display = ("email", "first_name", "last_name", "role", "department", "is_staff", "last_seen", "is_online_status")
    list_filter = ("role", "is_staff", "is_superuser", "is_active", "department")
    search_fields = ("email", "first_name", "last_name", "job_title", "azure_object_id")
    ordering = ("first_name", "last_name")
    
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "email", "avatar_url", "bio")}),
        ("MSP Corporate Structure", {"fields": ("role", "department", "job_title", "phone")}),
        ("Microsoft Entra ID Synchronization", {"fields": ("azure_object_id", "azure_tenant_id")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Telemetry & Preferences", {"fields": ("last_seen", "last_login_ip", "login_count", "notification_preferences")}),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )

    readonly_fields = ("login_count", "last_seen", "last_login_ip", "azure_object_id", "azure_tenant_id")

    @admin.display(description="Status", boolean=False)
    def is_online_status(self, obj):
        if obj.is_online:
            return format_html('<span style="color: #10B981; font-weight: bold;">● Online</span>')
        return format_html('<span style="color: #94A3B8;">○ Offline</span>')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Manages multi-tier support, software, and project taxonomy pathways."""
    list_display = ("name", "category_type", "parent", "sort_order", "is_active", "color_badge")
    list_filter = ("category_type", "is_active", "parent")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")

    @admin.display(description="Color")
    def color_badge(self, obj):
        return format_html(
            '<span style="background-color: {}; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            obj.color_hex, obj.color_hex
        )


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """Tracks label metrics and keyword taxonomy across articles."""
    list_display = ("name", "slug", "usage_count", "color_preview")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("usage_count",)

    @admin.display(description="Color Preview")
    def color_preview(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; border-radius: 50%; background-color: {}; border: 1px solid #cbd5e1;"></div>',
            obj.color_hex
        )


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """
    The control room for your technical knowledge asset infrastructure.
    Combines fields for Support, Projects, and Software environments.
    """
    list_display = ("title", "article_type", "category", "status", "visibility", "author", "views_count", "is_verified")
    list_filter = ("article_type", "status", "visibility", "category", "is_verified", "is_featured", "is_pinned")
    search_fields = ("title", "content", "summary", "error_codes", "microsoft_products", "affected_systems", "search_keywords")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("views_count", "helpful_votes", "not_helpful_votes", "version")
    filter_horizontal = ("tags", "contributors", "related_articles")
    inlines = [ProjectStepInline, AttachmentInline]

    fieldsets = (
        ("Core Metadata", {
            "fields": ("title", "slug", "article_type", "category", "tags", "summary", "content", "search_keywords")
        }),
        ("Governance & Workflow State", {
            "fields": ("status", "visibility", "author", "contributors", "reviewed_by", "review_notes", "version")
        }),
        ("Support Resolution Telemetry", {
            "fields": ("severity", "affected_systems", "error_codes", "microsoft_products", "resolution_type", "time_to_resolve_minutes"),
            "classes": ("collapse",),
            "description": "Populate these fields if documenting service desk fixes."
        }),
        ("Project Implementation Playbooks", {
            "fields": ("project_type", "tech_stack", "difficulty_level", "estimated_duration", "prerequisites"),
            "classes": ("collapse",),
            "description": "Populate these fields for long-term customer setups."
        }),
        ("Metrics & Curations", {
            "fields": ("views_count", "helpful_votes", "not_helpful_votes", "is_featured", "is_pinned", "needs_review", "is_verified")
        }),
        ("System Timestamps", {
            "fields": ("published_at", "last_reviewed_at"),
            "classes": ("collapse",)
        }),
    )

    def save_model(self, request, obj, form, change):
        """Enforce session identity mappings as default author configurations."""
        if not obj.pk:
            obj.author = request.user
        super().save_model(request, obj, form, change)


# =============================================================================
# TELEMETRY, INTERACTION & LOGGING SYSTEMS
# =============================================================================

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("author", "article", "parent", "is_approved", "is_pinned", "created_at")
    list_filter = ("is_approved", "is_pinned", "created_at")
    search_fields = ("content", "author__email", "article__title")


@admin.register(ArticleFeedback)
class ArticleFeedbackAdmin(admin.ModelAdmin):
    list_display = ("article", "user", "is_helpful", "created_at")
    list_filter = ("is_helpful", "created_at")
    search_fields = ("feedback_text", "user__email", "article__title")


@admin.register(ArticleView)
class ArticleViewAdmin(admin.ModelAdmin):
    list_display = ("article", "user", "ip_address", "viewed_at")
    list_filter = ("viewed_at",)
    search_fields = ("ip_address", "user__email", "article__title")
    readonly_fields = ("article", "user", "ip_address", "viewed_at")


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    """Crucial for discovering knowledge base gaps by auditing user queries."""
    list_display = ("query", "user", "results_count", "ip_address", "created_at")
    list_filter = ("created_at", "results_count")
    search_fields = ("query", "user__email")
    readonly_fields = ("query", "user", "results_count", "ip_address", "created_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "notification_type", "title", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("title", "message", "user__email")