import os
import bleach
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model

from .models import (
    Article,
    Attachment,
    Category,
    Comment,
    Project,
    ProjectActivity,
    ProjectDocument,
    ProjectMember,
    ResolutionStep,
    Tag,
    Team,
)

User = get_user_model()

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "s", "h2", "h3", "h4",
    "ul", "ol", "li", "blockquote", "pre", "code",
    "table", "thead", "tbody", "tr", "th", "td",
    "a", "img", "hr", "div", "span",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "code": ["class"],
    "div": ["class"],
    "span": ["class"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}

ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".md", ".csv", ".vsdx", ".visio", ".zip",
}

ALLOWED_ATTACHMENT_EXTENSIONS = ALLOWED_DOCUMENT_EXTENSIONS | {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".log", ".evtx", ".ps1", ".py", ".sh", ".bat", ".cmd",
    ".json", ".xml", ".yaml", ".yml", ".ini", ".reg",
}


def sanitize_html(html: str) -> str:
    return bleach.clean(html or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAILWIND LIGHT-MODE FORM MIXIN (CENTURY GOTHIC READY)
# ─────────────────────────────────────────────────────────────────────────────

class TailwindFormMixin:
    def apply_tailwind_styles(self):
        input_classes = (
            "w-full px-4 py-2.5 bg-white text-slate-800 border border-slate-200 rounded-lg "
            "shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent "
            "transition-all duration-200 text-sm placeholder-slate-400"
        )
        select_classes = (
            "w-full px-4 py-2.5 bg-white text-slate-800 border border-slate-200 rounded-lg "
            "shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent "
            "transition-all duration-200 text-sm"
        )
        textarea_classes = (
            "w-full px-4 py-2.5 bg-white text-slate-800 border border-slate-200 rounded-lg "
            "shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent "
            "transition-all duration-200 text-sm resize-y min-h-[100px] placeholder-slate-400"
        )
        multiselect_classes = (
            "w-full px-3 py-2 bg-white text-slate-800 border border-slate-200 rounded-lg "
            "shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent "
            "transition-all duration-200 text-sm min-h-[120px]"
        )
        checkbox_classes = (
            "h-4 w-4 text-blue-600 bg-white border-slate-300 rounded "
            "focus:ring-blue-500 focus:ring-2 transition duration-150 cursor-pointer"
        )
        file_classes = (
            "block w-full text-sm text-slate-600 bg-white border border-slate-200 rounded-lg "
            "file:mr-4 file:py-2.5 file:px-4 file:rounded-l-lg file:border-0 "
            "file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 "
            "hover:file:bg-blue-100 cursor-pointer"
        )

        for _, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.HiddenInput):
                continue

            current_attrs = widget.attrs
            existing = current_attrs.get("class", "")

            if isinstance(widget, forms.Textarea):
                base = textarea_classes
            elif isinstance(widget, forms.SelectMultiple):
                base = multiselect_classes
            elif isinstance(widget, forms.Select):
                base = select_classes
            elif isinstance(widget, forms.CheckboxInput):
                base = checkbox_classes
            elif isinstance(widget, (forms.FileInput, forms.ClearableFileInput)):
                base = file_classes
            else:
                base = input_classes

            current_attrs["class"] = f"{base} {existing}".strip()
            widget.attrs = current_attrs


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT FORMS
# ─────────────────────────────────────────────────────────────────────────────

class ProjectForm(TailwindFormMixin, forms.ModelForm):
    tag_names = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "e.g. Windows Autopilot, Intune, Entra ID, Zero-Touch…",
            "autocomplete": "off",
        }),
        help_text="Comma-separated tags for fast project lookup.",
    )

    class Meta:
        model = Project
        fields = [
            "project_code", "title", "client_or_unit", "category",
            "summary", "scope_notes", "microsoft_products", "tech_stack", "prerequisites",
            "status", "priority", "start_date", "target_end_date",
            "project_lead", "visibility", "allowed_teams", "allow_open_collaboration",
        ]
        widgets = {
            "project_code": forms.TextInput(attrs={"placeholder": "Auto-generated if left blank (e.g. PRJ-2026-001)"}),
            "title": forms.TextInput(attrs={"placeholder": "e.g. Enterprise Windows Autopilot Rollout"}),
            "client_or_unit": forms.TextInput(attrs={"placeholder": "Client name, Subsidiary, or Business Unit"}),
            "summary": forms.Textarea(attrs={"rows": 3, "placeholder": "Executive summary of project objectives..."}),
            "scope_notes": forms.Textarea(attrs={"rows": 4, "placeholder": "In-scope / out-of-scope overview..."}),
            "microsoft_products": forms.TextInput(attrs={"placeholder": "e.g. Windows Autopilot, Microsoft Intune, Entra ID"}),
            "tech_stack": forms.TextInput(attrs={"placeholder": "e.g. PowerShell, Graph API, Conditional Access"}),
            "prerequisites": forms.Textarea(attrs={"rows": 3, "placeholder": "Licensing, network, or identity prerequisites..."}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "target_end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("name")
        self.fields["project_lead"].queryset = User.objects.filter(
            is_active=True, role__in=[User.Role.ADMIN, User.Role.LEAD, User.Role.ENGINEER]
        ).order_by("first_name", "last_name")
        self.fields["allowed_teams"].queryset = Team.objects.filter(is_active=True).order_by("name")

        if self.instance.pk:
            self.fields["tag_names"].initial = ", ".join(
                self.instance.tags.values_list("name", flat=True)
            )
            self.fields["project_code"].disabled = True

        self.apply_tailwind_styles()

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if len(title) < 4:
            raise forms.ValidationError("Project title must be at least 4 characters.")
        return title

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        target = cleaned.get("target_end_date")
        if start and target and target < start:
            self.add_error("target_end_date", "Target completion date cannot precede start date.")
        return cleaned

    def save(self, commit=True):
        project = super().save(commit=False)
        if commit:
            project.save()
            self.save_m2m()
            self._save_tags(project)
        return project

    def _save_tags(self, project):
        raw = self.cleaned_data.get("tag_names", "")
        names = [t.strip() for t in raw.split(",") if t.strip()]
        tags = []
        for name in names:
            tag = Tag.objects.filter(name__iexact=name).first()
            if not tag:
                tag = Tag.objects.create(name=name)
            tags.append(tag)
        project.tags.set(tags)


class ProjectDocumentUploadForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectDocument
        fields = ["document_type", "title", "file", "status", "change_notes"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Windows Autopilot Statement of Work v1"}),
            "change_notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Describe updates, scope additions, or sign-off notes..."}),
        }

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop("project", None)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        can_approve = bool(self.project and self.user and self.project.can_approve_documents(self.user))
        if not can_approve:
            self.fields["status"].choices = [
                (ProjectDocument.Status.DRAFT, "Draft (Work in Progress)"),
                (ProjectDocument.Status.IN_REVIEW, "Submit for Review"),
            ]
        else:
            self.fields["status"].choices = [
                (ProjectDocument.Status.DRAFT, "Draft (Work in Progress)"),
                (ProjectDocument.Status.IN_REVIEW, "In Review"),
                (ProjectDocument.Status.APPROVED, "Approved"),
            ]
        self.apply_tailwind_styles()

    def clean_file(self):
        file_obj = self.cleaned_data.get("file")
        if not file_obj:
            raise forms.ValidationError("Please attach a document file.")

        ext = os.path.splitext(file_obj.name)[1].lower()
        if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise forms.ValidationError(
                f"Unsupported file format '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}"
            )

        max_mb = getattr(settings, "MAX_DOCUMENT_SIZE_MB", 50)
        if file_obj.size > max_mb * 1024 * 1024:
            raise forms.ValidationError(f"Document exceeds maximum allowed size of {max_mb} MB.")
        return file_obj


class ProjectDocumentReviewForm(TailwindFormMixin, forms.Form):
    decision = forms.ChoiceField(
        choices=[
            (ProjectDocument.Status.APPROVED, "Approve Document"),
            (ProjectDocument.Status.DRAFT, "Return to Draft (Needs Revision)"),
        ]
    )
    review_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Provide approval remarks or revision instructions..."}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styles()


class ProjectActivityForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectActivity
        fields = [
            "step_number", "phase", "title", "description",
            "code_snippet", "code_language", "expected_outcome",
            "warning", "tip", "status", "assigned_to",
            "due_date", "estimated_minutes", "is_optional",
        ]
        widgets = {
            "step_number": forms.NumberInput(attrs={"min": "1", "placeholder": "Auto"}),
            "title": forms.TextInput(attrs={"placeholder": "e.g. Configure Autopilot Deployment Profile in Intune"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Detailed action plan instructions for engineers..."}),
            "code_snippet": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "# PowerShell, Graph API, or CLI commands...",
                "class": "bg-slate-50 font-mono text-xs",
            }),
            "code_language": forms.TextInput(attrs={"placeholder": "powershell"}),
            "expected_outcome": forms.Textarea(attrs={"rows": 2, "placeholder": "What confirms this step succeeded?"}),
            "warning": forms.Textarea(attrs={"rows": 2, "placeholder": "Critical risks or prerequisites before executing..."}),
            "tip": forms.Textarea(attrs={"rows": 2, "placeholder": "Helpful engineering shortcuts or gotchas..."}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "estimated_minutes": forms.NumberInput(attrs={"min": "1", "placeholder": "Minutes"}),
        }

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop("project", None)
        super().__init__(*args, **kwargs)
        self.fields["step_number"].required = False
        self.fields["assigned_to"].queryset = User.objects.filter(
            is_active=True, role__in=[User.Role.ADMIN, User.Role.LEAD, User.Role.ENGINEER]
        ).order_by("first_name", "last_name")
        self.apply_tailwind_styles()

    def clean_step_number(self):
        step_num = self.cleaned_data.get("step_number")
        if step_num is not None and self.project:
            qs = ProjectActivity.objects.filter(project=self.project, step_number=step_num)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"Step #{step_num} already exists in this project.")
        return step_num


class ProjectMemberForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectMember
        fields = ["user", "role", "can_upload_docs", "can_approve_docs"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(is_active=True).order_by("first_name", "last_name")
        self.apply_tailwind_styles()


# ─────────────────────────────────────────────────────────────────────────────
# SUPPORT RESOLUTION & KNOWLEDGE BASE FORMS
# ─────────────────────────────────────────────────────────────────────────────

class ArticleForm(TailwindFormMixin, forms.ModelForm):
    tag_names = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "e.g. Autopilot, 80180014, TPM, Hybrid Join…",
            "autocomplete": "off",
        }),
        help_text="Comma-separated tags for fast search indexing.",
    )
    change_summary = forms.CharField(
        required=False,
        max_length=300,
        widget=forms.TextInput(attrs={
            "placeholder": "Briefly describe what you updated (saved to revision history)...",
        }),
    )

    class Meta:
        model = Article
        fields = [
            "title", "article_type", "category", "related_project",
            "summary", "symptoms", "root_cause", "content", "verification_steps",
            "search_keywords", "status", "visibility",
            "allowed_teams", "allowed_users", "allow_engineer_collaboration",
            "severity", "affected_systems", "error_codes", "microsoft_products",
            "resolution_type", "time_to_resolve_minutes",
            "tech_stack", "difficulty_level", "estimated_duration", "prerequisites",
            "is_featured", "is_pinned", "needs_review", "contributors", "related_articles",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Specify exact symptom, error, or operational runbook title..."}),
            "article_type": forms.Select(attrs={"id": "id_article_type"}),
            "summary": forms.Textarea(attrs={"rows": 2, "placeholder": "Concise executive summary shown in search & cards..."}),
            "symptoms": forms.Textarea(attrs={"rows": 3, "placeholder": "Describe user-facing symptoms or alert indicators..."}),
            "root_cause": forms.Textarea(attrs={"rows": 3, "placeholder": "Document the confirmed technical root cause..."}),
            "content": forms.Textarea(attrs={"rows": 14, "id": "article-content-editor", "class": "rich-editor"}),
            "verification_steps": forms.Textarea(attrs={"rows": 3, "placeholder": "How to verify the fix worked..."}),
            "search_keywords": forms.TextInput(attrs={"placeholder": "Additional lookup keywords or aliases..."}),
            "affected_systems": forms.TextInput(attrs={"placeholder": "e.g. Windows 11, Intune Enrollment, Entra ID..."}),
            "error_codes": forms.TextInput(attrs={"placeholder": "e.g. 0x80180014, 80070774..."}),
            "microsoft_products": forms.TextInput(attrs={"placeholder": "e.g. Windows Autopilot, Intune, Defender..."}),
            "resolution_type": forms.TextInput(attrs={"placeholder": "e.g. Policy Reconfiguration, Script Fix, Registry Patch..."}),
            "time_to_resolve_minutes": forms.NumberInput(attrs={"placeholder": "0", "min": "0"}),
            "tech_stack": forms.TextInput(attrs={"placeholder": "e.g. Intune, PowerShell, Graph API..."}),
            "estimated_duration": forms.TextInput(attrs={"placeholder": "e.g. 30 minutes"}),
            "prerequisites": forms.Textarea(attrs={"rows": 3, "placeholder": "Required admin roles or access permissions..."}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("name")
        if self.user:
            self.fields["related_project"].queryset = Project.objects.visible_to(self.user).order_by("title")
        else:
            self.fields["related_project"].queryset = Project.objects.all().order_by("title")

        qs = Article.objects.filter(status=Article.Status.PUBLISHED)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["related_articles"].queryset = qs.order_by("title")[:200]
        self.fields["contributors"].queryset = User.objects.filter(is_active=True).order_by("first_name", "last_name")
        self.fields["allowed_teams"].queryset = Team.objects.filter(is_active=True).order_by("name")
        self.fields["allowed_users"].queryset = User.objects.filter(is_active=True).order_by("first_name", "last_name")

        if self.user and not self.user.can_publish():
            self.fields["status"].choices = [
                (Article.Status.DRAFT, "Draft"),
                (Article.Status.IN_REVIEW, "In Review"),
            ]

        if self.instance.pk:
            self.fields["tag_names"].initial = ", ".join(
                self.instance.tags.values_list("name", flat=True)
            )
        else:
            self.fields["change_summary"].widget = forms.HiddenInput()

        self.apply_tailwind_styles()

    def clean_content(self):
        return sanitize_html(self.cleaned_data.get("content", ""))

    def clean_symptoms(self):
        return sanitize_html(self.cleaned_data.get("symptoms", ""))

    def clean_root_cause(self):
        return sanitize_html(self.cleaned_data.get("root_cause", ""))

    def clean_verification_steps(self):
        return sanitize_html(self.cleaned_data.get("verification_steps", ""))

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if len(title) < 5:
            raise forms.ValidationError("Title must be at least 5 characters.")
        return title

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("article_type") == Article.ArticleType.SUPPORT and not cleaned.get("severity"):
            self.add_error("severity", "Severity is required for support resolution articles.")
        return cleaned

    def save(self, commit=True):
        article = super().save(commit=False)
        if commit:
            article.save()
            self.save_m2m()
            self._save_tags(article)
        return article

    def _save_tags(self, article):
        raw = self.cleaned_data.get("tag_names", "")
        names = [t.strip() for t in raw.split(",") if t.strip()]
        tags = []
        for name in names:
            tag = Tag.objects.filter(name__iexact=name).first()
            if not tag:
                tag = Tag.objects.create(name=name)
            tags.append(tag)
        article.tags.set(tags)


class ResolutionStepForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ResolutionStep
        fields = [
            "step_number", "title", "description", "code_snippet",
            "code_language", "warning", "tip", "estimated_minutes", "is_optional",
        ]
        widgets = {
            "step_number": forms.HiddenInput(),
            "title": forms.TextInput(attrs={"placeholder": "Step title (e.g. Check Autopilot Hardware Hash)..."}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Detailed troubleshooting or execution instructions..."}),
            "code_snippet": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "# PowerShell, CMD, or diagnostic commands...",
                "class": "bg-slate-50 font-mono text-xs",
            }),
            "code_language": forms.TextInput(attrs={"placeholder": "powershell"}),
            "warning": forms.Textarea(attrs={"rows": 2, "placeholder": "Critical risk or prerequisite warning..."}),
            "tip": forms.Textarea(attrs={"rows": 2, "placeholder": "Helpful verification tip..."}),
            "estimated_minutes": forms.NumberInput(attrs={"min": "1", "placeholder": "Minutes"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styles()


ResolutionStepFormSet = forms.inlineformset_factory(
    Article,
    ResolutionStep,
    form=ResolutionStepForm,
    extra=1,
    can_delete=True,
    min_num=0,
)


# ─────────────────────────────────────────────────────────────────────────────
# COLLABORATION, ATTACHMENTS, TAXONOMIES & SEARCH
# ─────────────────────────────────────────────────────────────────────────────

class CommentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["content", "is_resolution_note"]
        widgets = {
            "content": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Share resolution updates, findings, or coordinate next steps with engineers...",
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styles()

    def clean_content(self):
        content = self.cleaned_data.get("content", "").strip()
        if len(content) < 4:
            raise forms.ValidationError("Comment must contain at least 4 characters.")
        return bleach.clean(content, tags=["p", "br", "strong", "em", "code"], strip=True)


class AttachmentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ["attachment_kind", "file", "description"]
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "Optional caption or screenshot description..."}),
            "file": forms.FileInput(attrs={"accept": "*/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styles()

    def clean_file(self):
        file_obj = self.cleaned_data.get("file")
        if not file_obj:
            return file_obj
        ext = os.path.splitext(file_obj.name)[1].lower()
        if ext and ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
            raise forms.ValidationError(f"File extension '{ext}' is not permitted for security reasons.")
        max_mb = getattr(settings, "MAX_ATTACHMENT_SIZE_MB", 25)
        if file_obj.size > max_mb * 1024 * 1024:
            raise forms.ValidationError(f"File exceeds maximum size limit of {max_mb} MB.")
        return file_obj


class TeamForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name", "description", "lead", "members", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Modern Workplace & Autopilot"}),
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "Team scope and responsibilities..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lead"].queryset = User.objects.filter(is_active=True).order_by("first_name", "last_name")
        self.fields["members"].queryset = User.objects.filter(is_active=True).order_by("first_name", "last_name")
        self.apply_tailwind_styles()


class CategoryForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "category_type", "parent", "color_hex", "sort_order", "description", "allowed_teams", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Windows Autopilot"}),
            "color_hex": forms.TextInput(attrs={"type": "color"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Category.objects.filter(is_active=True, parent=None).order_by("name")
        self.fields["allowed_teams"].queryset = Team.objects.filter(is_active=True).order_by("name")
        self.apply_tailwind_styles()


class SearchForm(TailwindFormMixin, forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Search projects, SOW/As-Built docs, resolutions, error codes…",
            "autocomplete": "off",
            "data-search-suggestions": "true",
        }),
    )
    scope = forms.ChoiceField(
        required=False,
        choices=[
            ("all", "Projects & Knowledge Base"),
            ("projects", "Projects & Deliverables Only"),
            ("articles", "Support Resolutions & Guides Only"),
        ],
        initial="all",
    )
    article_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Article Types")] + list(Article.ArticleType.choices),
    )
    category = forms.ModelChoiceField(
        required=False,
        queryset=Category.objects.filter(is_active=True).order_by("name"),
        empty_label="All Categories",
    )
    severity = forms.ChoiceField(
        required=False,
        choices=[("", "Any Severity")] + list(Article.Severity.choices),
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("-updated_at", "Recently Updated"),
            ("-published_at", "Recently Published"),
            ("-views_count", "Most Viewed"),
            ("-helpful_votes", "Most Helpful"),
            ("title", "Title A–Z"),
        ],
        initial="-updated_at",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styles()