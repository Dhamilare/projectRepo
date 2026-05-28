import bleach
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model

from .models import Article, ProjectStep, Comment, Category, Tag, Attachment

User = get_user_model()

# Allowed HTML tags/attributes for the article content body
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


def sanitize_html(html: str) -> str:
    """Strip disallowed tags/attributes to prevent cross-site scripting (XSS)."""
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAILWIND DESIGN MIXIN
# ─────────────────────────────────────────────────────────────────────────────

class TailwindFormMixin:
    """
    Programmatically injects clean, unified Tailwind UI styles into form inputs.
    Engineered cleanly for modern light-mode setups and Century Gothic text styling.
    """
    def apply_tailwind_styles(self):
        # Premium Tailwind UI baseline components
        input_classes = "w-full px-4 py-2.5 bg-white text-slate-800 border border-slate-200 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent transition-all duration-200 text-sm font-sans placeholder-slate-400"
        select_classes = "w-full px-4 py-2.5 bg-white text-slate-800 border border-slate-200 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent transition-all duration-200 text-sm font-sans"
        textarea_classes = "w-full px-4 py-2.5 bg-white text-slate-800 border border-slate-200 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent transition-all duration-200 text-sm font-sans resize-y min-h-[100px] placeholder-slate-400"
        multiselect_classes = "w-full px-4 py-2 bg-white text-slate-800 border border-slate-200 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent transition-all duration-200 text-sm font-sans min-h-[120px]"
        checkbox_classes = "h-4 w-4 text-blue-600 border-slate-300 rounded focus:ring-blue-500 focus:ring-2 transition duration-150 cursor-pointer"

        for field_name, field in self.fields.items():
            widget = field.widget
            
            # Preserve existing custom attributes while layering Tailwind updates safely
            current_attrs = widget.attrs
            
            if isinstance(widget, forms.Textarea):
                current_attrs["class"] = textarea_classes if "class" not in current_attrs else f"{textarea_classes} {current_attrs['class']}"
            elif isinstance(widget, forms.SelectMultiple):
                current_attrs["class"] = multiselect_classes if "class" not in current_attrs else f"{multiselect_classes} {current_attrs['class']}"
            elif isinstance(widget, forms.Select):
                current_attrs["class"] = select_classes if "class" not in current_attrs else f"{select_classes} {current_attrs['class']}"
            elif isinstance(widget, forms.CheckboxInput):
                current_attrs["class"] = checkbox_classes if "class" not in current_attrs else f"{checkbox_classes} {current_attrs['class']}"
            else:
                current_attrs["class"] = input_classes if "class" not in current_attrs else f"{input_classes} {current_attrs['class']}"
                
            widget.attrs = current_attrs


# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE MASTER FORM
# ─────────────────────────────────────────────────────────────────────────────

class ArticleForm(TailwindFormMixin, forms.ModelForm):
    """
    Master operational form managing both Service Resolutions and Playbooks.
    Tailwind integrated layout configurations map onto dynamic JS switches.
    """

    tag_names = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter tags separated by commas (e.g. Exchange, MFA, Azure AD)…",
            "autocomplete": "off",
        }),
        help_text="Comma-separated list of tags used for index sorting references.",
    )

    class Meta:
        model = Article
        fields = [
            "title", "article_type", "category", "summary", "content", "search_keywords",
            "status", "visibility", "severity", "affected_systems", "error_codes",
            "microsoft_products", "resolution_type", "time_to_resolve_minutes",
            "project_type", "tech_stack", "difficulty_level", "estimated_duration", "prerequisites",
            "is_featured", "is_pinned", "needs_review", "contributors", "related_articles",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Specify exact symptom or playbook objective..."}),
            "article_type": forms.Select(attrs={"id": "id_article_type"}),
            "category": forms.Select(),
            "summary": forms.Textarea(attrs={"rows": 3, "placeholder": "Provide a brief description shown in listings..."}),
            "content": forms.Textarea(attrs={"rows": 18, "id": "article-content-editor", "class": "rich-editor"}),
            "search_keywords": forms.TextInput(attrs={"placeholder": "Keywords for engine search optimization..."}),
            "status": forms.Select(),
            "visibility": forms.Select(),
            "severity": forms.Select(),
            "affected_systems": forms.TextInput(attrs={"placeholder": "e.g. Exchange Online, Entra ID, Local SAN..."}),
            "error_codes": forms.TextInput(attrs={"placeholder": "e.g. 0x800CCC0F, ERR_CONN_REFUSED..."}),
            "microsoft_products": forms.TextInput(attrs={"placeholder": "e.g. Microsoft 365, Exchange Server 2019..."}),
            "resolution_type": forms.TextInput(attrs={"placeholder": "e.g. Mailbox Replication, Tenant Hardening..."}),
            "time_to_resolve_minutes": forms.NumberInput(attrs={"placeholder": "0", "min": "0"}),
            "project_type": forms.TextInput(attrs={"placeholder": "e.g. Cloud Tenant Migration, Forest Trust Build..."}),
            "tech_stack": forms.TextInput(attrs={"placeholder": "e.g. Exchange Hybrid, Azure AD Connect..."}),
            "difficulty_level": forms.Select(),
            "estimated_duration": forms.TextInput(attrs={"placeholder": "e.g. 3 hours, 2 days..."}),
            "prerequisites": forms.Textarea(attrs={"rows": 4, "placeholder": "Specify configuration requirements or administrative access needed..."}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Enforce filtering constraints onto raw relation sets
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("name")

        qs = Article.objects.filter(status=Article.Status.PUBLISHED)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["related_articles"].queryset = qs.order_by("title")[:200]

        self.fields["contributors"].queryset = User.objects.filter(is_active=True).order_by("first_name", "last_name")

        # Dynamic authorization constraint filters
        if self.user and not self.user.can_publish():
            self.fields["status"].choices = [
                (Article.Status.DRAFT, "Draft"),
                (Article.Status.IN_REVIEW, "In Review"),
            ]

        if self.instance.pk:
            self.fields["tag_names"].initial = ", ".join(
                self.instance.tags.values_list("name", flat=True)
            )
            
        # Programmatically apply corporate Tailwind layout structures
        self.apply_tailwind_styles()

    def clean_content(self):
        return sanitize_html(self.cleaned_data.get("content", ""))

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if len(title) < 5:
            raise forms.ValidationError("Title must be at least 5 characters.")
        return title

    def clean(self):
        cleaned = super().clean()
        article_type = cleaned.get("article_type")
        
        if article_type == Article.ArticleType.SUPPORT:
            if not cleaned.get("severity"):
                self.add_error("severity", "Severity is required for support articles.")
        return cleaned

    def save(self, commit=True):
        article = super().save(commit=False)
        if commit:
            article.save()
            self._save_tags(article)
            self.save_m2m()
        return article

    def _save_tags(self, article):
        """Resolves raw comma strings into synchronized relational database records safely."""
        tag_names_raw = self.cleaned_data.get("tag_names", "")
        tag_names = [t.strip() for t in tag_names_raw.split(",") if t.strip()]
        tags = []
        for name in tag_names:
            # BUGFIX: Lowercase conversion match optimization prevents key parsing crash vectors on PostgreSQL
            tag = Tag.objects.filter(name__iexact=name).first()
            if not tag:
                tag = Tag.objects.create(name=name)
            tags.append(tag)
        article.tags.set(tags)


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT EXECUTION STEP LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

class ProjectStepForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectStep
        fields = [
            "step_number", "title", "description", "code_snippet", 
            "code_language", "warning", "tip", "estimated_minutes", "is_optional",
        ]
        widgets = {
            "step_number": forms.HiddenInput(),
            "title": forms.TextInput(attrs={"placeholder": "Provide an absolute milestone title…"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Engineering task details instructions..."}),
            "code_snippet": forms.Textarea(attrs={
                "rows": 5, 
                "placeholder": "# Enter your PowerShell, CLI, or config blocks here…",
                "class": "bg-slate-50 border-slate-200 text-slate-900 font-mono focus:bg-white text-xs",
            }),
            "code_language": forms.TextInput(attrs={"placeholder": "powershell"}),
            "warning": forms.Textarea(attrs={"rows": 2, "placeholder": "⚠ Critical configuration risks or production loss indicators…"}),
            "tip": forms.Textarea(attrs={"rows": 2, "placeholder": "💡 Helpful execution shortcuts or monitoring checks…"}),
            "estimated_minutes": forms.NumberInput(attrs={"min": "1", "placeholder": "Minutes"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styles()


ProjectStepFormSet = forms.inlineformset_factory(
    Article,
    ProjectStep,
    form=ProjectStepForm,
    extra=1,
    can_delete=True,
    min_num=0,
)


# ─────────────────────────────────────────────────────────────────────────────
# COLLABORATIVE INTERACTION MATRIX
# ─────────────────────────────────────────────────────────────────────────────

class CommentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Provide diagnostic modifications, troubleshooting adjustments, or documentation updates…",
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styles()

    def clean_content(self):
        content = self.cleaned_data.get("content", "").strip()
        if len(content) < 10:
            raise forms.ValidationError("Comment must contain at least 10 characters.")
        return bleach.clean(content, tags=["p", "br", "strong", "em", "code"], strip=True)


# ─────────────────────────────────────────────────────────────────────────────
# REPOSITORY DIGITAL ASSETS FORM
# ─────────────────────────────────────────────────────────────────────────────

class AttachmentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ["file", "description"]
        widgets = {
            "file": forms.FileInput(attrs={
                "accept": "*/*",
                "class": "block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer file:transition-all"
            }),
            "description": forms.TextInput(attrs={"placeholder": "e.g. Mailbox migration CSV template, environment topology diagram..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styles()

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if not file:
            return file
        max_size = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
        if file.size > max_size:
            raise forms.ValidationError(
                f"File payload size configuration limits exceeded. Maximum cap is {settings.MAX_ATTACHMENT_SIZE_MB} MB."
            )
        return file


# ─────────────────────────────────────────────────────────────────────────────
# EXTENSIVE SEARCH PARAMETERS FRAMEWORK
# ─────────────────────────────────────────────────────────────────────────────

class SearchForm(TailwindFormMixin, forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Search resolutions, playbooks, error codes or keywords…",
            "autocomplete": "off",
            "data-search-suggestions": "true",
        })
    )
    article_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Documentation Types")] + list(Article.ArticleType.choices),
        widget=forms.Select(),
    )
    category = forms.ModelChoiceField(
        required=False,
        queryset=Category.objects.filter(is_active=True).order_by("name"),
        empty_label="All Tech Taxonomies",
        widget=forms.Select(),
    )
    severity = forms.ChoiceField(
        required=False,
        choices=[("", "Any Incident Severity")] + list(Article.Severity.choices),
        widget=forms.Select(),
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("-updated_at", "Recently Updated Logs"),
            ("-published_at", "Recently Deployed Records"),
            ("-views_count", "Highest View Telemetry"),
            ("-helpful_votes", "Peer Verified Resolutions"),
            ("title", "Alphabetical Sort A–Z"),
        ],
        initial="-updated_at",
        widget=forms.Select(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styles()