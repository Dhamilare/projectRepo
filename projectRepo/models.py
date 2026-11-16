import hashlib
import logging
import os
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# USER & TEAM
# ─────────────────────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        base_username = extra_fields.pop("username", None) or email.split("@")[0]
        extra_fields["username"] = self._unique_username(base_username)
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

    def _unique_username(self, base: str) -> str:
        clean = base[:130]
        candidate, n = clean, 1
        while self.model.objects.filter(username=candidate).exists():
            candidate = f"{clean[:140]}-{n}"
            n += 1
        return candidate


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN    = "admin",    "Administrator"
        LEAD     = "lead",     "Lead / Senior Engineer"
        ENGINEER = "engineer", "Engineer"
        VIEWER   = "viewer",   "Viewer (Read Only)"

    email = models.EmailField(unique=True, db_index=True)
    azure_object_id = models.CharField(
        max_length=255, unique=True, null=True, blank=True, db_index=True
    )
    azure_tenant_id = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=200, blank=True)
    job_title = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    avatar_url = models.URLField(max_length=1000, blank=True)
    bio = models.TextField(blank=True, max_length=500)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER, db_index=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    login_count = models.PositiveIntegerField(default=0)
    notification_preferences = models.JSONField(default=dict, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["first_name", "last_name", "email"]

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

    # Role helpers
    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_lead(self) -> bool:
        return self.role == self.Role.LEAD or self.is_admin

    @property
    def is_engineer(self) -> bool:
        return self.role in (self.Role.ENGINEER, self.Role.LEAD, self.Role.ADMIN) or self.is_superuser

    def can_edit_content(self) -> bool:
        return self.is_engineer

    def can_publish(self) -> bool:
        return self.is_engineer

    def can_approve(self) -> bool:
        return self.is_lead

    def can_manage_users(self) -> bool:
        return self.is_admin

    def can_delete_content(self) -> bool:
        return self.is_admin

    def record_login(self, ip_address: str = None):
        self.login_count += 1
        self.last_seen = timezone.now()
        update_fields = ["login_count", "last_seen"]
        if ip_address:
            self.last_login_ip = ip_address
            update_fields.append("last_login_ip")
        self.save(update_fields=update_fields)


class Team(models.Model):
    """
    Engineering / Business Units used for scoping access to projects,
    documents, and support articles.
    """
    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField(max_length=500, blank=True)
    lead = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="led_teams"
    )
    members = models.ManyToManyField(User, blank=True, related_name="teams")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:160] or "team"
            slug, n = base, 1
            while Team.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY & TAG
# ─────────────────────────────────────────────────────────────────────────────

class Category(models.Model):
    class CategoryType(models.TextChoices):
        SUPPORT  = "support",  "Support Resolution"
        PROJECT  = "project",  "Project Implementation"
        SOFTWARE = "software", "Software & Automation"
        GENERAL  = "general",  "General Knowledge"

    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    category_type = models.CharField(
        max_length=20, choices=CategoryType.choices, default=CategoryType.GENERAL
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    description = models.TextField(blank=True, max_length=500)
    icon = models.CharField(max_length=60, blank=True)
    color_hex = models.CharField(max_length=7, default="#2563EB")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    allowed_teams = models.ManyToManyField(Team, blank=True, related_name="categories")
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="created_categories"
    )
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
            raise ValidationError("A category cannot be its own parent.")

    def _unique_slug(self) -> str:
        base = slugify(self.name)[:160] or "category"
        slug, n = base, 1
        while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    def get_absolute_url(self):
        return reverse("category_detail", kwargs={"slug": self.slug})

    @property
    def article_count(self):
        return self.articles.filter(status=Article.Status.PUBLISHED).count()

    @property
    def project_count(self):
        return self.projects.exclude(status=Project.Status.ARCHIVED).count()

    @property
    def breadcrumb(self):
        crumbs, node = [], self
        while node:
            crumbs.insert(0, (node.name, node.get_absolute_url()))
            node = node.parent
        return crumbs


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
            base = slugify(self.name)[:85] or "tag"
            slug, n = base, 1
            while Tag.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("tag_articles", kwargs={"slug": self.slug})


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT (ENTERPRISE DELIVERABLES, ACTION PLANS & SCOPED ACCESS)
# ─────────────────────────────────────────────────────────────────────────────

class ProjectQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not user or not user.is_authenticated:
            return self.none()
        if user.is_admin:
            return self.all()
        return self.filter(
            Q(visibility=Project.Visibility.PUBLIC)
            | Q(visibility=Project.Visibility.TEAM, allowed_teams__members=user)
            | Q(project_lead=user)
            | Q(created_by=user)
            | Q(memberships__user=user)
        ).distinct()


class Project(models.Model):
    class Status(models.TextChoices):
        PRE_IMPLEMENTATION = "pre_implementation", "Pre-Implementation (SOW & Requirements)"
        IN_PROGRESS        = "in_progress",        "In Progress (Implementation)"
        POST_IMPLEMENTATION= "post_implementation","Post-Implementation (Docs & Handover)"
        COMPLETED          = "completed",          "Completed"
        ON_HOLD            = "on_hold",            "On Hold"
        ARCHIVED           = "archived",           "Archived"

    class Visibility(models.TextChoices):
        PUBLIC     = "public",     "All Staff (Organization-Wide)"
        TEAM       = "team",       "Assigned Teams Only"
        RESTRICTED = "restricted", "Assigned Project Members Only"
        PRIVATE    = "private",    "Project Lead & Admins Only"

    class Priority(models.TextChoices):
        CRITICAL = "critical", "Critical"
        HIGH     = "high",     "High"
        MEDIUM   = "medium",   "Medium"
        LOW      = "low",      "Low"

    # Identification
    project_code = models.CharField(max_length=30, unique=True, blank=True, db_index=True)
    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=350, unique=True, blank=True, db_index=True)
    client_or_unit = models.CharField(
        max_length=200, blank=True, help_text="Client name, department, or business unit"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="projects"
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="projects")

    # Overview & Technical Scope
    summary = models.TextField(max_length=800, blank=True)
    scope_notes = models.TextField(blank=True, help_text="High-level in-scope / out-of-scope summary")
    tech_stack = models.CharField(max_length=500, blank=True)
    microsoft_products = models.CharField(
        max_length=400, blank=True, help_text="e.g., Windows Autopilot, Intune, Entra ID"
    )
    prerequisites = models.TextField(blank=True)

    # Lifecycle & Timeline
    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.PRE_IMPLEMENTATION, db_index=True
    )
    priority = models.CharField(
        max_length=15, choices=Priority.choices, default=Priority.MEDIUM
    )
    start_date = models.DateField(null=True, blank=True)
    target_end_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # People & Access Control
    project_lead = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="led_projects"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_projects"
    )
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC, db_index=True
    )
    allowed_teams = models.ManyToManyField(Team, blank=True, related_name="projects")
    allow_open_collaboration = models.BooleanField(
        default=True,
        help_text="If enabled on Public/Team projects, any engineer with view access can collaborate on checklists & uploads.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status", "visibility"]),
            models.Index(fields=["project_code"]),
        ]

    def __str__(self):
        return f"[{self.project_code}] {self.title}" if self.project_code else self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        if not self.project_code:
            self.project_code = self._generate_project_code()
        if self.status == self.Status.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)

    def _unique_slug(self) -> str:
        base = slugify(self.title)[:300] or "project"
        slug, n = base, 1
        while Project.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    def _generate_project_code(self) -> str:
        year = timezone.now().year
        prefix = f"PRJ-{year}-"
        last = (
            Project.objects.filter(project_code__startswith=prefix)
            .order_by("-project_code")
            .values_list("project_code", flat=True)
            .first()
        )
        seq = 1
        if last:
            try:
                seq = int(last.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = Project.objects.filter(project_code__startswith=prefix).count() + 1
        code = f"{prefix}{seq:03d}"
        while Project.objects.filter(project_code=code).exists():
            seq += 1
            code = f"{prefix}{seq:03d}"
        return code

    def get_absolute_url(self):
        return reverse("project_detail", kwargs={"slug": self.slug})

    # ── Document Compliance Helpers ──────────────────────────────────────────

    def get_latest_document(self, doc_type: str):
        return (
            self.documents.filter(document_type=doc_type, is_latest=True)
            .order_by("-version")
            .first()
        )

    def _has_document(self, doc_type: str) -> bool:
        return self.documents.filter(document_type=doc_type, is_latest=True).exists()

    @property
    def has_sow(self) -> bool:
        return self._has_document(ProjectDocument.DocumentType.SOW)

    @property
    def has_requirements(self) -> bool:
        return self._has_document(ProjectDocument.DocumentType.REQUIREMENTS)

    @property
    def has_as_built(self) -> bool:
        return self._has_document(ProjectDocument.DocumentType.AS_BUILT)

    @property
    def has_admin_guide(self) -> bool:
        return self._has_document(ProjectDocument.DocumentType.ADMIN_GUIDE)

    @property
    def pre_implementation_docs_ready(self) -> bool:
        return self.has_sow and self.has_requirements

    @property
    def post_implementation_docs_ready(self) -> bool:
        return self.has_as_built and self.has_admin_guide

    @property
    def missing_required_documents(self) -> list:
        required = [
            (ProjectDocument.DocumentType.SOW, "Statement of Work (SOW)", self.has_sow),
            (ProjectDocument.DocumentType.REQUIREMENTS, "Requirements Document", self.has_requirements),
            (ProjectDocument.DocumentType.AS_BUILT, "As-Built Document", self.has_as_built),
            (ProjectDocument.DocumentType.ADMIN_GUIDE, "Admin Guide", self.has_admin_guide),
        ]
        return [{"type": code, "label": label} for code, label, exists in required if not exists]

    @property
    def document_compliance_percent(self) -> int:
        completed = sum([
            self.has_sow,
            self.has_requirements,
            self.has_as_built,
            self.has_admin_guide,
        ])
        return round((completed / 4) * 100)

    @property
    def checklist_progress_percent(self) -> int:
        total = self.activities.exclude(status=ProjectActivity.Status.SKIPPED).count()
        if not total:
            return 0
        done = self.activities.filter(status=ProjectActivity.Status.COMPLETED).count()
        return round((done / total) * 100)

    # ── Scoped Permission Checks ─────────────────────────────────────────────

    def get_membership(self, user):
        if not user or not user.is_authenticated:
            return None
        return self.memberships.filter(user=user).first()

    def can_view(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_admin:
            return True
        if self.project_lead_id == user.id or self.created_by_id == user.id:
            return True
        if self.memberships.filter(user=user).exists():
            return True
        if self.visibility == self.Visibility.PUBLIC:
            return True
        if self.visibility == self.Visibility.TEAM:
            return self.allowed_teams.filter(members=user).exists()
        return False

    def can_edit(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_admin:
            return True
        if user.role == User.Role.VIEWER:
            return False
        if self.project_lead_id == user.id or self.created_by_id == user.id:
            return True
        membership = self.get_membership(user)
        if membership and membership.role in (ProjectMember.Role.LEAD, ProjectMember.Role.EDITOR):
            return True
        if self.allow_open_collaboration and self.can_view(user) and user.is_engineer:
            return True
        return False

    def can_upload_documents(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_admin:
            return True
        if user.role == User.Role.VIEWER:
            return False
        membership = self.get_membership(user)
        if membership and (membership.can_upload_docs or membership.role in (ProjectMember.Role.LEAD, ProjectMember.Role.EDITOR)):
            return True
        return self.can_edit(user)

    def can_approve_documents(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_admin:
            return True
        if self.project_lead_id == user.id:
            return True
        membership = self.get_membership(user)
        if membership and (membership.can_approve_docs or membership.role in (ProjectMember.Role.LEAD, ProjectMember.Role.REVIEWER)):
            return True
        return False

    def can_manage_members(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_admin or self.project_lead_id == user.id:
            return True
        membership = self.get_membership(user)
        return bool(membership and membership.role == ProjectMember.Role.LEAD)

    def can_delete(self, user) -> bool:
        return bool(user and user.is_authenticated and user.is_admin)


class ProjectMember(models.Model):
    class Role(models.TextChoices):
        LEAD     = "lead",     "Project Lead"
        EDITOR   = "editor",   "Collaborator (Read/Write)"
        REVIEWER = "reviewer", "Reviewer / Approver"
        VIEWER   = "viewer",   "Observer (Read Only)"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EDITOR)
    can_upload_docs = models.BooleanField(default=True)
    can_approve_docs = models.BooleanField(default=False)
    added_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_project_members"
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="unique_project_member")
        ]
        ordering = ["role", "user__first_name"]

    def __str__(self):
        return f"{self.user.full_name} → {self.project.project_code} ({self.get_role_display()})"


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT DOCUMENTS (SOW, REQUIREMENTS, AS-BUILT, ADMIN GUIDE)
# ─────────────────────────────────────────────────────────────────────────────

def project_document_path(instance, filename):
    clean_name = os.path.basename(filename)
    code = instance.project.project_code or instance.project.slug
    return f"uploads/projects/{code}/documents/{instance.document_type}/v{instance.version}_{clean_name}"


class ProjectDocument(models.Model):
    class DocumentType(models.TextChoices):
        SOW          = "sow",          "Statement of Work (SOW)"
        REQUIREMENTS = "requirements", "Requirements Document"
        AS_BUILT     = "as_built",     "As-Built Document"
        ADMIN_GUIDE  = "admin_guide",  "Admin Guide"
        SUPPORTING   = "supporting",   "Supporting Document"

    class DocumentPhase(models.TextChoices):
        PRE_IMPLEMENTATION  = "pre_implementation",  "Pre-Implementation"
        POST_IMPLEMENTATION = "post_implementation", "Post-Implementation"
        GENERAL             = "general",             "General / Supporting"

    class Status(models.TextChoices):
        DRAFT      = "draft",      "Draft"
        IN_REVIEW  = "in_review",  "In Review"
        APPROVED   = "approved",   "Approved"
        SUPERSEDED = "superseded", "Superseded"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=20, choices=DocumentType.choices, db_index=True)
    phase = models.CharField(
        max_length=25, choices=DocumentPhase.choices, default=DocumentPhase.GENERAL, db_index=True
    )
    title = models.CharField(max_length=300)
    version = models.PositiveSmallIntegerField(default=1)
    is_latest = models.BooleanField(default=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)

    file = models.FileField(upload_to=project_document_path, max_length=500)
    original_name = models.CharField(max_length=255)
    file_size_bytes = models.BigIntegerField(default=0)
    mime_type = models.CharField(max_length=120, blank=True)
    sha256_checksum = models.CharField(max_length=64, blank=True, editable=False)

    change_notes = models.TextField(blank=True, help_text="Summary of what changed in this version")
    review_notes = models.TextField(blank=True)

    uploaded_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="uploaded_project_documents"
    )
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_project_documents"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document_type", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "document_type", "version"],
                name="unique_project_document_version",
            )
        ]
        indexes = [
            models.Index(fields=["project", "document_type", "is_latest"]),
            models.Index(fields=["status", "is_latest"]),
        ]

    def __str__(self):
        return f"{self.project.project_code} | {self.get_document_type_display()} v{self.version}"

    def save(self, *args, **kwargs):
        # Enforce lifecycle phase mapping for the 4 core project documents
        if self.document_type in (self.DocumentType.SOW, self.DocumentType.REQUIREMENTS):
            self.phase = self.DocumentPhase.PRE_IMPLEMENTATION
        elif self.document_type in (self.DocumentType.AS_BUILT, self.DocumentType.ADMIN_GUIDE):
            self.phase = self.DocumentPhase.POST_IMPLEMENTATION

        with transaction.atomic():
            if self.pk is None:
                max_ver = (
                    ProjectDocument.objects.select_for_update()
                    .filter(project=self.project, document_type=self.document_type)
                    .aggregate(Max("version"))["version__max"]
                    or 0
                )
                self.version = max_ver + 1

            if self.file and not self.sha256_checksum:
                self.sha256_checksum = self._compute_checksum()

            if self.is_latest:
                ProjectDocument.objects.filter(
                    project=self.project,
                    document_type=self.document_type,
                    is_latest=True,
                ).exclude(pk=self.pk).update(
                    is_latest=False,
                    status=self.Status.SUPERSEDED,
                )

            super().save(*args, **kwargs)

    def _compute_checksum(self) -> str:
        try:
            hasher = hashlib.sha256()
            self.file.seek(0)
            for chunk in self.file.chunks():
                hasher.update(chunk)
            self.file.seek(0)
            return hasher.hexdigest()
        except Exception:
            return ""

    @property
    def file_size_human(self) -> str:
        size = float(self.file_size_bytes or 0)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def is_mandatory_deliverable(self) -> bool:
        return self.document_type != self.DocumentType.SUPPORTING


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT ACTIVITIES (ACTION PLAN / STEPS / CHECKLIST)
# ─────────────────────────────────────────────────────────────────────────────

class ProjectActivity(models.Model):
    class Phase(models.TextChoices):
        PRE_IMPLEMENTATION  = "pre_implementation",  "Pre-Implementation & Discovery"
        IMPLEMENTATION      = "implementation",      "Implementation & Deployment"
        VALIDATION          = "validation",          "Testing & Validation"
        POST_IMPLEMENTATION = "post_implementation", "Handover & Post-Implementation"

    class Status(models.TextChoices):
        PENDING     = "pending",     "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        BLOCKED     = "blocked",     "Blocked"
        COMPLETED   = "completed",   "Completed"
        SKIPPED     = "skipped",     "Skipped / N/A"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="activities")
    step_number = models.PositiveSmallIntegerField()
    phase = models.CharField(
        max_length=25, choices=Phase.choices, default=Phase.IMPLEMENTATION, db_index=True
    )
    title = models.CharField(max_length=300)
    description = models.TextField(help_text="Detailed engineer instructions / action plan")
    code_snippet = models.TextField(blank=True)
    code_language = models.CharField(max_length=50, blank=True, default="powershell")
    expected_outcome = models.TextField(blank=True, help_text="Verification criteria")
    warning = models.TextField(blank=True)
    tip = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    is_optional = models.BooleanField(default=False)
    estimated_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)

    assigned_to = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_activities"
    )
    completed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="completed_activities"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="updated_activities"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["step_number"]
        verbose_name_plural = "Project Activities"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "step_number"], name="unique_project_activity_order"
            )
        ]

    def __str__(self):
        return f"{self.project.project_code} Step {self.step_number}: {self.title}"

    def mark_completed(self, user: User):
        self.status = self.Status.COMPLETED
        self.completed_by = user
        self.completed_at = timezone.now()
        self.updated_by = user
        self.save(update_fields=["status", "completed_by", "completed_at", "updated_by", "updated_at"])


# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE (SUPPORT RESOLUTIONS, RUNBOOKS & KNOWLEDGE GUIDES)
# ─────────────────────────────────────────────────────────────────────────────

class ArticleQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not user or not user.is_authenticated:
            return self.none()
        if user.is_admin:
            return self.all()

        # Visibility scope for published articles
        published_scope = Q(status=Article.Status.PUBLISHED) & (
            Q(visibility=Article.Visibility.PUBLIC)
            | Q(visibility=Article.Visibility.TEAM, allowed_teams__members=user)
            | Q(visibility=Article.Visibility.RESTRICTED, allowed_users=user)
            | Q(visibility=Article.Visibility.RESTRICTED, author=user)
            | Q(visibility=Article.Visibility.RESTRICTED, contributors=user)
            | Q(
                visibility=Article.Visibility.RESTRICTED,
                related_project__memberships__user=user,
            )
        )
        if user.is_lead:
            published_scope |= Q(
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.RESTRICTED,
            )

        # Unpublished / review articles visible to author, contributors, and leads (for in_review)
        unpublished_scope = Q(author=user) | Q(contributors=user)
        if user.is_lead:
            unpublished_scope |= Q(status=Article.Status.IN_REVIEW)

        return self.filter(published_scope | unpublished_scope).distinct()


class Article(models.Model):
    class ArticleType(models.TextChoices):
        SUPPORT  = "support",  "Support Resolution"
        RUNBOOK  = "runbook",  "Operational Runbook"
        SOFTWARE = "software", "Software & Script Guide"
        GENERAL  = "general",  "General Knowledge"

    class Status(models.TextChoices):
        DRAFT     = "draft",     "Draft"
        IN_REVIEW = "in_review", "In Review"
        PUBLISHED = "published", "Published"
        ARCHIVED  = "archived",  "Archived"

    class Severity(models.TextChoices):
        CRITICAL = "critical", "Critical"
        HIGH     = "high",     "High"
        MEDIUM   = "medium",   "Medium"
        LOW      = "low",      "Low"
        NA       = "n/a",      "Not Applicable"

    class Visibility(models.TextChoices):
        PUBLIC     = "public",     "All Staff"
        TEAM       = "team",       "Assigned Teams Only"
        RESTRICTED = "restricted", "Senior Staff & Authorized Users"
        PRIVATE    = "private",    "Author & Collaborators Only"

    class DifficultyLevel(models.TextChoices):
        BEGINNER     = "beginner",     "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED     = "advanced",     "Advanced"
        EXPERT       = "expert",       "Expert"

    # Core
    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=350, unique=True, blank=True, db_index=True)
    article_type = models.CharField(
        max_length=20, choices=ArticleType.choices, default=ArticleType.SUPPORT, db_index=True
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="articles")
    related_project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_articles",
        help_text="Optional project this support resolution or guide belongs to",
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="articles")
    summary = models.TextField(max_length=600, blank=True)
    content = models.TextField(help_text="Full resolution guide or documentation")
    search_keywords = models.TextField(blank=True)

    # Structured Support Resolution Fields
    symptoms = models.TextField(blank=True, help_text="Observed symptoms or user-reported issue")
    root_cause = models.TextField(blank=True, help_text="Confirmed root cause")
    verification_steps = models.TextField(blank=True, help_text="How to verify the issue is resolved")
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.NA)
    affected_systems = models.CharField(max_length=500, blank=True)
    error_codes = models.CharField(max_length=300, blank=True, db_index=True)
    microsoft_products = models.CharField(max_length=400, blank=True)
    resolution_type = models.CharField(max_length=100, blank=True)
    time_to_resolve_minutes = models.PositiveIntegerField(null=True, blank=True)

    # Guide / Implementation Metadata
    tech_stack = models.CharField(max_length=500, blank=True)
    difficulty_level = models.CharField(max_length=20, choices=DifficultyLevel.choices, blank=True)
    estimated_duration = models.CharField(max_length=100, blank=True)
    prerequisites = models.TextField(blank=True)

    # People & Access Control
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="authored_articles")
    contributors = models.ManyToManyField(User, blank=True, related_name="contributed_articles")
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_articles"
    )
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC, db_index=True
    )
    allowed_teams = models.ManyToManyField(Team, blank=True, related_name="articles")
    allowed_users = models.ManyToManyField(User, blank=True, related_name="permitted_articles")
    allow_engineer_collaboration = models.BooleanField(
        default=True,
        help_text="Allow other engineers with access to update and collaborate on this article.",
    )

    # Workflow
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    version = models.PositiveSmallIntegerField(default=1)
    review_notes = models.TextField(blank=True)

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

    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ["-is_pinned", "-updated_at"]
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
        base = slugify(self.title)[:300] or "article"
        slug, n = base, 1
        while Article.objects.filter(slug=slug).exclude(pk=self.pk).exists():
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
            "critical": "red",
            "high":     "orange",
            "medium":   "yellow",
            "low":      "green",
            "n/a":      "gray",
        }.get(self.severity, "gray")

    def increment_view(self, user=None, ip_address: str = "", user_agent: str = ""):
        Article.objects.filter(pk=self.pk).update(views_count=models.F("views_count") + 1)
        if ip_address:
            ArticleView.objects.create(
                article=self,
                user=user if (user and user.is_authenticated) else None,
                ip_address=ip_address,
                user_agent=(user_agent or "")[:300],
            )
        self.refresh_from_db(fields=["views_count"])

    # ── Scoped Permission Checks ─────────────────────────────────────────────

    def can_view(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_admin:
            return True
        if self.author_id == user.id or self.contributors.filter(pk=user.pk).exists():
            return True
        if self.status != self.Status.PUBLISHED:
            return self.status == self.Status.IN_REVIEW and user.is_lead
        if self.visibility == self.Visibility.PUBLIC:
            return True
        if self.visibility == self.Visibility.TEAM:
            return self.allowed_teams.filter(members=user).exists()
        if self.visibility == self.Visibility.RESTRICTED:
            if user.is_lead or self.allowed_users.filter(pk=user.pk).exists():
                return True
            if self.related_project and self.related_project.can_view(user):
                return True
            return False
        return False

    def can_edit(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_admin:
            return True
        if user.role == User.Role.VIEWER:
            return False
        if self.author_id == user.id or self.contributors.filter(pk=user.pk).exists():
            return True
        if self.allow_engineer_collaboration and user.is_engineer and self.can_view(user):
            return True
        return False

    def can_publish(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_admin or user.is_lead:
            return True
        return self.author_id == user.id and user.is_engineer

    def can_delete(self, user) -> bool:
        return bool(user and user.is_authenticated and user.is_admin)


class ResolutionStep(models.Model):
    """
    Ordered troubleshooting / action steps for Support Resolutions & Runbooks.
    """
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="steps")
    step_number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=300)
    description = models.TextField()
    code_snippet = models.TextField(blank=True)
    code_language = models.CharField(max_length=50, blank=True, default="powershell")
    warning = models.TextField(blank=True)
    tip = models.TextField(blank=True)
    estimated_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    is_optional = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["step_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "step_number"], name="unique_article_resolution_step_order"
            )
        ]

    def __str__(self):
        return f"Step {self.step_number}: {self.title}"


class ArticleRevision(models.Model):
    """
    Preserves historical edits when engineers collaborate on Support Resolutions.
    """
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=300)
    summary = models.TextField(blank=True)
    content = models.TextField()
    change_summary = models.CharField(max_length=300, blank=True)
    edited_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "version"], name="unique_article_revision_version"
            )
        ]

    def __str__(self):
        return f"{self.article.title} (v{self.version})"


# ─────────────────────────────────────────────────────────────────────────────
# ATTACHMENTS (SCREENSHOTS, LOGS, SCRIPTS & SUPPORTING FILES)
# ─────────────────────────────────────────────────────────────────────────────

def attachment_upload_path(instance, filename):
    clean_name = os.path.basename(filename)
    if instance.project_id:
        folder = f"projects/{instance.project.project_code or instance.project.slug}"
    elif instance.activity_id:
        proj = instance.activity.project
        folder = f"projects/{proj.project_code or proj.slug}/activities/{instance.activity.step_number}"
    elif instance.article_id:
        folder = f"articles/{instance.article.slug}"
    else:
        folder = "comments"
    return f"uploads/{folder}/attachments/{clean_name}"


class Attachment(models.Model):
    class AttachmentKind(models.TextChoices):
        SCREENSHOT = "screenshot", "Screenshot / Image"
        DOCUMENT   = "document",   "Document"
        LOG        = "log",        "Log / Diagnostic"
        SCRIPT     = "script",     "Script / Config"
        DIAGRAM    = "diagram",    "Architecture Diagram"
        OTHER      = "other",      "Other"

    article = models.ForeignKey(
        Article, null=True, blank=True, on_delete=models.CASCADE, related_name="attachments"
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.CASCADE, related_name="attachments"
    )
    activity = models.ForeignKey(
        ProjectActivity, null=True, blank=True, on_delete=models.CASCADE, related_name="attachments"
    )
    comment = models.ForeignKey(
        "Comment", null=True, blank=True, on_delete=models.CASCADE, related_name="attachments"
    )

    attachment_kind = models.CharField(
        max_length=20, choices=AttachmentKind.choices, default=AttachmentKind.OTHER
    )
    file = models.FileField(upload_to=attachment_upload_path, max_length=500)
    original_name = models.CharField(max_length=255)
    file_size_bytes = models.BigIntegerField(help_text="File size in bytes")
    file_type = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=300, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.original_name

    def clean(self):
        if not any([self.article_id, self.project_id, self.activity_id, self.comment_id]):
            raise ValidationError(
                "An attachment must be linked to an article, project, activity, or comment."
            )

    @property
    def is_image(self) -> bool:
        if self.attachment_kind == self.AttachmentKind.SCREENSHOT:
            return True
        if self.file_type.startswith("image/"):
            return True
        ext = os.path.splitext(self.original_name)[1].lower()
        return ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

    @property
    def file_size_human(self) -> str:
        size = float(self.file_size_bytes or 0)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# ─────────────────────────────────────────────────────────────────────────────
# COLLABORATION COMMENTS
# ─────────────────────────────────────────────────────────────────────────────

class Comment(models.Model):
    article = models.ForeignKey(
        Article, null=True, blank=True, on_delete=models.CASCADE, related_name="comments"
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.CASCADE, related_name="comments"
    )
    activity = models.ForeignKey(
        ProjectActivity, null=True, blank=True, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies"
    )
    content = models.TextField(max_length=3000)
    mentions = models.ManyToManyField(User, blank=True, related_name="mentioned_in_comments")
    is_approved = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    is_resolution_note = models.BooleanField(
        default=False, help_text="Highlight as an engineer resolution / action update"
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "created_at"]

    def __str__(self):
        target = self.article or self.project or self.activity
        return f"Comment by {self.author.email} on '{target}'"

    def clean(self):
        if not any([self.article_id, self.project_id, self.activity_id]):
            raise ValidationError("A comment must belong to an article, project, or activity.")

    @property
    def is_edited(self) -> bool:
        return self.edited_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# FEEDBACK, BOOKMARKS, VIEWS, SEARCH LOGS, NOTIFICATIONS & AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────

class ArticleFeedback(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="feedback")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="feedback_given")
    is_helpful = models.BooleanField()
    feedback_text = models.TextField(blank=True, max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["article", "user"], name="unique_user_article_feedback")
        ]

    def __str__(self):
        return f"{'Helpful' if self.is_helpful else 'Not Helpful'} by {self.user.email}"


class Bookmark(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookmarks")
    article = models.ForeignKey(
        Article, null=True, blank=True, on_delete=models.CASCADE, related_name="bookmarked_by"
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.CASCADE, related_name="bookmarked_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "article"],
                condition=Q(article__isnull=False),
                name="unique_user_article_bookmark",
            ),
            models.UniqueConstraint(
                fields=["user", "project"],
                condition=Q(project__isnull=False),
                name="unique_user_project_bookmark",
            ),
        ]

    def clean(self):
        if not (self.article_id or self.project_id):
            raise ValidationError("Bookmark must reference an article or a project.")


class ArticleView(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="views")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField()
    viewed_at = models.DateTimeField(auto_now_add=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-viewed_at"]


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


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        ARTICLE_PUBLISHED  = "article_published",  "Article Published"
        ARTICLE_UPDATED    = "article_updated",    "Article Updated"
        COMMENT            = "comment",            "New Comment"
        REVIEW_REQUEST     = "review_request",     "Review Requested"
        MENTION            = "mention",            "You Were Mentioned"
        PROJECT_ASSIGNED   = "project_assigned",   "Assigned to Project"
        DOCUMENT_UPLOADED  = "document_uploaded",  "Project Document Uploaded"
        DOCUMENT_APPROVED  = "document_approved",  "Project Document Approved"
        DOCUMENT_REJECTED  = "document_rejected",  "Project Document Needs Revision"
        ACTIVITY_ASSIGNED  = "activity_assigned",  "Activity Assigned"
        ACTIVITY_COMPLETED = "activity_completed", "Activity Completed"
        SYSTEM             = "system",             "System"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices)
    title = models.CharField(max_length=200)
    message = models.TextField(max_length=500)
    article = models.ForeignKey(
        Article, null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications"
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications"
    )
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


class AuditLog(models.Model):
    """
    Immutable enterprise audit trail for authentication, document uploads,
    approvals, permission changes, and content modifications.
    """
    class Action(models.TextChoices):
        USER_LOGIN         = "user_login",         "User Login"
        USER_ROLE_CHANGED  = "user_role_changed",  "User Role Changed"
        PROJECT_CREATED    = "project_created",    "Project Created"
        PROJECT_UPDATED    = "project_updated",    "Project Updated"
        PROJECT_DELETED    = "project_deleted",    "Project Deleted"
        DOCUMENT_UPLOADED  = "document_uploaded",  "Document Uploaded"
        DOCUMENT_APPROVED  = "document_approved",  "Document Approved"
        DOCUMENT_DOWNLOADED= "document_downloaded","Document Downloaded"
        ARTICLE_CREATED    = "article_created",    "Article Created"
        ARTICLE_UPDATED    = "article_updated",    "Article Updated"
        ARTICLE_PUBLISHED  = "article_published",  "Article Published"
        ARTICLE_DELETED    = "article_deleted",    "Article Deleted"
        PERMISSION_CHANGED = "permission_changed", "Permission Changed"

    actor = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    target_repr = models.CharField(max_length=300, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self):
        actor_str = self.actor.email if self.actor else "System"
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {actor_str} - {self.action} ({self.target_repr})"