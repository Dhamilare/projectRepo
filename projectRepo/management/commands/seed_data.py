from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from projectRepo.models import (
    Category,
    Tag,
    Article,
    ProjectStep,
    Comment,
    ArticleFeedback,
    ArticleView,
    SearchLog,
    Notification,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds the database with realistic sample enterprise engineering knowledge base data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Flushes existing non-superuser data before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("--- Starting Database Seeding Routine ---"))

        if options["flush"]:
            self.stdout.write(self.style.WARNING("Flushing existing non-superuser data..."))
            ArticleView.objects.all().delete()
            ArticleFeedback.objects.all().delete()
            Comment.objects.all().delete()
            ProjectStep.objects.all().delete()
            Notification.objects.all().delete()
            SearchLog.objects.all().delete()
            Article.objects.all().delete()
            Category.objects.all().delete()
            Tag.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

        # ----------------------------------------------------------------------
        # 1. SEED USERS
        # ----------------------------------------------------------------------
        self.stdout.write("1. Seeding User Accounts...")
        users_data = [
            {
                "email": "admin@company.com",
                "first_name": "Sarah",
                "last_name": "Connor",
                "role": User.Role.ADMIN,
                "department": "Infrastructure Eng",
                "job_title": "Principal Systems Architect",
            },
            {
                "email": "alex.dev@company.com",
                "first_name": "Alex",
                "last_name": "Mercer",
                "role": User.Role.ENGINEER,
                "department": "Infrastructure Eng",
                "job_title": "Senior Cloud Engineer",
            },
            {
                "email": "chen.wei@company.com",
                "first_name": "Chen",
                "last_name": "Wei",
                "role": User.Role.ENGINEER,
                "department": "DevOps Security",
                "job_title": "SecOps Automation Lead",
            },
            {
                "email": "jamal.k@company.com",
                "first_name": "Jamal",
                "last_name": "Khan",
                "role": User.Role.ENGINEER,
                "department": "End User Computing",
                "job_title": "Tier 3 Escalations Specialist",
            },
            {
                "email": "viewer.john@company.com",
                "first_name": "John",
                "last_name": "Doe",
                "role": User.Role.VIEWER,
                "department": "Helpdesk Support",
                "job_title": "Tier 1 Analyst",
            },
        ]

        created_users = []
        for u in users_data:
            user, created = User.objects.get_or_create(
                email=u["email"],
                defaults={
                    "username": u["email"], 
                    "first_name": u["first_name"],
                    "last_name": u["last_name"],
                    "role": u["role"],
                    "department": u["department"],
                    "job_title": u["job_title"],
                    "is_staff": True if u["role"] == User.Role.ADMIN else False,
                    "last_seen": timezone.now(),
                },
            )
            if created:
                user.set_password("Password123!")
                user.save()
            created_users.append(user)

        admin_user = next(u for u in created_users if u.role == User.Role.ADMIN)
        engineers = [u for u in created_users if u.role == User.Role.ENGINEER]

        # ----------------------------------------------------------------------
        # 2. SEED CATEGORIES
        # ----------------------------------------------------------------------
        self.stdout.write("2. Seeding Categories...")
        categories_def = [
            ("Identity & Entra ID", Category.CategoryType.SUPPORT, "#2563EB", "shield-check"),
            ("Exchange & Email Services", Category.CategoryType.SUPPORT, "#D97706", "mail"),
            ("Cloud Migration Playbooks", Category.CategoryType.PROJECT, "#059669", "cloud-upload"),
            ("DevOps & CI/CD Pipelines", Category.CategoryType.PROJECT, "#7C3AED", "terminal"),
            ("General IT Guidelines", Category.CategoryType.GENERAL, "#4B5563", "book-open"),
        ]

        categories = []
        for name, c_type, color, icon in categories_def:
            cat, _ = Category.objects.get_or_create(
                name=name,
                defaults={
                    "category_type": c_type,
                    "color_hex": color,
                    "icon": icon,
                    "description": f"Standard operational playbooks and logs for {name}.",
                    "created_by": admin_user,
                },
            )
            categories.append(cat)

        # ----------------------------------------------------------------------
        # 3. SEED TAGS
        # ----------------------------------------------------------------------
        self.stdout.write("3. Seeding Tags...")
        tag_names = [
            "Entra ID", "OAuth2.0", "MFA", "Hybrid Sync", "Exchange Online", 
            "PowerShell", "Terraform", "Kubernetes", "Troubleshooting", "Security"
        ]
        tags = []
        for tag_name in tag_names:
            t, _ = Tag.objects.get_or_create(name=tag_name, defaults={"color_hex": "#2563EB"})
            tags.append(t)

        # ----------------------------------------------------------------------
        # 4. SEED ARTICLES
        # ----------------------------------------------------------------------
        self.stdout.write("4. Seeding Articles & Steps...")

        # --- Article 1: Support Incident ---
        art1, _ = Article.objects.get_or_create(
            title="Troubleshooting Microsoft Entra ID Sync Failure: Duplicate UserPrincipalName Conflict",
            defaults={
                "article_type": Article.ArticleType.SUPPORT,
                "category": categories[0],  # Identity & Entra ID
                "author": engineers[0],
                "reviewed_by": admin_user,
                "status": Article.Status.PUBLISHED,
                "visibility": Article.Visibility.PUBLIC,
                "severity": Article.Severity.HIGH,
                "affected_systems": "Entra Connect Cloud Sync / On-Prem AD",
                "error_codes": "AttributeValueMustBeUnique / Fault 8344",
                "microsoft_products": "Microsoft Entra ID, Windows Server 2022 AD DS",
                "resolution_type": "Attribute Soft-Match Alignment / UPN Cleansing",
                "time_to_resolve_minutes": 45,
                "summary": "Step-by-step diagnostic process for resolving duplicate UserPrincipalName collisions during delta synchronization cycles.",
                "content": (
                    "<p>During execution of the identity synchronization cycle via Microsoft Entra Connect, "
                    "a critical processing block occurred due to a collision on the UPN attribute mapping.</p>"
                    "<h3>Root Cause Diagnostic Analysis</h3>"
                    "<p>This collision typically represents an attribute duplication failure. When directory synchronization handles "
                    "matching loops, it cross-references SMTP proxy addresses and UPN nodes. If a matching target string is found on a "
                    "conflicting object ID, the delta sync engine flags the transaction as un-routable.</p>"
                ),
                "is_featured": True,
                "is_verified": True,
                "published_at": timezone.now(),
            },
        )
        art1.tags.set(tags[:4])

        # --- Article 2: Project Playbook ---
        art2, _ = Article.objects.get_or_create(
            title="Hybrid Exchange Online Mailbox Migration Architecture & Execution Playbook",
            defaults={
                "article_type": Article.ArticleType.PROJECT,
                "category": categories[2],  # Cloud Migration
                "author": engineers[1],
                "reviewed_by": admin_user,
                "status": Article.Status.PUBLISHED,
                "visibility": Article.Visibility.PUBLIC,
                "project_type": "Datacenter to Cloud Migration",
                "tech_stack": "Exchange Server 2019, Exchange Online, Azure MRS, PowerShell",
                "difficulty_level": "High",
                "estimated_duration": "3 Weeks",
                "prerequisites": "1. Exchange Hybrid Configuration Wizard (HCW) executed successfully.\n2. MRSProxy endpoint enabled on Edge servers.\n3. Valid OAuth certificate configured.",
                "summary": "Comprehensive architectural guide for migrating 5,000+ enterprise mailboxes to Exchange Online without mail flow disruption.",
                "content": (
                    "<p>This playbook establishes the operational phases required to stage, move, and cut over legacy "
                    "on-premises Exchange mailboxes to M365 infrastructure seamlessly.</p>"
                ),
                "is_pinned": True,
                "is_verified": True,
                "published_at": timezone.now(),
            },
        )
        art2.tags.set([tags[4], tags[5], tags[8]])

        # Create Sequential Steps for the Project Article
        steps_data = [
            {
                "step_number": 1,
                "title": "Validate MRSProxy Endpoint Readiness",
                "description": "Ensure the Mailbox Replication Service Proxy endpoint is active and answering on Port 443 on all internal Exchange Client Access servers.",
                "code_snippet": "Get-WebServicesVirtualDirectory -Server EXCH01 | Set-WebServicesVirtualDirectory -MRSProxyEnabled $true",
                "code_language": "powershell",
                "warning": "Enabling MRSProxy restarts IIS AppPool services automatically. Run only during designated maintenance windows.",
                "estimated_minutes": 15,
            },
            {
                "step_number": 2,
                "title": "Create Migration Batch Payload Container",
                "description": "Compile user identity batches using CSV seed matrices containing PrimarySmtpAddress parameters.",
                "code_snippet": "New-MigrationBatch -Name 'Batch_Pilot_VIP' -CSVData ([System.IO.File]::ReadAllBytes('C:\\Mig\\pilot.csv')) -TargetDeliveryDomain 'tenant.mail.onmicrosoft.com'",
                "code_language": "powershell",
                "tip": "Limit batch sizes to 50 users per invocation to ensure max throughput without tripping tenant throttle limits.",
                "estimated_minutes": 30,
            },
        ]

        for s in steps_data:
            ProjectStep.objects.get_or_create(
                article=art2,
                step_number=s["step_number"],
                defaults=s,
            )

        # ----------------------------------------------------------------------
        # 5. SEED FEEDBACK, COMMENTS, SEARCH LOGS, NOTIFICATIONS
        # ----------------------------------------------------------------------
        self.stdout.write("5. Seeding Interactions & Telemetry Logs...")

        # Feedback
        ArticleFeedback.objects.get_or_create(
            article=art1, user=engineers[1], defaults={"is_helpful": True, "feedback_text": "Saved me 2 hours on a P2 incident."}
        )
        ArticleFeedback.objects.get_or_create(
            article=art2, user=admin_user, defaults={"is_helpful": True, "feedback_text": "Approved for corporate-wide rollout."}
        )

        # Comments
        c1, _ = Comment.objects.get_or_create(
            article=art1,
            author=admin_user,
            defaults={"content": "Ensure you clear the cache anchor before triggering the manual delta cycle.", "is_approved": True},
        )
        Comment.objects.get_or_create(
            article=art1,
            author=engineers[0],
            parent=c1,
            defaults={"content": "Confirmed. Added note to Step 3 of the diagnostic runbook.", "is_approved": True},
        )

        # Views & Search
        ArticleView.objects.create(article=art1, user=engineers[0], ip_address="192.168.1.100")
        ArticleView.objects.create(article=art2, user=engineers[1], ip_address="192.168.1.101")
        art1.views_count = 42
        art1.helpful_votes = 12
        art1.save()

        SearchLog.objects.create(query="Entra ID Sync Error", user=engineers[0], results_count=1, ip_address="192.168.1.100")
        SearchLog.objects.create(query="Exchange Migration", user=admin_user, results_count=3, ip_address="192.168.1.1")

        # Notifications
        Notification.objects.create(
            user=engineers[0],
            notification_type=Notification.NotificationType.COMMENT,
            title="New Reply on your Article",
            message=f"{admin_user.full_name} commented on 'Troubleshooting Microsoft Entra ID Sync Failure'.",
            article=art1,
        )

        # Update tag usage stats
        for tag in Tag.objects.all():
            tag.usage_count = tag.articles.count()
            tag.save()

        self.stdout.write(self.style.SUCCESS("Successfully populated sample engineering data!"))
        self.stdout.write(
            self.style.NOTICE(
                "\nSample Login Credentials:\n"
                " - Administrator: admin@company.com / Password123!\n"
                " - Engineer: alex.dev@company.com / Password123!\n"
                " - Viewer: viewer.john@company.com / Password123!\n"
            )
        )