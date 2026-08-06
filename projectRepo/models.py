import logging
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# USER
# ─────────────────────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        extra_fields.setdefault("username", email.split("@")[0])
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", self.model.Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN    = "admin",  "Administrator"
        ENGINEER = "engineer", "Engineer"
        VIEWER   = "viewer", "Viewer (Read Only)"

    email = models.EmailField(unique=True, db_index=True)
    azure_object_id = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True)
    azure_tenant_id = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=200, blank=True)
    job_title = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=50,  blank=True)
    avatar_url = models.URLField(max_length=1000, blank=True)
    bio = models.TextField(blank=True, max_length=500)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    login_count = models.PositiveIntegerField(default=0)
    notification_preferences = models.JSONField(default=dict, blank=True)

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        verbose_name  = "User"
        verbose_name_plural = "Users"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    @property
    def full_name(self) -> str:
        name = self.get_full_name().strip()
        return name if name else self.email

    @property
    def initials(self) -> str:
        parts = self.get_full_name().strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        return self.email[0].upper()

    @property
    def is_online(self) -> bool:
        if not self.last_seen:
            return False
        return (timezone.now() - self.last_seen).total_seconds() < 300


    def can_edit_content(self) -> bool:
        return self.role in [self.Role.ADMIN, self.Role.ENGINEER] or self.is_superuser

    def can_publish(self) -> bool:
        return self.role in [self.Role.ADMIN, self.Role.ENGINEER] or self.is_superuser

    def can_manage_users(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    def can_delete_content(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    def record_login(self, ip_address: str = None):
        self.login_count += 1
        self.last_seen = timezone.now()
        if ip_address:
            self.last_login_ip = ip_address
        self.save(update_fields=["login_count", "last_seen", "last_login_ip"])


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY
# ─────────────────────────────────────────────────────────────────────────────

class Category(models.Model):
    class CategoryType(models.TextChoices):
        SUPPORT  = "support", "Support Resolution"
        PROJECT  = "project", "Project Implementation"
        SOFTWARE = "software", "Software Development"
        GENERAL  = "general", "General Knowledge"

    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    category_type = models.CharField(max_length=20, choices=CategoryType.choices, default=CategoryType.GENERAL)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    description = models.TextField(blank=True, max_length=500)
    icon = models.CharField(max_length=60, blank=True)
    color_hex = models.CharField(max_length=7, default="#2563EB")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="created_categories")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return f"{self.parent.name} › {self.name}" if self.parent else self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def clean(self):
        if self.parent and self.pk and self.parent.pk == self.pk:
            from django.core.exceptions import ValidationError
            raise ValidationError("A category cannot be its own parent.")

    def _unique_slug(self) -> str:
        base = slugify(self.name)
        slug, n = base, 1
        while Category.objects.filter(slug=slug).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    def get_absolute_url(self):
        return reverse("category_detail", kwargs={"slug": self.slug})

    @property
    def article_count(self):
        return self.articles.filter(status=Article.Status.PUBLISHED).count()

    @property
    def breadcrumb(self):
        crumbs, node = [], self
        while node:
            crumbs.insert(0, (node.name, node.get_absolute_url()))
            node = node.parent
        return crumbs


# ─────────────────────────────────────────────────────────────────────────────
# TAG
# ─────────────────────────────────────────────────────────────────────────────

class Tag(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    color_hex = models.CharField(max_length=7, default="#6B7280")
    usage_count = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-usage_count", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("tag_articles", kwargs={"slug": self.slug})


# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE
# ─────────────────────────────────────────────────────────────────────────────

class Article(models.Model):
    class ArticleType(models.TextChoices):
        SUPPORT  = "support", "Support Resolution"
        PROJECT  = "project", "Project Implementation"
        SOFTWARE = "software","Software Guide"
        GENERAL  = "general", "General Knowledge"

    class Status(models.TextChoices):
        DRAFT     = "draft", "Draft"
        IN_REVIEW = "in_review", "In Review"
        PUBLISHED = "published", "Published"
        ARCHIVED  = "archived", "Archived"

    class Severity(models.TextChoices):
        CRITICAL = "critical", "Critical"
        HIGH     = "high", "High"
        MEDIUM   = "medium", "Medium"
        LOW      = "low", "Low"
        NA       = "n/a", "Not Applicable"

    class Visibility(models.TextChoices):
        PUBLIC     = "public", "All Staff"
        RESTRICTED = "restricted", "Senior Staff Only"
        PRIVATE    = "private", "Author Only"

    class DifficultyLevel(models.TextChoices):
        BEGINNER     = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED     = "advanced", "Advanced"
        EXPERT       = "expert", "Expert"

    # Core
    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=350, unique=True, blank=True, db_index=True)
    article_type = models.CharField(max_length=20, choices=ArticleType.choices, default=ArticleType.SUPPORT, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="articles")
    tags = models.ManyToManyField(Tag, blank=True, related_name="articles")
    summary = models.TextField(max_length=600, blank=True)
    content = models.TextField()
    search_keywords = models.TextField(blank=True)

    # People
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="authored_articles")
    contributors = models.ManyToManyField(User, blank=True, related_name="contributed_articles")
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_articles")

    # Workflow
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC)
    version = models.PositiveSmallIntegerField(default=1)
    review_notes = models.TextField(blank=True)

    # Support metadata
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.NA)
    affected_systems = models.CharField(max_length=500, blank=True)
    error_codes = models.CharField(max_length=300, blank=True)
    microsoft_products = models.CharField(max_length=400, blank=True)
    resolution_type = models.CharField(max_length=100, blank=True)
    time_to_resolve_minutes = models.PositiveIntegerField(null=True, blank=True)

    # Project metadata
    project_type = models.CharField(max_length=150, blank=True)
    tech_stack = models.CharField(max_length=500, blank=True)
    difficulty_level = models.CharField(max_length=20, choices=DifficultyLevel.choices, blank=True)
    estimated_duration = models.CharField(max_length=100, blank=True)
    prerequisites = models.TextField(blank=True)

    # Metrics
    views_count = models.PositiveIntegerField(default=0, editable=False)
    helpful_votes = models.PositiveIntegerField(default=0, editable=False)
    not_helpful_votes = models.PositiveIntegerField(default=0, editable=False)

    # Flags
    is_featured = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    needs_review = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    related_articles = models.ManyToManyField("self", blank=True, symmetrical=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status", "visibility"]),
            models.Index(fields=["article_type", "status"]),
            models.Index(fields=["is_featured", "status"]),
            models.Index(fields=["-published_at"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def _unique_slug(self) -> str:
        base = slugify(self.title)[:300]
        slug, n = base, 1
        while Article.objects.filter(slug=slug).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    def get_absolute_url(self):
        return reverse("article_detail", kwargs={"slug": self.slug})

    def get_edit_url(self):
        return reverse("article_edit", kwargs={"slug": self.slug})

    @property
    def helpfulness_score(self) -> int:
        total = self.helpful_votes + self.not_helpful_votes
        return round((self.helpful_votes / total) * 100) if total else 0

    @property
    def severity_color(self) -> str:
        return {
            "critical":"red",
            "high":"orange",
            "medium":"yellow",
            "low":"green",
            "n/a":"gray",
        }.get(self.severity, "gray")

    def increment_view(self, user=None, ip_address=""):
        Article.objects.filter(pk=self.pk).update(views_count=models.F("views_count") + 1)
        self.refresh_from_db(fields=["views_count"])


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT STEP
# ─────────────────────────────────────────────────────────────────────────────

class ProjectStep(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="steps", limit_choices_to={"article_type": Article.ArticleType.PROJECT})
    step_number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=300)
    description = models.TextField()
    code_snippet = models.TextField(blank=True)
    code_language = models.CharField(max_length=50, blank=True, default="bash")
    warning = models.TextField(blank=True)
    tip = models.TextField(blank=True)
    estimated_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    is_optional = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["step_number"]
        constraints = [
            models.UniqueConstraint(fields=["article", "step_number"], name="unique_article_step_order")
        ]

    def __str__(self):
        return f"Step {self.step_number}: {self.title}"


# ─────────────────────────────────────────────────────────────────────────────
# ATTACHMENT
# ─────────────────────────────────────────────────────────────────────────────

def article_attachment_path(instance, filename):
    return f"uploads/articles/{instance.article.slug}/{filename}"

class Attachment(models.Model):
    article       = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="attachments")
    file          = models.FileField(upload_to=article_attachment_path, max_length=500)
    original_name = models.CharField(max_length=255)
    file_size_bytes = models.BigIntegerField(help_text="File size in bytes")
    file_type     = models.CharField(max_length=100, blank=True)
    description   = models.CharField(max_length=300, blank=True)
    uploaded_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    uploaded_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_name} → {self.article.title}"

    @property
    def file_size_human(self) -> str:
        size = self.file_size_bytes
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# ─────────────────────────────────────────────────────────────────────────────
# COMMENT 
# ─────────────────────────────────────────────────────────────────────────────

class Comment(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    content = models.TextField(max_length=3000)
    is_approved = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author.email} on '{self.article.title}'"

    @property
    def is_edited(self) -> bool:
        return self.edited_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE FEEDBACK
# ─────────────────────────────────────────────────────────────────────────────

class ArticleFeedback(models.Model):
    article       = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="feedback")
    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name="feedback_given")
    is_helpful    = models.BooleanField()
    feedback_text = models.TextField(blank=True, max_length=1000)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["article", "user"], name="unique_user_article_feedback")
        ]

    def __str__(self):
        return f"{'👍' if self.is_helpful else '👎'} by {self.user.email}"


# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE VIEW
# ─────────────────────────────────────────────────────────────────────────────

class ArticleView(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="views")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField()
    viewed_at  = models.DateTimeField(auto_now_add=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-viewed_at"]


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH LOG
# ─────────────────────────────────────────────────────────────────────────────

class SearchLog(models.Model):
    query = models.CharField(max_length=300, db_index=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    results_count = models.PositiveSmallIntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f'"{self.query}" ({self.results_count} results)'


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION
# ─────────────────────────────────────────────────────────────────────────────

class Notification(models.Model):
    class NotificationType(models.TextChoices):
        ARTICLE_PUBLISHED = "article_published", "Article Published"
        COMMENT           = "comment",           "New Comment"
        REVIEW_REQUEST    = "review_request",    "Review Requested"
        MENTION           = "mention",           "You Were Mentioned"
        ARTICLE_UPDATED   = "article_updated",   "Article Updated"
        SYSTEM            = "system",            "System"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices)
    title = models.CharField(max_length=200)
    message = models.TextField(max_length=500)
    article = models.ForeignKey(Article, null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications")
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_type} → {self.user.email}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])