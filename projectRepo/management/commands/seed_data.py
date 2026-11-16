from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from projectRepo.models import (
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
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds the database with enterprise Projects, Mandatory Deliverables, Support Resolutions, and RBAC sample data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Deletes all non-superuser repository data before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("━━━  Enterprise Project & Support Repository — Seeding Routine  ━━━"))

        if options["flush"]:
            self.stdout.write(self.style.WARNING("  Flushing existing data…"))
            AuditLog.objects.all().delete()
            Bookmark.objects.all().delete()
            ArticleRevision.objects.all().delete()
            ArticleView.objects.all().delete()
            ArticleFeedback.objects.all().delete()
            Comment.objects.all().delete()
            Attachment.objects.all().delete()
            ResolutionStep.objects.all().delete()
            ProjectActivity.objects.all().delete()
            ProjectDocument.objects.all().delete()
            ProjectMember.objects.all().delete()
            Notification.objects.all().delete()
            SearchLog.objects.all().delete()
            Article.objects.all().delete()
            Project.objects.all().delete()
            Category.objects.all().delete()
            Tag.objects.all().delete()
            Team.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

        now = timezone.now()
        today = now.date()

        # ──────────────────────────────────────────────────────────────────────
        # 1. USERS (ADMIN, LEAD, ENGINEER, VIEWER)
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  1. Creating users…")
        users_data = [
            dict(
                email="admin@msp.com",
                first_name="Sarah",
                last_name="Connor",
                role=User.Role.ADMIN,
                department="Infrastructure Engineering",
                job_title="Principal Systems Architect",
                is_staff=True,
            ),
            dict(
                email="alex.m@msp.com",
                first_name="Alex",
                last_name="Mercer",
                role=User.Role.LEAD,
                department="Infrastructure Engineering",
                job_title="Lead Cloud Engineer",
                is_staff=False,
            ),
            dict(
                email="priya.r@msp.com",
                first_name="Priya",
                last_name="Ramesh",
                role=User.Role.LEAD,
                department="Microsoft 365 Practice",
                job_title="Lead M365 & Exchange Architect",
                is_staff=False,
            ),
            dict(
                email="chen.w@msp.com",
                first_name="Chen",
                last_name="Wei",
                role=User.Role.ENGINEER,
                department="DevOps & Security",
                job_title="SecOps Automation Engineer",
                is_staff=False,
            ),
            dict(
                email="jamal.k@msp.com",
                first_name="Jamal",
                last_name="Khan",
                role=User.Role.ENGINEER,
                department="End User Computing",
                job_title="Modern Workplace / Autopilot Engineer",
                is_staff=False,
            ),
            dict(
                email="tom.b@msp.com",
                first_name="Tom",
                last_name="Briggs",
                role=User.Role.ENGINEER,
                department="Network Engineering",
                job_title="Network Infrastructure Engineer",
                is_staff=False,
            ),
            dict(
                email="viewer.j@msp.com",
                first_name="John",
                last_name="Doe",
                role=User.Role.VIEWER,
                department="Helpdesk Support",
                job_title="Tier 1 Analyst",
                is_staff=False,
            ),
            dict(
                email="viewer.a@msp.com",
                first_name="Amina",
                last_name="Osei",
                role=User.Role.VIEWER,
                department="Project Management Office",
                job_title="Project Coordinator",
                is_staff=False,
            ),
        ]

        created_users = {}
        for u in users_data:
            user, created = User.objects.get_or_create(
                email=u["email"],
                defaults={
                    "username": u["email"].split("@")[0],
                    "first_name": u["first_name"],
                    "last_name": u["last_name"],
                    "role": u["role"],
                    "department": u["department"],
                    "job_title": u["job_title"],
                    "is_staff": u["is_staff"],
                    "last_seen": now - timedelta(minutes=8),
                    "bio": f"{u['job_title']} in {u['department']}.",
                },
            )
            if created:
                user.set_password("Password123!")
                user.save()
            created_users[u["email"]] = user

        admin = created_users["admin@msp.com"]
        alex = created_users["alex.m@msp.com"]
        priya = created_users["priya.r@msp.com"]
        chen = created_users["chen.w@msp.com"]
        jamal = created_users["jamal.k@msp.com"]
        tom = created_users["tom.b@msp.com"]
        john = created_users["viewer.j@msp.com"]
        amina = created_users["viewer.a@msp.com"]

        self.stdout.write(self.style.SUCCESS(f"    ✓ {len(created_users)} users ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 2. TEAMS (FOR SCOPED PERMISSIONS)
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  2. Creating engineering teams…")
        team_workplace, _ = Team.objects.get_or_create(
            name="Modern Workplace & Autopilot",
            defaults={
                "description": "Windows Autopilot, Microsoft Intune, and endpoint provisioning specialists.",
                "lead": alex,
            },
        )
        team_workplace.members.set([admin, alex, jamal, priya])

        team_secops, _ = Team.objects.get_or_create(
            name="SecOps & Identity",
            defaults={
                "description": "Entra ID, Conditional Access, Zero-Trust, and security compliance.",
                "lead": chen,
            },
        )
        team_secops.members.set([admin, chen, alex])

        team_cloud, _ = Team.objects.get_or_create(
            name="Cloud & Messaging Infrastructure",
            defaults={
                "description": "Exchange Online, M365 migrations, Active Directory, and Core Networking.",
                "lead": priya,
            },
        )
        team_cloud.members.set([admin, priya, alex, tom])

        self.stdout.write(self.style.SUCCESS("    ✓ 3 teams ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 3. CATEGORIES & SUBCATEGORIES
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  3. Creating categories…")
        cats_def = [
            ("Microsoft Intune & Autopilot", Category.CategoryType.PROJECT, "#EA580C", "device-phone-mobile", 1),
            ("Cloud Migration Playbooks", Category.CategoryType.PROJECT, "#059669", "cloud-arrow-up", 2),
            ("Identity & Entra ID", Category.CategoryType.SUPPORT, "#2563EB", "shield-check", 3),
            ("Exchange & Email Services", Category.CategoryType.SUPPORT, "#D97706", "mail", 4),
            ("Windows Server & Active Directory", Category.CategoryType.SUPPORT, "#DC2626", "server", 5),
            ("Microsoft 365 & Teams", Category.CategoryType.SUPPORT, "#7C3AED", "cube", 6),
            ("Networking & DNS", Category.CategoryType.SUPPORT, "#0891B2", "globe-alt", 7),
            ("Security & Compliance", Category.CategoryType.PROJECT, "#B91C1C", "lock-closed", 8),
            ("PowerShell Scripting Library", Category.CategoryType.SOFTWARE, "#0D9488", "code-bracket", 9),
            ("General IT Guidelines", Category.CategoryType.GENERAL, "#4B5563", "book-open", 10),
        ]

        cats = {}
        for name, c_type, color, icon, sort in cats_def:
            cat, _ = Category.objects.get_or_create(
                name=name,
                defaults={
                    "category_type": c_type,
                    "color_hex": color,
                    "icon": icon,
                    "sort_order": sort,
                    "description": f"Operational projects and knowledge base for {name}.",
                    "created_by": admin,
                },
            )
            cats[name] = cat

        subcats = [
            ("Exchange Online", cats["Exchange & Email Services"], Category.CategoryType.SUPPORT, "#F59E0B"),
            ("Exchange On-Premises", cats["Exchange & Email Services"], Category.CategoryType.SUPPORT, "#B45309"),
            ("Azure AD Connect", cats["Identity & Entra ID"], Category.CategoryType.SUPPORT, "#1D4ED8"),
        ]
        for name, parent, c_type, color in subcats:
            Category.objects.get_or_create(
                name=name,
                defaults={"category_type": c_type, "color_hex": color, "parent": parent, "created_by": admin},
            )

        self.stdout.write(self.style.SUCCESS(f"    ✓ {len(cats_def) + len(subcats)} categories ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 4. TAGS
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  4. Creating tags…")
        tags_data = [
            ("Autopilot", "#D97706"),
            ("Intune", "#EA580C"),
            ("Entra ID", "#2563EB"),
            ("Hybrid Sync", "#059669"),
            ("MFA", "#D97706"),
            ("Exchange Online", "#EA580C"),
            ("Exchange On-Prem", "#B91C1C"),
            ("PowerShell", "#0D9488"),
            ("Troubleshooting", "#DC2626"),
            ("Security", "#B91C1C"),
            ("Active Directory", "#1D4ED8"),
            ("DNS", "#0891B2"),
            ("LDAP", "#6D28D9"),
            ("Azure", "#0078D4"),
            ("M365", "#7C3AED"),
            ("Teams", "#464EB8"),
            ("SharePoint", "#038387"),
            ("Windows 11", "#0078D4"),
            ("Windows Server", "#00BCF2"),
            ("GPO", "#107C10"),
            ("TLS/SSL", "#D83B01"),
            ("Networking", "#0078D4"),
            ("Monitoring", "#059669"),
            ("Runbook", "#4B5563"),
        ]
        tags = {}
        for name, color in tags_data:
            t, _ = Tag.objects.get_or_create(name=name, defaults={"color_hex": color})
            tags[name] = t

        self.stdout.write(self.style.SUCCESS(f"    ✓ {len(tags)} tags ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 5. ENTERPRISE PROJECTS, MANDATORY DOCUMENTS & ACTION PLAN CHECKLISTS
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  5. Creating projects, mandatory deliverables & checklists…")

        # ── Project 1: Windows Autopilot (100% Document Compliance) ──────────
        proj_autopilot, _ = Project.objects.get_or_create(
            project_code="PRJ-2026-001",
            defaults=dict(
                title="Enterprise Windows Autopilot & Intune Rollout",
                client_or_unit="Corporate HQ & Branch Offices",
                category=cats["Microsoft Intune & Autopilot"],
                summary="Zero-touch Windows 11 endpoint provisioning deployment using Windows Autopilot, Microsoft Intune, and Entra ID.",
                scope_notes=(
                    "In-Scope: Autopilot Hybrid/Entra-Joined profiles, Enrollment Status Page (ESP), Win32 app packaging, BitLocker encryption.\n"
                    "Out-of-Scope: Legacy Windows 7/8 imaging and third-party MDM migration."
                ),
                microsoft_products="Windows Autopilot, Microsoft Intune, Entra ID, Windows 11 Enterprise",
                tech_stack="PowerShell, Microsoft Graph API, Win32 Content Prep Tool",
                prerequisites="M365 E3/Business Premium licensing, Intune MDM authority set, OEM hardware hash ingestion.",
                status=Project.Status.COMPLETED,
                priority=Project.Priority.HIGH,
                start_date=today - timedelta(days=45),
                target_end_date=today - timedelta(days=5),
                completed_at=now - timedelta(days=4),
                project_lead=alex,
                created_by=admin,
                visibility=Project.Visibility.PUBLIC,
                allow_open_collaboration=True,
            ),
        )
        proj_autopilot.tags.set([tags["Autopilot"], tags["Intune"], tags["Windows 11"], tags["Entra ID"], tags["PowerShell"]])
        proj_autopilot.allowed_teams.set([team_workplace])

        ProjectMember.objects.get_or_create(
            project=proj_autopilot, user=alex,
            defaults={"role": ProjectMember.Role.LEAD, "can_upload_docs": True, "can_approve_docs": True, "added_by": admin},
        )
        ProjectMember.objects.get_or_create(
            project=proj_autopilot, user=jamal,
            defaults={"role": ProjectMember.Role.EDITOR, "can_upload_docs": True, "can_approve_docs": False, "added_by": alex},
        )

        # 4 Mandatory Deliverables for Autopilot Project
        autopilot_docs = [
            (
                ProjectDocument.DocumentType.SOW,
                "Windows Autopilot Deployment — Statement of Work (SOW)",
                "Autopilot_Statement_of_Work_v1.txt",
                b"STATEMENT OF WORK (SOW) - PRJ-2026-001\nScope: Zero-Touch Windows 11 Autopilot Deployment.\nOut of Scope: Legacy SCCM OSD Task Sequences.\nTimeline: 6 Weeks.\n",
                ProjectDocument.Status.APPROVED,
                jamal,
                alex,
                "Initial signed SOW defining scope, deliverables, and 6-week timeline.",
            ),
            (
                ProjectDocument.DocumentType.REQUIREMENTS,
                "Windows Autopilot — Technical Requirements Document",
                "Autopilot_Requirements_Document_v1.txt",
                b"REQUIREMENTS DOCUMENT - PRJ-2026-001\n1. Windows 11 Pro/Enterprise 23H2+\n2. TPM 2.0 enabled\n3. Automatic Intune Enrollment enabled\n4. Required Line-of-Business Win32 Apps.\n",
                ProjectDocument.Status.APPROVED,
                jamal,
                alex,
                "Validated technical & licensing prerequisites.",
            ),
            (
                ProjectDocument.DocumentType.AS_BUILT,
                "Windows Autopilot — As-Built Architecture Document",
                "Autopilot_As_Built_v1.txt",
                b"AS-BUILT DOCUMENT - PRJ-2026-001\nDeployment Profile: Corp-Autopilot-EntraJoined\nESP Timeout: 60 mins\nBitLocker: XTS-AES 256-bit\nDynamic Group Rules documented.\n",
                ProjectDocument.Status.APPROVED,
                jamal,
                admin,
                "Final post-implementation configuration and tenant baseline.",
            ),
            (
                ProjectDocument.DocumentType.ADMIN_GUIDE,
                "Windows Autopilot — Operations & Admin Guide",
                "Autopilot_Admin_Guide_v1.txt",
                b"ADMIN GUIDE - PRJ-2026-001\nDay-2 Operations:\n- Harvesting hardware hashes via Get-WindowsAutoPilotInfo\n- Re-assigning Group Tags\n- Troubleshooting ESP timeouts.\n",
                ProjectDocument.Status.APPROVED,
                alex,
                admin,
                "Day-2 administrative procedures and support runbook.",
            ),
        ]
        for doc_type, title, fname, content_bytes, status_val, uploader, reviewer, notes in autopilot_docs:
            if not ProjectDocument.objects.filter(project=proj_autopilot, document_type=doc_type).exists():
                ProjectDocument.objects.create(
                    project=proj_autopilot,
                    document_type=doc_type,
                    title=title,
                    status=status_val,
                    file=ContentFile(content_bytes, name=fname),
                    original_name=fname,
                    file_size_bytes=len(content_bytes),
                    mime_type="text/plain",
                    change_notes=notes,
                    uploaded_by=uploader,
                    reviewed_by=reviewer,
                    reviewed_at=now - timedelta(days=3),
                )

        autopilot_activities = [
            dict(
                step_number=1,
                phase=ProjectActivity.Phase.PRE_IMPLEMENTATION,
                title="Verify M365 Licensing & Intune MDM Authority",
                description="Confirm all target users hold Intune Plan 1 / M365 Business Premium licenses and set MDM User Scope to All or pilot group.",
                code_snippet="Connect-MgGraph -Scopes 'Organization.Read.All'\nGet-MgSubscribedSku | Select-Object SkuPartNumber, ConsumedUnits",
                code_language="powershell",
                expected_outcome="MDM User Scope active and sufficient licenses available.",
                status=ProjectActivity.Status.COMPLETED,
                assigned_to=jamal,
                completed_by=jamal,
                completed_at=now - timedelta(days=35),
                estimated_minutes=20,
            ),
            dict(
                step_number=2,
                phase=ProjectActivity.Phase.IMPLEMENTATION,
                title="Collect & Upload Device Hardware Hashes",
                description="Harvest 4K hardware hashes from pilot devices and upload directly to the Autopilot tenant with Group Tag.",
                code_snippet="Install-Script -Name Get-WindowsAutoPilotInfo -Force\nGet-WindowsAutoPilotInfo -Online -GroupTag 'Corporate-HQ'",
                code_language="powershell",
                expected_outcome="Devices appear under Intune > Devices > Enrollment > Windows Autopilot devices.",
                tip="Use -Online to avoid manual CSV exports when internet connectivity is available during OOBE.",
                status=ProjectActivity.Status.COMPLETED,
                assigned_to=jamal,
                completed_by=jamal,
                completed_at=now - timedelta(days=25),
                estimated_minutes=30,
            ),
            dict(
                step_number=3,
                phase=ProjectActivity.Phase.IMPLEMENTATION,
                title="Configure Autopilot Deployment Profile & ESP",
                description="Create User-Driven Entra ID Joined profile and configure Enrollment Status Page blocking only core security/office apps.",
                code_snippet="(device.devicePhysicalIds -any (_ -eq \"[OrderID]:Corporate-HQ\"))",
                code_language="text",
                warning="Do not assign too many blocking apps in ESP or OOBE provisioning will exceed the 60-minute timeout.",
                expected_outcome="Profile status shows 'Assigned' on all pilot devices.",
                status=ProjectActivity.Status.COMPLETED,
                assigned_to=alex,
                completed_by=alex,
                completed_at=now - timedelta(days=20),
                estimated_minutes=45,
            ),
            dict(
                step_number=4,
                phase=ProjectActivity.Phase.POST_IMPLEMENTATION,
                title="Complete As-Built & Admin Guide Handover",
                description="Finalize As-Built documentation and Admin Guide, upload to repository, and conduct service desk handover.",
                expected_outcome="Both post-implementation documents approved in repository.",
                status=ProjectActivity.Status.COMPLETED,
                assigned_to=alex,
                completed_by=alex,
                completed_at=now - timedelta(days=4),
                estimated_minutes=60,
            ),
        ]
        for act in autopilot_activities:
            ProjectActivity.objects.get_or_create(project=proj_autopilot, step_number=act["step_number"], defaults=act)

        # ── Project 2: Hybrid Exchange Migration (50% Docs - Pre-Imp Ready) ──
        proj_exchange, _ = Project.objects.get_or_create(
            project_code="PRJ-2026-002",
            defaults=dict(
                title="Hybrid Exchange Online Mailbox Migration",
                client_or_unit="Finance & Operations Division",
                category=cats["Cloud Migration Playbooks"],
                summary="Phased migration of 3,500 on-premises Exchange 2019 mailboxes to Exchange Online using MRSProxy with zero mail flow disruption.",
                scope_notes="In-Scope: HCW configuration, pilot wave, Wave 1-3 batches, MX cutover.\nOut-of-Scope: Third-party PST archive ingestion.",
                microsoft_products="Exchange Server 2019, Exchange Online, Microsoft 365",
                tech_stack="PowerShell, Exchange HCW, MRSProxy",
                prerequisites="Valid wildcard TLS certificate, port 443 inbound for MRSProxy, Entra Connect healthy.",
                status=Project.Status.IN_PROGRESS,
                priority=Project.Priority.CRITICAL,
                start_date=today - timedelta(days=14),
                target_end_date=today + timedelta(days=21),
                project_lead=priya,
                created_by=admin,
                visibility=Project.Visibility.PUBLIC,
                allow_open_collaboration=True,
            ),
        )
        proj_exchange.tags.set([tags["Exchange Online"], tags["Exchange On-Prem"], tags["M365"], tags["PowerShell"]])
        proj_exchange.allowed_teams.set([team_cloud])

        ProjectMember.objects.get_or_create(
            project=proj_exchange, user=priya,
            defaults={"role": ProjectMember.Role.LEAD, "can_upload_docs": True, "can_approve_docs": True, "added_by": admin},
        )
        ProjectMember.objects.get_or_create(
            project=proj_exchange, user=alex,
            defaults={"role": ProjectMember.Role.EDITOR, "can_upload_docs": True, "can_approve_docs": False, "added_by": priya},
        )

        if not ProjectDocument.objects.filter(project=proj_exchange, document_type=ProjectDocument.DocumentType.SOW).exists():
            ProjectDocument.objects.create(
                project=proj_exchange,
                document_type=ProjectDocument.DocumentType.SOW,
                title="Exchange Hybrid Migration — Statement of Work",
                status=ProjectDocument.Status.APPROVED,
                file=ContentFile(b"SOW for PRJ-2026-002 Hybrid Exchange Migration.", name="Exchange_Migration_SOW.txt"),
                original_name="Exchange_Migration_SOW.txt",
                file_size_bytes=48,
                mime_type="text/plain",
                change_notes="Approved scope and cutover windows.",
                uploaded_by=priya,
                reviewed_by=admin,
                reviewed_at=now - timedelta(days=12),
            )
        if not ProjectDocument.objects.filter(project=proj_exchange, document_type=ProjectDocument.DocumentType.REQUIREMENTS).exists():
            ProjectDocument.objects.create(
                project=proj_exchange,
                document_type=ProjectDocument.DocumentType.REQUIREMENTS,
                title="Exchange Hybrid Migration — Technical Requirements",
                status=ProjectDocument.Status.APPROVED,
                file=ContentFile(b"Requirements for PRJ-2026-002: TLS 1.2, MRSProxy, OAuth cert.", name="Exchange_Requirements.txt"),
                original_name="Exchange_Requirements.txt",
                file_size_bytes=66,
                mime_type="text/plain",
                change_notes="Confirmed bandwidth and firewall port 443 requirements.",
                uploaded_by=priya,
                reviewed_by=admin,
                reviewed_at=now - timedelta(days=11),
            )

        exchange_activities = [
            dict(
                step_number=1,
                phase=ProjectActivity.Phase.PRE_IMPLEMENTATION,
                title="Enable & Validate MRSProxy Endpoint",
                description="Verify EWS virtual directory has MRSProxyEnabled=$true and test remote move availability.",
                code_snippet="Get-WebServicesVirtualDirectory -Server EXCH01 | Set-WebServicesVirtualDirectory -MRSProxyEnabled $true\nTest-MigrationServerAvailability -ExchangeRemoteMove -RemoteServer 'mail.contoso.com'",
                code_language="powershell",
                warning="Triggers IIS AppPool recycle; execute during maintenance window.",
                status=ProjectActivity.Status.COMPLETED,
                assigned_to=priya,
                completed_by=priya,
                completed_at=now - timedelta(days=10),
                estimated_minutes=25,
            ),
            dict(
                step_number=2,
                phase=ProjectActivity.Phase.IMPLEMENTATION,
                title="Execute Pilot Migration Batch (20 Mailboxes)",
                description="Run pilot batch for IT & non-executive users with AutoComplete enabled and verify Outlook autodiscover.",
                code_snippet="New-MigrationBatch -Name 'Batch_Pilot_01' -SourceEndpoint 'HybridEndpoint' -CSVData $csvData -TargetDeliveryDomain 'contoso.mail.onmicrosoft.com' -AutoStart",
                code_language="powershell",
                status=ProjectActivity.Status.IN_PROGRESS,
                assigned_to=alex,
                due_date=today + timedelta(days=3),
                estimated_minutes=60,
            ),
            dict(
                step_number=3,
                phase=ProjectActivity.Phase.VALIDATION,
                title="Perform DNS MX Cutover & Mail Flow Validation",
                description="Point MX record to Exchange Online Protection after final wave completion and monitor mail queues.",
                status=ProjectActivity.Status.PENDING,
                assigned_to=tom,
                due_date=today + timedelta(days=18),
                estimated_minutes=90,
            ),
        ]
        for act in exchange_activities:
            ProjectActivity.objects.get_or_create(project=proj_exchange, step_number=act["step_number"], defaults=act)

        # ── Project 3: Restricted Team Project (Scoped Permissions Demo) ─────
        proj_zerotrust, _ = Project.objects.get_or_create(
            project_code="PRJ-2026-003",
            defaults=dict(
                title="Zero-Trust Entra ID & Conditional Access Hardening",
                client_or_unit="Information Security & Compliance",
                category=cats["Security & Compliance"],
                summary="Hardening privileged identity governance, phishing-resistant MFA (FIDO2), and token protection policies.",
                scope_notes="Restricted to SecOps & Identity team due to break-glass & CA policy architecture.",
                microsoft_products="Microsoft Entra ID P2, Conditional Access, PIM",
                tech_stack="Graph API, PowerShell, JSON CA Templates",
                status=Project.Status.PRE_IMPLEMENTATION,
                priority=Project.Priority.CRITICAL,
                start_date=today,
                target_end_date=today + timedelta(days=30),
                project_lead=chen,
                created_by=admin,
                visibility=Project.Visibility.TEAM,
                allow_open_collaboration=False,
            ),
        )
        proj_zerotrust.tags.set([tags["Entra ID"], tags["Security"], tags["MFA"]])
        proj_zerotrust.allowed_teams.set([team_secops])
        ProjectMember.objects.get_or_create(
            project=proj_zerotrust, user=chen,
            defaults={"role": ProjectMember.Role.LEAD, "can_upload_docs": True, "can_approve_docs": True, "added_by": admin},
        )
        if not ProjectDocument.objects.filter(project=proj_zerotrust, document_type=ProjectDocument.DocumentType.SOW).exists():
            ProjectDocument.objects.create(
                project=proj_zerotrust,
                document_type=ProjectDocument.DocumentType.SOW,
                title="Zero-Trust Hardening — Statement of Work (Pending Review)",
                status=ProjectDocument.Status.IN_REVIEW,
                file=ContentFile(b"Zero-Trust SOW awaiting Lead/Admin review.", name="ZeroTrust_SOW_Draft.txt"),
                original_name="ZeroTrust_SOW_Draft.txt",
                file_size_bytes=42,
                mime_type="text/plain",
                change_notes="Submitted for security architecture review.",
                uploaded_by=chen,
            )

        self.stdout.write(self.style.SUCCESS("    ✓ Projects, mandatory deliverables & checklists ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 6. SUPPORT RESOLUTIONS, RUNBOOKS & KNOWLEDGE ARTICLES
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  6. Creating support resolutions & knowledge articles…")

        # ── A1: Support — Windows Autopilot Error 0x80180014 (Linked to Project!) ──
        a_autopilot_err, _ = Article.objects.get_or_create(
            title="Windows Autopilot Enrollment Error 0x80180014 (MDM Enrollment Disabled)",
            defaults=dict(
                article_type=Article.ArticleType.SUPPORT,
                category=cats["Microsoft Intune & Autopilot"],
                related_project=proj_autopilot,
                author=jamal,
                reviewed_by=alex,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.HIGH,
                affected_systems="Windows 11 OOBE, Microsoft Intune Enrollment",
                error_codes="0x80180014, ZTDDeviceNotFound",
                microsoft_products="Windows Autopilot, Microsoft Intune, Entra ID",
                resolution_type="MDM Scope Policy & Device Limit Adjustment",
                time_to_resolve_minutes=20,
                summary="Quick resolution for Autopilot enrollment failing during OOBE with error code 0x80180014.",
                symptoms="Device fails at 'Securing your hardware' or 'Registering your device for mobile management' with error 0x80180014.",
                root_cause="User lacks an Intune license, MDM user scope is set to None, or the user hit the maximum Intune device enrollment limit (default 5).",
                verification_steps="Re-run Autopilot OOBE or run dsregcmd /status and confirm MDMUrl and AzureAdJoined show YES.",
                search_keywords="0x80180014, Autopilot enrollment failed, MDM disabled, device cap",
                content="Follow the diagnostic steps below to verify Intune licensing, MDM enrollment scope, and device enrollment limits.",
                is_featured=True,
                is_verified=True,
                is_pinned=True,
                published_at=now - timedelta(days=2),
                views_count=92,
            ),
        )
        a_autopilot_err.tags.set([tags["Autopilot"], tags["Intune"], tags["Troubleshooting"], tags["Windows 11"]])
        a_autopilot_err.contributors.set([alex])

        for s in [
            dict(
                step_number=1,
                title="Verify User Intune License & MDM Scope",
                description="Ensure the enrolling user holds an active Microsoft Intune Plan 1 license and is included in Entra ID > Mobility (MDM and WIP) > Microsoft Intune > MDM User Scope.",
                code_snippet="Get-MgUserLicenseDetail -UserId 'user@contoso.com' | Select-Object SkuPartNumber",
                code_language="powershell",
                estimated_minutes=5,
            ),
            dict(
                step_number=2,
                title="Check Device Limit Restrictions & Windows Enrollment Block",
                description="In Intune Admin Center > Devices > Enrollment > Device platform restrictions, confirm Windows MDM is set to Allow and check if the user exceeded their 5-device cap.",
                code_snippet="Get-MgUserOwnedDevice -UserId 'user@contoso.com' | Measure-Object",
                code_language="powershell",
                tip="Remove stale test VMs from Entra ID / Intune before retrying OOBE.",
                estimated_minutes=10,
            ),
        ]:
            ResolutionStep.objects.get_or_create(article=a_autopilot_err, step_number=s["step_number"], defaults=s)

        # ── A2: Support — Entra ID Sync Conflict ─────────────────────────────
        a1, _ = Article.objects.get_or_create(
            title="Resolving Entra ID Sync Failure: Duplicate UserPrincipalName Conflict",
            defaults=dict(
                article_type=Article.ArticleType.SUPPORT,
                category=cats["Identity & Entra ID"],
                author=alex,
                reviewed_by=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.HIGH,
                affected_systems="Entra Connect Sync / On-Prem AD DS",
                error_codes="AttributeValueMustBeUnique / FaultCode 8344",
                microsoft_products="Microsoft Entra ID, Entra Connect, Windows Server 2022 AD DS",
                resolution_type="ImmutableId Soft-Match Alignment",
                time_to_resolve_minutes=45,
                summary="Diagnostic walkthrough for resolving duplicate UPN collisions blocking delta sync cycles in Microsoft Entra Connect.",
                symptoms="Entra Connect shows AttributeValueMustBeUnique and Event ID 6111; affected user cannot access M365.",
                root_cause="A cloud-only shadow object holds the same UPN/SMTP proxy address as an on-premises AD user.",
                verification_steps="Run Start-ADSyncSyncCycle -PolicyType Delta and confirm zero export errors in Synchronization Service Manager.",
                search_keywords="Entra sync error, UPN conflict, Azure AD Connect, delta sync, AttributeValueMustBeUnique",
                content="Use Microsoft Graph PowerShell to stamp the Base64 ObjectGUID onto OnPremisesImmutableId to trigger a soft-match.",
                is_featured=True,
                is_verified=True,
                published_at=now - timedelta(days=5),
                views_count=84,
            ),
        )
        a1.tags.set([tags["Entra ID"], tags["Hybrid Sync"], tags["Active Directory"], tags["Troubleshooting"], tags["PowerShell"]])
        a1.contributors.set([priya])

        ResolutionStep.objects.get_or_create(
            article=a1, step_number=1,
            defaults=dict(
                title="Soft-Match On-Prem ObjectGUID to Cloud User",
                description="Convert on-premises ObjectGUID to Base64 ImmutableId and update the conflicting cloud user.",
                code_snippet="$onPrem = Get-ADUser -Identity 'jdoe' -Properties ObjectGUID\n$immutableId = [System.Convert]::ToBase64String($onPrem.ObjectGUID.ToByteArray())\nUpdate-MgUser -UserId '<cloud-guid>' -OnPremisesImmutableId $immutableId\nStart-ADSyncSyncCycle -PolicyType Delta",
                code_language="powershell",
                estimated_minutes=15,
            ),
        )

        # ── A3: Support — Exchange Admin Center 403 ──────────────────────────
        a2, _ = Article.objects.get_or_create(
            title="Cannot Access Exchange Admin Center (EAC) — HTTP 403 / Redirect Loop",
            defaults=dict(
                article_type=Article.ArticleType.SUPPORT,
                category=cats["Exchange & Email Services"],
                related_project=proj_exchange,
                author=priya,
                reviewed_by=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.HIGH,
                affected_systems="Exchange Online Admin Center / Entra Conditional Access",
                error_codes="HTTP 403 Forbidden, AADSTS50076",
                microsoft_products="Exchange Online, Microsoft Entra ID, Conditional Access",
                resolution_type="Conditional Access Policy Scope & RBAC Verification",
                time_to_resolve_minutes=20,
                summary="Remediation for administrators blocked from EAC due to Conditional Access device compliance or missing RBAC assignment.",
                symptoms="403 Forbidden or infinite sign-in redirect loop on admin.exchange.microsoft.com.",
                root_cause="CA policy requires compliant device for All Cloud Apps or admin lacks Organization Management RBAC role.",
                verification_steps="Sign into admin.exchange.microsoft.com in an InPrivate session and verify mailboxes load.",
                search_keywords="EAC access denied, exchange admin center 403, conditional access EAC",
                content="Check Entra Sign-In logs for CA policy failures and verify Exchange RBAC role membership.",
                is_featured=True,
                is_verified=True,
                published_at=now - timedelta(days=12),
                views_count=143,
            ),
        )
        a2.tags.set([tags["Exchange Online"], tags["Entra ID"], tags["MFA"], tags["Troubleshooting"], tags["M365"]])

        # ── A4: Support — DNS Failure After DC Decommission ──────────────────
        a3, _ = Article.objects.get_or_create(
            title="DNS Resolution Failures Across Site After Domain Controller Decommission",
            defaults=dict(
                article_type=Article.ArticleType.SUPPORT,
                category=cats["Networking & DNS"],
                author=tom,
                reviewed_by=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.CRITICAL,
                affected_systems="Windows Server DNS, Active Directory Replication",
                error_codes="DNS Event 4015, Event 4007, LDAP 81",
                microsoft_products="Windows Server 2022, Active Directory DNS",
                resolution_type="Stale NS & _msdcs SRV Record Cleanup",
                time_to_resolve_minutes=90,
                summary="Remediation for site-wide DNS failures caused by stale NS records and forwarders pointing to a retired DC.",
                symptoms="Slow logons, intermittent internal DNS timeouts, repadmin failures.",
                root_cause="Decommissioned DC left orphaned NS/SRV records in forward lookup zones and _msdcs.",
                verification_steps="Run dcdiag /test:dns /v and confirm 0 failures.",
                search_keywords="DNS failure decommission, stale NS record, Event 4015",
                content="Enumerate and remove stale NS records, conditional forwarders, and flush DNS server caches across remaining DCs.",
                is_verified=True,
                published_at=now - timedelta(days=3),
                views_count=56,
            ),
        )
        a3.tags.set([tags["DNS"], tags["Active Directory"], tags["Windows Server"], tags["Troubleshooting"]])
        a3.contributors.set([alex, jamal])

        # ── A5: Software — PowerShell Health Check Script ─────────────────────
        a7, _ = Article.objects.get_or_create(
            title="Enterprise PowerShell Module: Automated Windows Server & AD Health Check",
            defaults=dict(
                article_type=Article.ArticleType.SOFTWARE,
                category=cats["PowerShell Scripting Library"],
                author=chen,
                reviewed_by=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.NA,
                tech_stack="PowerShell 7, Microsoft Graph API, Windows Server",
                difficulty_level=Article.DifficultyLevel.INTERMEDIATE,
                estimated_duration="30 minutes",
                prerequisites="App Registration in Entra ID with Mail.Send and certificate authentication.",
                summary="Automated health-check script delivering daily Windows Server & AD HTML reports via Graph API.",
                search_keywords="PowerShell health check, AD health script, graph API sendmail",
                content="Schedule Invoke-ServerHealthCheck via Task Scheduler or Azure Automation using certificate-based Graph authentication.",
                is_featured=True,
                is_verified=True,
                published_at=now - timedelta(days=30),
                views_count=211,
            ),
        )
        a7.tags.set([tags["PowerShell"], tags["Windows Server"], tags["Active Directory"], tags["Monitoring"]])
        a7.contributors.set([alex, priya])

        # ── A6: Runbook — Client Onboarding Discovery Checklist ──────────────
        a10, _ = Article.objects.get_or_create(
            title="New Client Onboarding: Infrastructure Discovery Runbook",
            defaults=dict(
                article_type=Article.ArticleType.RUNBOOK,
                category=cats["General IT Guidelines"],
                author=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.NA,
                summary="Standard discovery runbook feeding directly into the project Statement of Work (SOW) and Requirements Document.",
                search_keywords="new client onboarding, discovery runbook, SOW input, requirements audit",
                content="Complete Identity, Email, Infrastructure, and Security Posture audits within 5 business days before drafting the SOW.",
                is_pinned=True,
                is_verified=True,
                published_at=now - timedelta(days=60),
                views_count=312,
            ),
        )
        a10.tags.set([tags["Active Directory"], tags["M365"], tags["Networking"], tags["Security"], tags["Runbook"]])

        # ── A7: Restricted / In-Review Articles ──────────────────────────────
        a11, _ = Article.objects.get_or_create(
            title="Break-Glass Account & Emergency Access Recovery Procedure",
            defaults=dict(
                article_type=Article.ArticleType.RUNBOOK,
                category=cats["Security & Compliance"],
                related_project=proj_zerotrust,
                author=chen,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.RESTRICTED,
                severity=Article.Severity.CRITICAL,
                summary="Restricted emergency recovery procedure for Entra ID Global Administrator break-glass accounts.",
                content="Restricted to Senior / Lead Engineers and Administrators.",
                is_verified=True,
                published_at=now - timedelta(days=7),
                views_count=19,
            ),
        )
        a11.tags.set([tags["Security"], tags["Entra ID"], tags["Runbook"]])

        a12, _ = Article.objects.get_or_create(
            title="TLS 1.0/1.1 Deprecation: Registry Key Remediation for .NET and Schannel",
            defaults=dict(
                article_type=Article.ArticleType.SUPPORT,
                category=cats["Security & Compliance"],
                author=chen,
                status=Article.Status.IN_REVIEW,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.HIGH,
                error_codes="SEC_E_ALGORITHM_MISMATCH, 0x80090326",
                summary="Registry steps to disable legacy TLS 1.0/1.1 and enforce TLS 1.2+ across IIS and .NET.",
                content="Pending Lead Engineer review before publishing.",
                needs_review=True,
                views_count=8,
            ),
        )
        a12.tags.set([tags["TLS/SSL"], tags["Security"], tags["Windows Server"]])

        a_autopilot_err.related_articles.add(a1)
        a1.related_articles.add(a2)

        # Revision snapshot example on a1
        ArticleRevision.objects.get_or_create(
            article=a1,
            version=1,
            defaults={
                "title": a1.title,
                "summary": "Initial version before adding Graph PowerShell cmdlets.",
                "content": "Initial draft using legacy MSOnline cmdlets.",
                "change_summary": "Migrated cmdlets from MSOnline to Microsoft Graph PowerShell.",
                "edited_by": priya,
            },
        )

        self.stdout.write(self.style.SUCCESS("    ✓ Support resolutions & knowledge articles ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 7. ATTACHMENTS (ON ARTICLES, PROJECTS & ACTIVITIES)
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  7. Creating attachments…")
        attachments_data = [
            (a_autopilot_err, None, None, Attachment.AttachmentKind.SCRIPT, "Check-AutopilotStatus.ps1", b"# Autopilot diagnostics\ndsregcmd /status\n", jamal, "Diagnostic PowerShell helper"),
            (a1, None, None, Attachment.AttachmentKind.DOCUMENT, "Entra_Sync_Runbook.txt", b"Entra Connect soft-match reference.", alex, "Quick reference card"),
            (None, proj_autopilot, None, Attachment.AttachmentKind.SCRIPT, "Harvest-AutopilotHashes.ps1", b"Get-WindowsAutoPilotInfo -Online -GroupTag 'Corporate-HQ'\n", jamal, "Hash collection script"),
            (None, proj_exchange, None, Attachment.AttachmentKind.DOCUMENT, "Pilot_Batch_Template.csv", b"EmailAddress\nvip.user1@contoso.com\n", priya, "Migration batch CSV template"),
        ]
        att_count = 0
        for art, proj, act, kind, fname, payload, uploader, desc in attachments_data:
            if not Attachment.objects.filter(original_name=fname).exists():
                Attachment.objects.create(
                    article=art,
                    project=proj,
                    activity=act,
                    attachment_kind=kind,
                    file=ContentFile(payload, name=fname),
                    original_name=fname,
                    file_size_bytes=len(payload),
                    file_type="text/plain",
                    uploaded_by=uploader,
                    description=desc,
                )
                att_count += 1

        self.stdout.write(self.style.SUCCESS(f"    ✓ {att_count} attachments ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 8. COMMENTS, FEEDBACK, BOOKMARKS & TELEMETRY
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  8. Creating comments, feedback, bookmarks & logs…")

        c1, _ = Comment.objects.get_or_create(
            article=a_autopilot_err,
            author=alex,
            content="Also verify the user hasn't hit the Entra ID device join quota (default 50). Cleaning up stale devices fixes this immediately.",
            defaults={"is_approved": True, "is_resolution_note": True, "is_pinned": True},
        )
        Comment.objects.get_or_create(
            article=a_autopilot_err,
            author=jamal,
            parent=c1,
            content="Good point — added that check to the verification steps.",
            defaults={"is_approved": True},
        )
        Comment.objects.get_or_create(
            project=proj_exchange,
            author=priya,
            content="Pilot batch kicked off at 09:00 UTC. Monitoring MRSProxy throughput.",
            defaults={"is_approved": True, "is_resolution_note": True},
        )

        feedback_data = [
            (a_autopilot_err, alex, True, "Resolved a live Autopilot enrollment block in 10 minutes."),
            (a_autopilot_err, john, True, "Very clear error code lookup."),
            (a1, jamal, True, "ImmutableId soft-match command worked cleanly."),
            (a2, alex, True, "CA exclusion solved the EAC redirect loop."),
            (a7, chen, True, "Running across production tenants."),
        ]
        for art, user, helpful, text in feedback_data:
            ArticleFeedback.objects.get_or_create(
                article=art, user=user, defaults={"is_helpful": helpful, "feedback_text": text}
            )

        for art in [a_autopilot_err, a1, a2, a3, a7, a10]:
            Article.objects.filter(pk=art.pk).update(
                helpful_votes=ArticleFeedback.objects.filter(article=art, is_helpful=True).count(),
                not_helpful_votes=ArticleFeedback.objects.filter(article=art, is_helpful=False).count(),
            )

        Bookmark.objects.get_or_create(user=jamal, project=proj_autopilot)
        Bookmark.objects.get_or_create(user=jamal, article=a_autopilot_err)
        Bookmark.objects.get_or_create(user=alex, project=proj_exchange)

        for query, user, count in [
            ("Windows Autopilot 0x80180014", jamal, 2),
            ("Entra ID UPN conflict", alex, 1),
            ("Exchange SOW", priya, 1),
            ("As-Built Autopilot", admin, 1),
        ]:
            SearchLog.objects.create(query=query, user=user, results_count=count, ip_address="192.168.1.100")

        Notification.objects.get_or_create(
            user=admin,
            title="SOW awaiting review on PRJ-2026-003",
            defaults={
                "notification_type": Notification.NotificationType.REVIEW_REQUEST,
                "message": f"{chen.full_name} uploaded ZeroTrust_SOW_Draft.txt for review.",
                "project": proj_zerotrust,
            },
        )
        Notification.objects.get_or_create(
            user=alex,
            title="Article awaiting review",
            defaults={
                "notification_type": Notification.NotificationType.REVIEW_REQUEST,
                "message": f"{chen.full_name} submitted '{a12.title}' for review.",
                "article": a12,
            },
        )

        AuditLog.objects.create(
            actor=admin,
            action=AuditLog.Action.PROJECT_CREATED,
            target_type="Project",
            target_id=str(proj_autopilot.pk),
            target_repr=str(proj_autopilot),
            details={"seeded": True},
            ip_address="127.0.0.1",
        )

        # Recalculate tag usage counts across both articles and projects
        for tag in Tag.objects.all():
            total_usage = tag.articles.count() + tag.projects.count()
            Tag.objects.filter(pk=tag.pk).update(usage_count=total_usage)

        self.stdout.write("\n" + self.style.MIGRATE_HEADING("━━━  Seeding Complete  ━━━"))
        self.stdout.write(
            self.style.SUCCESS(
                f"\n  Users:             {User.objects.filter(is_superuser=False).count()}"
                f"\n  Teams:             {Team.objects.count()}"
                f"\n  Projects:          {Project.objects.count()}"
                f"\n  Project Documents: {ProjectDocument.objects.count()}"
                f"\n  Project Activities:{ProjectActivity.objects.count()}"
                f"\n  Articles:          {Article.objects.count()}"
                f"\n  Resolution Steps:  {ResolutionStep.objects.count()}"
                f"\n  Attachments:       {Attachment.objects.count()}"
                f"\n  Comments:          {Comment.objects.count()}"
            )
        )
        self.stdout.write(
            self.style.NOTICE(
                "\n  Login credentials (Password123! for all seeded accounts):"
                "\n    admin@msp.com      (Administrator)"
                "\n    alex.m@msp.com     (Lead Engineer)"
                "\n    priya.r@msp.com    (Lead Engineer)"
                "\n    chen.w@msp.com     (Engineer)"
                "\n    jamal.k@msp.com    (Engineer)"
                "\n    tom.b@msp.com      (Engineer)"
                "\n    viewer.j@msp.com   (Viewer - Read Only)"
                "\n    viewer.a@msp.com   (Viewer - Read Only)\n"
            )
        )