from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from projectRepo.models import (
    Article,
    ArticleFeedback,
    ArticleView,
    Attachment,
    Category,
    Comment,
    Notification,
    ProjectStep,
    SearchLog,
    Tag,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds the database with comprehensive enterprise MSP knowledge base sample data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Deletes all non-superuser knowledge base data before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("━━━  MSP Knowledge Base — Seeding Routine  ━━━"))

        if options["flush"]:
            self.stdout.write(self.style.WARNING("  Flushing existing data…"))
            ArticleView.objects.all().delete()
            ArticleFeedback.objects.all().delete()
            Comment.objects.all().delete()
            Attachment.objects.all().delete()
            ProjectStep.objects.all().delete()
            Notification.objects.all().delete()
            SearchLog.objects.all().delete()
            Article.objects.all().delete()
            Category.objects.all().delete()
            Tag.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

        # ──────────────────────────────────────────────────────────────────────
        # 1. USERS
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
                role=User.Role.ENGINEER,
                department="Infrastructure Engineering",
                job_title="Senior Cloud Engineer",
                is_staff=False,
            ),
            dict(
                email="chen.w@msp.com",
                first_name="Chen",
                last_name="Wei",
                role=User.Role.ENGINEER,
                department="DevOps & Security",
                job_title="SecOps Automation Lead",
                is_staff=False,
            ),
            dict(
                email="jamal.k@msp.com",
                first_name="Jamal",
                last_name="Khan",
                role=User.Role.ENGINEER,
                department="End User Computing",
                job_title="Tier 3 Escalations Specialist",
                is_staff=False,
            ),
            dict(
                email="priya.r@msp.com",
                first_name="Priya",
                last_name="Ramesh",
                role=User.Role.ENGINEER,
                department="Microsoft 365 Practice",
                job_title="Exchange & M365 Consultant",
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
                department="Helpdesk Support",
                job_title="Tier 1 Analyst",
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
                    "last_seen": timezone.now() - timedelta(minutes=10),
                    "bio": f"{u['job_title']} in the {u['department']} team.",
                },
            )
            if created:
                user.set_password("Password123!")
                user.save()
            created_users[u["email"]] = user

        admin = created_users["admin@msp.com"]
        alex = created_users["alex.m@msp.com"]
        chen = created_users["chen.w@msp.com"]
        jamal = created_users["jamal.k@msp.com"]
        priya = created_users["priya.r@msp.com"]
        tom = created_users["tom.b@msp.com"]
        john = created_users["viewer.j@msp.com"]
        amina = created_users["viewer.a@msp.com"]

        self.stdout.write(self.style.SUCCESS(f"    ✓ {len(created_users)} users ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 2. CATEGORIES
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  2. Creating categories…")
        cats_def = [
            # (name, type, color, icon, sort_order)
            ("Identity & Entra ID", Category.CategoryType.SUPPORT, "#2563EB", "shield-check", 1),
            ("Exchange & Email Services", Category.CategoryType.SUPPORT, "#D97706", "mail", 2),
            ("Windows Server & Active Directory", Category.CategoryType.SUPPORT, "#DC2626", "server", 3),
            ("Microsoft 365 & Teams", Category.CategoryType.SUPPORT, "#7C3AED", "cube", 4),
            ("Networking & DNS", Category.CategoryType.SUPPORT, "#0891B2", "globe-alt", 5),
            ("Cloud Migration Playbooks", Category.CategoryType.PROJECT, "#059669", "cloud-arrow-up", 6),
            ("Microsoft Intune & Autopilot", Category.CategoryType.PROJECT, "#EA580C", "device-phone-mobile", 7),
            ("DevOps & CI/CD Pipelines", Category.CategoryType.PROJECT, "#6D28D9", "command-line", 8),
            ("Security & Compliance", Category.CategoryType.PROJECT, "#B91C1C", "lock-closed", 9),
            ("PowerShell Scripting Library", Category.CategoryType.SOFTWARE, "#0D9488", "code-bracket", 10),
            ("General IT Guidelines", Category.CategoryType.GENERAL, "#4B5563", "book-open", 11),
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
                    "description": f"Operational knowledge base for {name}.",
                    "created_by": admin,
                },
            )
            cats[name] = cat

        # Sub-categories
        SubCats = [
            ("Exchange Online", cats["Exchange & Email Services"], Category.CategoryType.SUPPORT, "#F59E0B"),
            ("Exchange On-Premises", cats["Exchange & Email Services"], Category.CategoryType.SUPPORT, "#B45309"),
            ("Azure AD Connect", cats["Identity & Entra ID"], Category.CategoryType.SUPPORT, "#1D4ED8"),
        ]
        for name, parent, c_type, color in SubCats:
            Category.objects.get_or_create(
                name=name,
                defaults={"category_type": c_type, "color_hex": color, "parent": parent, "created_by": admin},
            )

        self.stdout.write(self.style.SUCCESS(f"    ✓ {len(cats_def) + len(SubCats)} categories ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 3. TAGS
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  3. Creating tags…")
        tags_data = [
            ("Entra ID", "#2563EB"),
            ("OAuth2.0", "#7C3AED"),
            ("MFA", "#D97706"),
            ("Hybrid Sync", "#059669"),
            ("Exchange Online", "#EA580C"),
            ("Exchange On-Prem", "#B91C1C"),
            ("PowerShell", "#0D9488"),
            ("Terraform", "#7C3AED"),
            ("Kubernetes", "#2563EB"),
            ("Troubleshooting", "#DC2626"),
            ("Security", "#B91C1C"),
            ("Active Directory", "#1D4ED8"),
            ("DNS", "#0891B2"),
            ("LDAP", "#6D28D9"),
            ("Intune", "#EA580C"),
            ("Autopilot", "#D97706"),
            ("Azure", "#0078D4"),
            ("M365", "#7C3AED"),
            ("Teams", "#464EB8"),
            ("SharePoint", "#038387"),
            ("Windows Server", "#00BCF2"),
            ("GPO", "#107C10"),
            ("Certificate", "#FFB900"),
            ("TLS/SSL", "#D83B01"),
            ("Networking", "#0078D4"),
            ("Firewall", "#B91C1C"),
            ("Monitoring", "#059669"),
            ("Patch Management", "#6D28D9"),
            ("Runbook", "#4B5563"),
            ("Python", "#3B7EBB"),
        ]
        tags = {}
        for name, color in tags_data:
            t, _ = Tag.objects.get_or_create(name=name, defaults={"color_hex": color})
            tags[name] = t

        self.stdout.write(self.style.SUCCESS(f"    ✓ {len(tags)} tags ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 4. ARTICLES
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  4. Creating articles…")
        now = timezone.now()

        # ── A1: Support — Entra ID Sync Conflict ─────────────────────────────
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
                affected_systems="Entra Connect Cloud Sync / On-Prem AD DS",
                error_codes="AttributeValueMustBeUnique / FaultCode 8344",
                microsoft_products="Microsoft Entra ID, Entra Connect, Windows Server 2022 AD DS",
                resolution_type="Attribute Soft-Match Alignment / UPN Cleansing",
                time_to_resolve_minutes=45,
                summary="Diagnostic walkthrough for resolving duplicate UPN collisions that block delta synchronisation cycles in Microsoft Entra ID Connect.",
                search_keywords="Entra sync error, UPN conflict, Azure AD Connect, delta sync, AttributeValueMustBeUnique, directory synchronisation",
                content=r"""
During execution of the identity synchronisation cycle via Microsoft Entra Connect, a critical processing block
occurs due to a collision on the UserPrincipalName (UPN) attribute mapping. This article documents
the full diagnostic and remediation path.

Symptoms

  Entra Connect Synchronisation Service shows status stopped-server-down or stopped-extension-dll-exception.

  Azure AD Sync errors portal displays: AttributeValueMustBeUnique for affected objects.

  Event ID 6111 in the Synchronisation Service Manager Application log.

  Affected user cannot sign into Microsoft 365 services despite on-premise account being active.
Root Cause
The Entra Connect delta sync engine cross-references SMTP proxy addresses and UPN nodes during each cycle.
If a target UPN string is already bound to a conflicting cloud object ID — typically from a legacy migration
or an administrator manually creating a cloud account — the engine flags the transaction as non-routable and
suspends the affected connector run profile.

Diagnostic Steps

  Open Synchronization Service Manager → Operations → identify the failed run profile step.

  Note the CS Object ID of the offending connector space object.

  Run the following PowerShell to identify duplicate UPN objects in the cloud tenant:
Connect-MgGraph -Scopes "User.Read.All"
$upn = "conflicted.user@contoso.com"
Get-MgUser -Filter "userPrincipalName eq '$upn'" | Select-Object Id, DisplayName, UserPrincipalName, OnPremisesSyncEnabled

  Confirm whether a cloud-only shadow account exists for the conflicting UPN.

  If the cloud object has no on-prem equivalent, perform a soft-match using the ImmutableId:
# Get the on-prem ObjectGUID and convert to ImmutableId
$onPremUser = Get-ADUser -Identity "conflicted.user" -Properties ObjectGUID
$immutableId = [System.Convert]::ToBase64String($onPremUser.ObjectGUID.ToByteArray())

# Stamp the ImmutableId on the cloud object to trigger soft-match
Update-MgUser -UserId "cloud-object-guid-here" -OnPremisesImmutableId $immutableId
Resolution

  After stamping the ImmutableId, run a delta sync manually to validate the merge:
Start-ADSyncSyncCycle -PolicyType Delta

  Monitor the Sync Service Manager → Operations for the next delta run. Confirm the object transitions from staged to exported.

  Verify the user can authenticate at https://myapps.microsoft.com.
Prevention

Always provision cloud accounts exclusively via on-premises AD when Entra Connect is deployed in the environment. Direct cloud provisioning of accounts that exist on-prem will always result in UPN collision during the next sync cycle.
Configure a scoped Entra Connect filtering rule to exclude any OU used for cloud-only service accounts from the sync scope to prevent future cross-contamination.
""",
                is_featured=True,
                is_verified=True,
                needs_review=False,
                published_at=now - timedelta(days=5),
                views_count=84,
                helpful_votes=23,
                not_helpful_votes=2,
            ),
        )
        a1.tags.set([tags["Entra ID"], tags["Hybrid Sync"], tags["Active Directory"], tags["Troubleshooting"], tags["PowerShell"]])
        a1.contributors.set([priya])

        # ── A2: Support — Exchange Online Cannot Open EAC ─────────────────────
        a2, _ = Article.objects.get_or_create(
            title="Cannot Access Exchange Admin Center (EAC) — HTTP 403 / Redirect Loop",
            defaults=dict(
                article_type=Article.ArticleType.SUPPORT,
                category=cats["Exchange & Email Services"],
                author=priya,
                reviewed_by=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.HIGH,
                affected_systems="Exchange Online Admin Center / Microsoft 365 Admin Portal",
                error_codes="HTTP 403 Forbidden, AADSTS50076, CAP_BLOCK_ACCESS",
                microsoft_products="Exchange Online, Microsoft Entra ID, Conditional Access",
                resolution_type="Conditional Access Policy Scope Exclusion",
                time_to_resolve_minutes=20,
                summary="Step-by-step remediation for administrators blocked from accessing the Exchange Admin Center due to Conditional Access policy conflicts.",
                search_keywords="EAC access denied, exchange admin center 403, cannot open EAC, admin blocked exchange, conditional access EAC",
                content=r"""
Administrators intermittently receive a 403 Forbidden error or are redirected in a continuous
loop when attempting to access the Exchange Admin Center at https://admin.exchange.microsoft.com.
Affected Scenarios

  Recently tightened Conditional Access (CA) policies scoped to All Cloud Apps now blocking admin portals.

  Admin account does not have a compliant device but CA requires device compliance for all apps.

  Admin account is excluded from MFA CA policy but included in a separate block policy.

  New Break-Glass admin account never seeded with the required RBAC role assignment in Exchange Online.
Diagnostic Checklist

  Confirm the affected user holds the Exchange Administrator or Global Administrator Entra role.

  Review Entra Sign-In logs for the user and filter for the EXO Admin Center app. Check the CA applied policies column.

  Identify which CA policy is producing a Failure result.
# Check Exchange RBAC role assignment via PowerShell
Connect-ExchangeOnline -UserPrincipalName admin@contoso.com
Get-RoleGroupMember -Identity "Organization Management" | Where-Object {$_.Name -like "*affected.admin*"}
Resolution — Conditional Access

  Navigate to Entra Admin Center → Protection → Conditional Access → Policies.

  Identify the policy causing the block (usually a Require Compliant Device or Require MFA from trusted location policy).

  Under Users → Exclude, add the affected administrator account or the Directory Role: Exchange Administrator.

  Alternatively, scope the CA policy to exclude the Microsoft Exchange Online PowerShell app ID: fb78d390-0c51-40cd-8e17-fdbfab77341b.

⚠ Do not permanently exclude Break-Glass accounts from all CA policies. Scope the exclusion to the minimum required and review quarterly.
Resolution — Missing RBAC Role
# Assign the Exchange Administrator role via M365 PowerShell
Add-RoleGroupMember -Identity "Organization Management" -Member "affected.admin@contoso.com"

# Confirm assignment took effect
Get-RoleGroupMember -Identity "Organization Management"
Allow up to 15 minutes for role propagation before testing access again.
""",
                is_featured=True,
                is_verified=True,
                published_at=now - timedelta(days=12),
                views_count=143,
                helpful_votes=38,
                not_helpful_votes=3,
            ),
        )
        a2.tags.set([tags["Exchange Online"], tags["Entra ID"], tags["MFA"], tags["Troubleshooting"], tags["M365"]])

        # ── A3: Support — DNS Resolution Failure After DC Decommission ────────
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
                affected_systems="Windows Server DNS, Active Directory Replication, All Domain-Joined Clients",
                error_codes="DNS Event 4015, Event 4007, LDAP 81",
                microsoft_products="Windows Server 2022, Active Directory DNS, AD DS",
                resolution_type="Stale NS Record Removal / Conditional Forwarder Cleanup",
                time_to_resolve_minutes=90,
                summary="Remediation guide for enterprise-wide DNS failures caused by stale NS records and forwarder references pointing to a decommissioned Domain Controller.",
                search_keywords="DNS failure after decommission, stale NS record, DC decommission DNS, Event 4015, DNS delegation broken",
                content=r"""
Following the decommission of a Domain Controller, intermittent to complete DNS resolution failures begin
affecting all domain-joined clients and server workloads. This is caused by stale NS (Name Server) records and
conditional forwarder entries that still reference the decommissioned server's IP address.

Impact Scope

  Clients intermittently fail to resolve internal and external hostnames.

  AD replication may begin to show errors as DCs cannot locate each other via DNS.

  Logon times increase significantly or interactive logons fail with no logon servers available.
Identification
# List all NS records for the zone — look for records pointing to the old DC's IP
dnscmd /enumrecords contoso.com @ /type NS

# Check conditional forwarders for references to the decommissioned DC
Get-DnsServerForwarder | Select-Object IPAddress

# Check replication status
repadmin /showrepl * /csv > C:\Logs\repl_report.csv
Remediation Steps

  Identify stale NS records pointing to the decommissioned DC across all DNS zones (forward + reverse).

  Remove stale NS records from each affected DNS zone:
# Remove the stale NS record
Remove-DnsServerResourceRecord -ZoneName "contoso.com" -RRType "NS" -Name "@" -RecordData "old-dc.contoso.com." -Force

# Confirm removal
dnscmd /enumrecords contoso.com @ /type NS

  Remove stale conditional forwarders referencing the decommissioned DC's IP:
Remove-DnsServerConditionalForwarderZone -Name "partner.contoso.com" -Force

  Update Root Hints if the old DC was referenced there (rare but possible):
Get-DnsServerRootHint | Where-Object {$_.NameServer -like "*old-dc*"} | Remove-DnsServerRootHint -Force

  Force DNS cache flush across all remaining Domain Controllers:
Clear-DnsServerCache -Force -ComputerName (Get-ADDomainController -Filter *).HostName

  Validate resolution has restored on a sample of clients:
Resolve-DnsName "contoso.com" -Type NS | Select-Object NameHost
nslookup contoso.com
Post-Remediation Validation
Run dcdiag /test:dns /v on all remaining DCs and confirm zero failures in the DNS delegation section.
Log results to the incident ticket as evidence of closure.
""",
                is_featured=False,
                is_verified=True,
                is_pinned=False,
                published_at=now - timedelta(days=3),
                views_count=56,
                helpful_votes=19,
                not_helpful_votes=1,
            ),
        )
        a3.tags.set([tags["DNS"], tags["Active Directory"], tags["Windows Server"], tags["Troubleshooting"], tags["Runbook"]])
        a3.contributors.set([alex, jamal])

        # ── A4: Support — LDAP Signing Security Remediation ──────────────────
        a4, _ = Article.objects.get_or_create(
            title="LDAP Signing & Channel Binding Enforcement: Identification and Remediation",
            defaults=dict(
                article_type=Article.ArticleType.SUPPORT,
                category=cats["Security & Compliance"],
                author=chen,
                reviewed_by=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.HIGH,
                affected_systems="Windows Server AD DS, VMware vCenter, Application Servers",
                error_codes="Event ID 2886, 2887, 2889 — LDAP signing warnings",
                microsoft_products="Windows Server 2022, Active Directory, Microsoft Entra ID",
                resolution_type="GPO Enforcement + Application LDAP Authentication Migration",
                time_to_resolve_minutes=240,
                summary="Enterprise playbook for identifying applications using unsigned LDAP binds and safely enforcing LDAP signing without causing application outages.",
                search_keywords="LDAP signing, channel binding, Event 2886, Event 2887, unsigned LDAP bind, domain controller LDAP security",
                content=r"""
Microsoft's hardened LDAP security requirements mandate that all clients connecting to Domain Controllers
use LDAP signing (and optionally channel binding). Environments that have not enforced this will experience
authentication failures after enforcing the new DC behaviour.

Discovery — Identify Offending Clients
Enable LDAP signing diagnostic logging on all DCs:

# Enable LDAP Interface Event logging (Level 2 = verbose)
$ldapDiagPath = "HKLM:\SYSTEM\CurrentControlSet\Services\NTDS\Diagnostics"
Set-ItemProperty -Path $ldapDiagPath -Name "16 LDAP Interface Events" -Value 2
Monitor Event ID 2889 in the Directory Service log — each event contains the client IP
and the account performing unsigned binds:

Get-WinEvent -LogName "Directory Service" -FilterXPath "*[System[EventID=2889]]" |
  Select-Object TimeCreated, Message | Export-Csv C:\Logs\UnsignedLDAP.csv -NoTypeInformation
Remediation by Application Type

  ApplicationRecommended FixNotes
  
    VMware vCenterSwitch to Windows Integrated Authentication (Kerberos)Avoids LDAPS complexity; preferred for vCenter 7+
    Custom Line-of-Business AppsUpdate LDAP library to enforce signing in connection stringSet LDAP_OPT_SIGN flag
    Legacy Monitoring ToolsMigrate to LDAPS (port 636) with a valid DC certificateRequires certificate issued by enterprise CA
    Network Devices (Cisco, etc.)Reconfigure to use LDAPS or Kerberos-based RADIUSVendor-specific; refer to device documentation
  Enforcing LDAP Signing via GPO
# Via Group Policy Management
# Path: Computer Config → Windows Settings → Security Settings →
#        Local Policies → Security Options
# Setting: "Domain controller: LDAP server signing requirements" = Require signing
Apply the GPO to the Domain Controllers OU only. Validate with a phased rollout — start with one DC.


⚠ Do NOT enforce signing before remediating ALL offending clients. Enforcing on a live DC before remediation will cause immediate authentication failures for affected applications.
""",
                is_verified=True,
                published_at=now - timedelta(days=8),
                views_count=62,
                helpful_votes=18,
                not_helpful_votes=2,
            ),
        )
        a4.tags.set([tags["LDAP"], tags["Security"], tags["Active Directory"], tags["GPO"], tags["Windows Server"]])

        # ── A5: Support — MFA Conditional Access Rollout Issue ────────────────
        a5, _ = Article.objects.get_or_create(
            title="MFA Registration Campaign — Users Unable to Complete Registration Flow",
            defaults=dict(
                article_type=Article.ArticleType.SUPPORT,
                category=cats["Identity & Entra ID"],
                author=priya,
                reviewed_by=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.MEDIUM,
                affected_systems="Microsoft Entra ID, Microsoft Authenticator App, SSPR Portal",
                error_codes="AADSTS50076, AADSTS50079, AADSTS90072",
                microsoft_products="Microsoft Entra ID, Microsoft Authenticator, M365",
                resolution_type="Registration Campaign Scope / Named Location Exclusion",
                time_to_resolve_minutes=30,
                summary="Common blockers and fixes for users stuck in the MFA registration loop during an organisation-wide Conditional Access MFA enforcement rollout.",
                search_keywords="MFA registration stuck, Authenticator app loop, SSPR MFA, conditional access MFA block, AADSTS50079",
                content=r"""
During a phased MFA enforcement rollout, a subset of users report being unable to complete the Authenticator app
registration and are blocked in an infinite redirect loop between the sign-in page and the MFA registration
wizard.

Common Causes and Fixes
1. Security Defaults Conflicting with Custom CA Policies
If Security Defaults are still enabled alongside custom Conditional Access policies, users can enter a
conflict state. Disable Security Defaults before deploying CA-based MFA:

Connect-MgGraph -Scopes "Policy.ReadWrite.SecurityDefaults"
$params = @{ IsEnabled = $false }
Update-MgPolicyIdentitySecurityDefaultEnforcementPolicy -BodyParameter $params
2. User Not in MFA Registration Campaign Scope
Verify the user is included in the Registration Campaign policy target group in Entra:


  Entra Admin Center → Protection → Authentication Methods → Registration Campaign

  Confirm the user's group assignment under the campaign scope.
3. Legacy Authentication Protocols Bypassing MFA
# Identify sign-ins using legacy authentication in Entra Sign-In logs
Get-MgAuditLogSignIn -Filter "clientAppUsed eq 'IMAP4'" | Select-Object UserPrincipalName, ClientAppUsed, Status
Block legacy auth via a dedicated CA policy with Client App: Exchange ActiveSync clients + Other clients selected.

4. Named Location Exclusion for Pilot Phase
If certain office IP ranges should be exempt during pilot, configure Named Locations and exclude them from
the MFA CA policy's Conditions → Locations section.


Once rollout is complete, remove Named Location exclusions and enforce MFA from all locations except compliant devices.
""",
                is_featured=False,
                is_verified=True,
                published_at=now - timedelta(days=15),
                views_count=97,
                helpful_votes=29,
                not_helpful_votes=4,
            ),
        )
        a5.tags.set([tags["MFA"], tags["Entra ID"], tags["Security"], tags["M365"], tags["Troubleshooting"]])

        # ── A6: Support — Windows Failover Cluster Network Name Failed ────────
        a6, _ = Article.objects.get_or_create(
            title="Windows Server Failover Cluster: Network Name Resource in Failed State",
            defaults=dict(
                article_type=Article.ArticleType.SUPPORT,
                category=cats["Windows Server & Active Directory"],
                author=jamal,
                reviewed_by=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.CRITICAL,
                affected_systems="Windows Server 2019/2022 Failover Cluster, File Services, SQL Server FCI",
                error_codes="Error 1069 — Resource Failed, Kerberos Event 4, Secure Channel Error",
                microsoft_products="Windows Server 2022, Failover Clustering, Active Directory",
                resolution_type="AD Computer Account Reset + Secure Channel Re-establishment",
                time_to_resolve_minutes=60,
                summary="Full remediation for a Failover Cluster Network Name resource that enters a Failed state due to a desynchronised AD computer account secure channel.",
                search_keywords="cluster network name failed, WSFC resource failed, Kerberos cluster error, secure channel cluster, failover cluster AD",
                content=r"""
The Failover Cluster Network Name resource enters a Failed state and cannot be brought online.
The cluster role associated with the network name (File Share, SQL FCI, etc.) is consequently offline.

Diagnostic Steps
# Check cluster event log for the specific failure reason
Get-ClusterLog -Destination C:\ClusterLogs -TimeSpan 60

# Check if the cluster computer account's secure channel is intact
Test-ComputerSecureChannel -Server "CLUSTER-NAME" -Verbose
Root Cause Confirmation
If Test-ComputerSecureChannel returns False, the computer account password held in AD
has drifted from what the cluster nodes expect. This typically happens after a prolonged outage, domain controller
failover, or manual account manipulation in ADUC.

Remediation

  Reset the secure channel from an active cluster node running as Domain Admin:
Reset-ComputerMachinePassword -Server "PRIMARY-DC.contoso.com" -Credential (Get-Credential)

  Reset the AD computer account password attribute (if the above fails):
# Reset via ADUC or PowerShell
Set-ADComputer -Identity "CLUSTER-NAME" -ServicePrincipalNames @{} -TrustedForDelegation $false
Reset-ADServiceAccountPassword -Identity "CLUSTER-NAME$"

  Bring the Network Name resource back online from Failover Cluster Manager:
Start-ClusterResource -Name "Network Name (CLUSTER-ROLE)"

  Bring the full cluster role online:
Start-ClusterGroup -Name "FILE-SERVER-ROLE"
Validation
Confirm the Network Name resolves correctly and the cluster role is fully online before communicating
restoration to the business. Run cluster.exe /log /level:5 and check for any residual errors.
""",
                is_verified=True,
                published_at=now - timedelta(days=20),
                views_count=41,
                helpful_votes=14,
                not_helpful_votes=1,
            ),
        )
        a6.tags.set([tags["Windows Server"], tags["Active Directory"], tags["Troubleshooting"], tags["Runbook"]])

        # ── A7: Software — PowerShell Health Check Script ─────────────────────
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
                summary="Production-ready PowerShell module that executes 18 health checks across Windows Server infrastructure and Active Directory, then delivers a formatted HTML report via email using Microsoft Graph API.",
                search_keywords="PowerShell health check, AD health script, server monitoring powershell, graph API sendmail, automated health report",
                content=r"""
This module provides automated health-check coverage for Windows Server environments and Active Directory.
It is scheduled via Task Scheduler or Azure Automation and delivers results via the Microsoft Graph sendMail endpoint,
requiring no SMTP relay.

Prerequisites

  PowerShell 5.1+ (PS7 recommended for parallel execution)

  App Registration in Entra ID with Mail.Send and Directory.Read.All Graph permissions

  Certificate-based authentication configured for the App Registration
Core Functions
function Invoke-ServerHealthCheck {
    param (
        [string[]]$Servers,
        [string]$TenantId,
        [string]$ClientId,
        [string]$CertThumbprint
    )

    $token = Get-GraphAccessToken -TenantId $TenantId -ClientId $ClientId -CertThumbprint $CertThumbprint
    $results = @()

    foreach ($server in $Servers) {
        $check = [PSCustomObject]@{
            ServerName     = $server
            Online         = Test-Connection $server -Count 1 -Quiet
            DiskUsage      = Get-DiskUsagePercent -ComputerName $server
            CPUAvg         = Get-CpuAverage -ComputerName $server -Minutes 5
            EventLogErrors = Get-RecentErrors -ComputerName $server -Hours 24
            ServiceStatus  = Get-CriticalServiceStatus -ComputerName $server
            LastPatchDate  = Get-LastPatchInstall -ComputerName $server
            ADReplication  = Test-ADReplication -ComputerName $server
        }
        $results += $check
    }

    $htmlBody = ConvertTo-HtmlReport -Data $results
    Send-GraphMail -Token $token -To "infra-team@msp.com" -Subject "Daily Health Report" -Body $htmlBody
}
Scheduling
$action = New-ScheduledTaskAction -Execute "pwsh.exe" `
    -Argument "-NonInteractive -File C:\\Scripts\\Invoke-HealthCheck.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At "07:00"
Register-ScheduledTask -TaskName "MSP Daily Health Check" -Action $action -Trigger $trigger -RunLevel Highest
""",
                is_featured=True,
                is_verified=True,
                published_at=now - timedelta(days=30),
                views_count=211,
                helpful_votes=67,
                not_helpful_votes=5,
            ),
        )
        a7.tags.set([tags["PowerShell"], tags["Windows Server"], tags["Active Directory"], tags["Monitoring"], tags["Azure"]])
        a7.contributors.set([alex, priya])

        # ── A8: Project — Hybrid Mailbox Migration Playbook ───────────────────
        a8, _ = Article.objects.get_or_create(
            title="Hybrid Exchange Online Mailbox Migration: Architecture & Execution Playbook",
            defaults=dict(
                article_type=Article.ArticleType.PROJECT,
                category=cats["Cloud Migration Playbooks"],
                author=priya,
                reviewed_by=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.NA,
                project_type="Datacenter to Cloud Migration",
                tech_stack="Exchange Server 2019, Exchange Online, Azure MRS Proxy, PowerShell, Microsoft 365",
                difficulty_level=Article.DifficultyLevel.ADVANCED,
                estimated_duration="3 Weeks",
                prerequisites=(
                    "1. Exchange Hybrid Configuration Wizard (HCW) executed and validated successfully.\n"
                    "2. MRSProxy endpoint enabled on all Client Access / Edge servers.\n"
                    "3. OAuth certificate configured and not expired.\n"
                    "4. Mail flow validated end-to-end in hybrid mode.\n"
                    "5. Migration endpoint created and test-connectivity confirmed."
                ),
                summary="Comprehensive architectural guide and phased execution plan for migrating 5,000+ enterprise mailboxes to Exchange Online with zero mail flow disruption.",
                search_keywords="exchange migration, mailbox migration, exchange online hybrid, MRS proxy, migration batch, Exchange HCW, M365 mailbox move",
                content=r"""
This playbook establishes the full operational phases required to stage, move, and cut over legacy on-premises
Exchange mailboxes to Microsoft 365 infrastructure at enterprise scale, maintaining mail flow continuity throughout.

Architecture Overview
The migration leverages the Mailbox Replication Service (MRS) operating over the hybrid MRSProxy
endpoint. Mail flow is maintained bidirectionally throughout the migration via the existing hybrid mail flow
connectors configured during the Hybrid Configuration Wizard execution.

  PhaseDurationScopeOwner
  
    1. ValidationDay 1-2Infra pre-checks, MRS validationExchange Engineer
    2. Pilot BatchDay 3-520 VIP mailboxesExchange Engineer
    3. Wave 1Week 21,500 mailboxes, non-execMigration Team
    4. Wave 2-NWeek 3Remaining mailboxesMigration Team
    5. CutoverWeek 3 endDNS MX cutover, decommissionNetwork + Exchange
  Success Criteria

  Zero mail loss across all migration waves (monitored via MRS move report).

  Mailbox access latency within 10% of baseline post-migration.

  All public folder co-existence rules validated and functional.

  Legacy on-prem environment decommission-ready after final wave.
""",
                is_pinned=True,
                is_featured=True,
                is_verified=True,
                published_at=now - timedelta(days=45),
                views_count=178,
                helpful_votes=52,
                not_helpful_votes=3,
            ),
        )
        a8.tags.set([tags["Exchange Online"], tags["Exchange On-Prem"], tags["PowerShell"], tags["M365"], tags["Runbook"]])
        a8.contributors.set([alex, chen])

        # Project Steps for A8
        steps_a8 = [
            dict(
                step_number=1,
                title="Validate MRSProxy Endpoint Readiness",
                description="Ensure the Mailbox Replication Service Proxy endpoint is active and responding on port 443 on all Client Access servers.",
                code_snippet=r"Get-WebServicesVirtualDirectory -Server EXCH01 | Set-WebServicesVirtualDirectory -MRSProxyEnabled $true`nTest-MigrationServerAvailability -ExchangeRemoteMove -RemoteServer 'mail.contoso.com'",
                code_language="powershell",
                warning="Enabling MRSProxy triggers an automatic IIS AppPool restart. Execute only during a declared change window.",
                tip="Run Test-MigrationServerAvailability from the Exchange Online PowerShell module to verify end-to-end connectivity before creating any batch.",
                estimated_minutes=20,
            ),
            dict(
                step_number=2,
                title="Create Migration Endpoint",
                description="Create the Migration Endpoint in Exchange Online that points to the on-premises hybrid server.",
                code_snippet=r"Connect-ExchangeOnline`nNew-MigrationEndpoint -Name 'HybridEndpoint' -ExchangeRemoteMove -RemoteServer 'mail.contoso.com' -Credentials (Get-Credential)",
                code_language="powershell",
                tip="Name the endpoint clearly — it will be referenced in every batch creation command.",
                estimated_minutes=15,
            ),
            dict(
                step_number=3,
                title="Build CSV Batch Payload",
                description="Compile the pilot user identity batch using a CSV containing the EmailAddress column (primary SMTP address).",
                code_snippet=r'# Pilot CSV format' + "\n" + r'# EmailAddress' + "\n" + r'# vip.user1@contoso.com' + "\n" + r'# vip.user2@contoso.com' + "\n\n" + r'$csvPath = "C:\Mig\pilot_batch.csv"' + "\n" + r'$csvData = [System.IO.File]::ReadAllBytes($csvPath)',
                code_language="powershell",
                tip="Limit pilot batch to 20-50 mailboxes. Prioritise non-exec, technical users who can self-diagnose minor post-migration issues.",
                estimated_minutes=30,
            ),
            dict(
                step_number=4,
                title="Create and Start Migration Batch",
                description="Create the migration batch in Exchange Online and set it to auto-complete once initial sync finishes.",
                code_snippet=r'New-MigrationBatch -Name "Batch_Pilot_01" `' + "\n" + r'  -SourceEndpoint "HybridEndpoint" `' + "\n" + r'  -CSVData $csvData `' + "\n" + r'  -TargetDeliveryDomain "contoso.mail.onmicrosoft.com" `' + "\n" + r'  -AutoStart `' + "\n" + r'  -AutoComplete' + "\n\n" + r'Get-MigrationBatch -Identity "Batch_Pilot_01" | Select-Object Status, TotalCount, SyncedCount, FailedCount',
                code_language="powershell",
                warning="Do NOT set AutoComplete for production waves unless you have a confirmed maintenance window. Set it to manual to control cutover timing.",
                estimated_minutes=45,
            ),
            dict(
                step_number=5,
                title="Monitor and Validate Batch Health",
                description="Continuously monitor the batch progress and individual mailbox move reports for failures.",
                code_snippet=r'# Live monitoring loop' + "\n" + r'while ($true) {' + "\n" + r'  $batch = Get-MigrationBatch -Identity "Batch_Pilot_01"' + "\n" + r'  Write-Host "$($batch.Status) | Synced: $($batch.SyncedCount)/$($batch.TotalCount) | Failed: $($batch.FailedCount)"' + "\n" + r'  Start-Sleep -Seconds 60' + "\n" + r'}' + "\n\n" + r'# Get detailed move report for a failed mailbox' + "\n" + r'Get-MoveRequestStatistics -Identity "vip.user1@contoso.com" -IncludeReport | Select-Object -ExpandProperty Report',
                code_language="powershell",
                tip="Export the full move report to CSV at the end of each wave for auditing purposes.",
                estimated_minutes=60,
            ),
            dict(
                step_number=6,
                title="DNS MX Cutover (Final Wave Only)",
                description="After the final wave completes and all mailboxes are confirmed in Exchange Online, perform the MX record cutover.",
                code_snippet=r'# Verify all mailboxes are cloud-hosted' + "\n" + r'Get-Recipient -ResultSize Unlimited | Where-Object {$_.RecipientTypeDetails -eq "UserMailbox" -and $_.Database -ne $null} | Select-Object Name, Database' + "\n\n" + r'# MX change: point to Microsoft 365' + "\n" + r'# Old: contoso.com MX → mail.contoso.com (on-prem)' + "\n" + r'# New: contoso.com MX → contoso-com.mail.protection.outlook.com (EXO)',
                code_language="powershell",
                warning="Coordinate MX TTL reduction (to 300s) 48 hours before cutover. Monitor mail flow for 2 hours post-cutover before confirming success.",
                estimated_minutes=120,
            ),
        ]
        for s in steps_a8:
            ProjectStep.objects.get_or_create(article=a8, step_number=s["step_number"], defaults=s)

        # ── A9: Project — Windows Autopilot + Intune Deployment ──────────────
        a9, _ = Article.objects.get_or_create(
            title="Zero-Touch Windows 11 Provisioning: Autopilot + Intune Hybrid Azure AD Join",
            defaults=dict(
                article_type=Article.ArticleType.PROJECT,
                category=cats["Microsoft Intune & Autopilot"],
                author=jamal,
                reviewed_by=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                project_type="Endpoint Management Deployment",
                tech_stack="Windows Autopilot, Microsoft Intune, Azure AD, Windows 11, PowerShell, Intune Graph API",
                difficulty_level=Article.DifficultyLevel.ADVANCED,
                estimated_duration="2 Weeks",
                prerequisites=(
                    "1. Intune configured with Hybrid Azure AD Join profile.\n"
                    "2. Intune Connector for Active Directory installed on an on-prem domain-joined server.\n"
                    "3. Device hardware hash collected and uploaded to Autopilot.\n"
                    "4. Deployment profile created and assigned to the target device group.\n"
                    "5. Required apps packaged as .intunewin and available in Intune app catalogue."
                ),
                summary="End-to-end implementation guide for zero-touch Windows 11 device provisioning using Windows Autopilot in Hybrid Azure AD Join mode with department-based Intune app deployment.",
                search_keywords="Autopilot, zero touch deployment, Intune hybrid join, Windows 11 provisioning, OOBE, device enrollment, Intune app deployment",
                content=r"""
This playbook delivers a fully automated Windows 11 device provisioning pipeline using the Windows Autopilot Hybrid Azure AD Join deployment model. Devices boot from factory
state, register themselves, join the domain, and receive their application set — all without
a technician touching the machine beyond physically powering it on.

High-Level Flow

  Device boots → OOBE detects Autopilot profile via device serial / hardware hash lookup in Intune.

  Autopilot applies Deployment Profile → suppresses standard OOBE pages.

  Intune Connector coordinates Hybrid Azure AD Join → device joins on-prem domain AND registers in Entra.

  Compliance policy evaluates → device becomes compliant.

  Dynamic Entra group membership based on department attribute triggers app assignment.

  Required and available apps are silently installed via Intune Win32 deployment.
""",
                is_featured=True,
                is_verified=True,
                published_at=now - timedelta(days=10),
                views_count=134,
                helpful_votes=45,
                not_helpful_votes=2,
            ),
        )
        a9.tags.set([tags["Intune"], tags["Autopilot"], tags["Azure"], tags["Windows Server"], tags["Entra ID"]])

        steps_a9 = [
            dict(
                step_number=1,
                title="Collect and Upload Device Hardware Hash",
                description="Use the Get-WindowsAutoPilotInfo script to collect the hardware hash from each device and upload to Intune/Autopilot.",
                code_snippet=r"Install-Script -Name Get-WindowsAutoPilotInfo -Force" + "\n" + r"Get-WindowsAutoPilotInfo -Online -GroupTag 'Corporate-HQ'",
                code_language="powershell",
                tip="Run this from within Windows PE or from the device itself before shipping to the end user. The -Online flag uploads directly to Intune without needing a CSV file.",
                estimated_minutes=15,
            ),
            dict(
                step_number=2,
                title="Create Autopilot Deployment Profile",
                description="In Intune, create a Hybrid Azure AD Join deployment profile targeting the uploaded device group.",
                code_snippet=r'# Verify device shows in Autopilot devices' + "\n" + r'Connect-MSGraph' + "\n" + r'Get-AutopilotDevice | Select-Object SerialNumber, Model, GroupTag',
                code_language="powershell",
                warning="Select 'Hybrid Azure AD joined' (not Azure AD joined) in the deployment profile Join Type. Choosing the wrong type is the #1 cause of Autopilot failures in on-prem environments.",
                estimated_minutes=30,
            ),
            dict(
                step_number=3,
                title="Configure Dynamic Device Groups by Department",
                description="Create dynamic Entra device groups that auto-populate based on the user's department attribute, enabling department-specific app deployments.",
                code_snippet=r'(device.enrollmentProfileName -eq "Corp-Autopilot-Profile") and (user.department -eq "Finance")',
                code_language="text",
                tip="Use the userExtensionAttribute fields if the standard department attribute is not synced reliably from on-prem AD via Entra Connect.",
                estimated_minutes=20,
            ),
            dict(
                step_number=4,
                title="Package and Deploy Apps via Intune Win32",
                description="Package required applications as .intunewin files using the Microsoft Win32 Content Prep Tool and publish to Intune.",
                code_snippet=r'# Package the app' + "\n" + r'.\IntuneWinAppUtil.exe -c "C:\Sources\App" -s "setup.exe" -o "C:\Output"' + "\n\n" + r'# Detection rule example (registry key)' + "\n" + r'# Key path: HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP-GUID}' + "\n" + r'# Value name: DisplayName' + "\n" + r'# Value: "Application Name"',
                code_language="bash",
                warning="Always test the detection rule before assigning to production groups. An incorrect detection rule causes Intune to loop-reinstall the application on every check-in.",
                estimated_minutes=60,
            ),
        ]
        for s in steps_a9:
            ProjectStep.objects.get_or_create(article=a9, step_number=s["step_number"], defaults=s)

        # ── A10: General — Onboarding Checklist ───────────────────────────────
        a10, _ = Article.objects.get_or_create(
            title="New Client Onboarding: Infrastructure Discovery Checklist",
            defaults=dict(
                article_type=Article.ArticleType.GENERAL,
                category=cats["General IT Guidelines"],
                author=admin,
                status=Article.Status.PUBLISHED,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.NA,
                summary="Standard checklist for the initial infrastructure discovery engagement with a new MSP client, covering AD, Exchange, networking, security posture, and licensing.",
                search_keywords="new client onboarding, MSP discovery, infrastructure assessment, onboarding checklist, client IT audit",
                content=r"""
This checklist must be completed within the first 5 business days of a new client engagement. The output
feeds directly into the Statement of Work (SOW) and the client's infrastructure documentation repository.

Identity & Directory

  ☐ Number of Domain Controllers, OS versions, functional levels

  ☐ AD Sites and Services topology — subnets and site link costs

  ☐ Entra ID sync status — Cloud Only / Synced / Hybrid

  ☐ Privileged account inventory — Domain Admins, Enterprise Admins, Schema Admins

  ☐ Password policy and fine-grained password policies

  ☐ Group Policy Object (GPO) inventory — count, custom vs default
Email & Collaboration

  ☐ Mail platform — Exchange On-Prem / Exchange Online / Hybrid

  ☐ Number of mailboxes, distribution groups, shared mailboxes

  ☐ Mail flow connectors — inbound and outbound

  ☐ Anti-spam / email filtering solution (Defender for Office 365 / third-party)

  ☐ M365 licensing SKUs in use
Infrastructure

  ☐ Server inventory — physical vs virtual, hypervisor type

  ☐ Backup solution and last successful restore test date

  ☐ Firewall vendor and firmware version

  ☐ Network segmentation / VLAN design

  ☐ Internet circuit — provider, bandwidth, redundancy
Security Posture

  ☐ EDR/AV solution deployed across all endpoints

  ☐ MFA status — enforced / partially deployed / not deployed

  ☐ Patch cadence — auto vs manual, last OS patch date

  ☐ Vulnerability scan results from last 90 days

  ☐ Security awareness training status
""",
                is_featured=False,
                is_pinned=True,
                is_verified=True,
                published_at=now - timedelta(days=60),
                views_count=312,
                helpful_votes=89,
                not_helpful_votes=4,
            ),
        )
        a10.tags.set([tags["Active Directory"], tags["M365"], tags["Networking"], tags["Security"], tags["Runbook"]])

        # Draft article
        a11, _ = Article.objects.get_or_create(
            title="TLS 1.0/1.1 Deprecation: Registry Key Remediation for .NET and Schannel",
            defaults=dict(
                article_type=Article.ArticleType.SUPPORT,
                category=cats["Security & Compliance"],
                author=chen,
                status=Article.Status.DRAFT,
                visibility=Article.Visibility.PUBLIC,
                severity=Article.Severity.HIGH,
                affected_systems="Windows Server, IIS, .NET Applications, SQL Server",
                error_codes="SEC_E_ALGORITHM_MISMATCH, Schannel Event 36887, 0x80090326",
                microsoft_products="Windows Server 2019/2022, IIS, .NET Framework, SQL Server",
                resolution_type="Registry Key + .NET Security Configuration",
                time_to_resolve_minutes=90,
                summary="Registry and configuration steps to disable TLS 1.0/1.1 and enforce TLS 1.2+ across Windows Server, .NET applications, and IIS, without breaking existing connectivity.",
                content=r"""
Draft — work in progress.
""",
                needs_review=True,
                views_count=5,
            ),
        )
        a11.tags.set([tags["TLS/SSL"], tags["Certificate"], tags["Security"], tags["Windows Server"]])

        # In-review article
        a12, _ = Article.objects.get_or_create(
            title="SharePoint Online to Teams Migration: File Structure and Permission Mapping",
            defaults=dict(
                article_type=Article.ArticleType.PROJECT,
                category=cats["Cloud Migration Playbooks"],
                author=alex,
                status=Article.Status.IN_REVIEW,
                visibility=Article.Visibility.PUBLIC,
                project_type="Collaboration Platform Migration",
                tech_stack="SharePoint Online, Microsoft Teams, Power Automate, PnP PowerShell",
                difficulty_level=Article.DifficultyLevel.INTERMEDIATE,
                estimated_duration="1 Week per department",
                summary="Project guide for migrating existing SharePoint Online document libraries into Microsoft Teams channels with preserved permission structures.",
                content=r"""
Under peer review — awaiting sign-off from Sarah Connor.
""",
                needs_review=True,
                review_notes="Review focus areas: Permission mapping accuracy, Teams channel naming convention compliance, rollback procedure completeness.",
                views_count=18,
            ),
        )
        a12.tags.set([tags["M365"], tags["Teams"], tags["SharePoint"]])

        all_articles = [a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, a12]
        # Cross-link related articles
        a1.related_articles.add(a5)
        a2.related_articles.add(a5)
        a3.related_articles.add(a6)
        a8.related_articles.add(a9)

        self.stdout.write(self.style.SUCCESS(f"    ✓ {len(all_articles)} articles ready"))

        # ──────────────────────────────────────────────────────────────────────
        # 5. ATTACHMENTS
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  5. Creating attachments…")

        attachments_data = [
            (a1, "entra-sync-runbook.pdf", "Entra Sync Remediation Runbook v2.pdf", 245_760, "application/pdf", alex, "Full diagnostic runbook PDF for distribution to Tier 2 team"),
            (a1, "sync-error-screenshot.png", "SyncManager_Error_Screenshot.png", 87_040, "image/png", alex, "Synchronization Service Manager showing the error state"),
            (a2, "eac-ca-policy-config.pdf", "EAC_CA_Policy_Configuration_Guide.pdf", 198_656, "application/pdf", priya, "Step-by-step CA policy scoping screenshots"),
            (a2, "exchange-rbac-export.xlsx", "Exchange_RBAC_Role_Export.xlsx", 54_272, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", priya, "RBAC role membership export at time of incident"),
            (a3, "dns-repadmin-report.csv", "Repadmin_Replication_Report.csv", 12_800, "text/csv", tom, "AD replication report generated post-remediation"),
            (a4, "ldap-signing-audit.csv", "Unsigned_LDAP_Clients_Audit.csv", 18_432, "text/csv", chen, "CSV export of all Event ID 2889 entries identifying unsigned LDAP clients"),
            (a4, "ldap-gpo-template.xml", "LDAP_Signing_GPO_Template.xml", 6_144, "text/xml", chen, "Exportable GPO backup for LDAP signing enforcement policy"),
            (a7, "ahc-v2-script.ps1", "AHC_v2.ps1", 38_912, "text/plain", chen, "Production PowerShell health check script — AHC v2"),
            (a7, "m365-health-script.ps1", "M365HC_v2.ps1", 41_984, "text/plain", chen, "M365 / Entra ID health check script — M365HC v2"),
            (a8, "migration-pilot-csv.csv", "Pilot_Batch_Template.csv", 2_048, "text/csv", priya, "Migration batch CSV template for pilot wave"),
            (a8, "exchange-migration-sow.docx", "Exchange_Migration_SOW_Template.docx", 312_320, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", admin, "Statement of Work template for Exchange migration engagements"),
            (a9, "autopilot-profile-export.json", "Autopilot_Deployment_Profile.json", 8_192, "application/json", jamal, "Exported Autopilot deployment profile configuration"),
            (a9, "win11-app-matrix.xlsx", "Win11_Department_App_Matrix.xlsx", 89_088, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", jamal, "Department vs required application matrix for Intune assignment"),
            (a10, "onboarding-checklist.pdf", "MSP_Client_Onboarding_Checklist_v3.pdf", 156_672, "application/pdf", admin, "Printable onboarding checklist for use during client site visits"),
        ]

        att_count = 0
        for art, path_hint, name, size, ftype, uploader, desc in attachments_data:
            if not Attachment.objects.filter(article=art, original_name=name).exists():
                Attachment.objects.create(
                    article=art,
                    file=f"uploads/articles/{art.slug}/{path_hint}",
                    original_name=name,
                    file_size_bytes=size,
                    file_type=ftype,
                    uploaded_by=uploader,
                    description=desc,
                )
                att_count += 1

        self.stdout.write(self.style.SUCCESS(f"    ✓ {att_count} attachments created"))

        # ──────────────────────────────────────────────────────────────────────
        # 6. COMMENTS (threaded)
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  6. Creating comments…")

        comments_data = [
            # Article A1 thread
            dict(art=a1, author=admin, parent=None, content="Ensure you clear the connector space anchor cache before triggering the manual delta cycle. The stale anchor will cause the same collision to re-surface."),
            dict(art=a1, author=alex, parent=None, content="Confirmed — also worth checking if the cloud object was created by a former admin before Connect was deployed. Soft-match is the cleanest path in that scenario."),
            dict(art=a1, author=jamal, parent=None, content="Can this be used if the cloud account has an active mailbox? I assume we'd need to export PST first before soft-matching and merging."),
            # Article A2 thread
            dict(art=a2, author=priya, parent=None, content="Important note: if the CA policy was just created, it can take up to 5-10 minutes to propagate to all Entra sign-in enforcement points. Clearing the browser session first always helps."),
            dict(art=a2, author=john, parent=None, content="This article saved us during a P1 incident last Tuesday. The CA exclusion for the app registration was the fix we needed."),
            dict(art=a2, author=amina, parent=None, content="Should we also check if the admin account has the 'Exchange Recipient Administrator' role specifically? The 'Exchange Administrator' role doesn't always grant EAC access in delegated tenants."),
            # Article A3 thread
            dict(art=a3, author=tom, parent=None, content="After running the stale record cleanup, also audit the _msdcs zone specifically. I've seen decommissioned DCs leave SRV records in the _msdcs zone that continue to cause Kerberos failures even after the NS records are cleaned."),
            dict(art=a3, author=alex, parent=None, content="Good call. The Global Catalog SRV records in _msdcs are particularly nasty — they affect all forest-wide Kerberos authentications, not just the domain."),
            # Article A7 thread
            dict(art=a7, author=chen, parent=None, content="For PS7 compatibility, note that .Count on an empty result set behaves differently. Wrap all count checks with @() to ensure array coercion. PS5 returns null, PS7 returns 0 — both break if you don't account for it."),
            dict(art=a7, author=alex, parent=None, content="Also tested the Graph sendMail function against a tenant with Security Defaults enabled — works fine as long as the App Registration uses certificate auth rather than client secret."),
            # Article A8 thread
            dict(art=a8, author=priya, parent=None, content="One thing to highlight: set the bad item limit to at least 50 for large mailboxes. Default is 0 and a single corrupted calendar item will halt the entire move for that mailbox."),
            dict(art=a8, author=admin, parent=None, content="Approved for use as the standard delivery template for all Exchange Online migration engagements. Please update the client name placeholder before distributing to customers."),
            # Article A10 thread
            dict(art=a10, author=jamal, parent=None, content="Added the Defender for Business licensing check to the security posture section after we found three consecutive clients without it. Worth making it a mandatory checkbox."),
        ]

        created_comments = {}
        c_count = 0
        for cd in comments_data:
            c, created = Comment.objects.get_or_create(
                article=cd["art"],
                author=cd["author"],
                content=cd["content"],
                defaults={"is_approved": True, "is_pinned": False},
            )
            created_comments[(cd["art"].pk, cd["author"].pk)] = c
            if created:
                c_count += 1

        # Threaded replies
        parent_a1 = created_comments.get((a1.pk, admin.pk))
        if parent_a1:
            Comment.objects.get_or_create(
                article=a1,
                author=alex,
                parent=parent_a1,
                defaults={"content": "Confirmed. Added the cache-clear step to the runbook attached in the article. Thanks Sarah.", "is_approved": True},
            )
        parent_a2 = created_comments.get((a2.pk, priya.pk))
        if parent_a2:
            Comment.objects.get_or_create(
                article=a2,
                author=john,
                parent=parent_a2,
                defaults={"content": "Good point — we also tried InPrivate browsing which helped rule out token caching as a factor.", "is_approved": True},
            )
        parent_a8 = created_comments.get((a8.pk, priya.pk))
        if parent_a8:
            Comment.objects.get_or_create(
                article=a8,
                author=alex,
                parent=parent_a8,
                defaults={"content": "Agreed. Also set AcceptLargeDataLoss for any mailbox over 25GB. Always pre-validate via Test-MoveRequest before starting production waves.", "is_approved": True},
            )

        self.stdout.write(self.style.SUCCESS(f"    ✓ {c_count}+ comments and threaded replies created"))

        # ──────────────────────────────────────────────────────────────────────
        # 7. ARTICLE FEEDBACK
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  7. Recording article feedback…")
        feedback_data = [
            (a1, alex, True, "Resolved a P2 incident in under an hour. The ImmutableId soft-match command was exactly what we needed."),
            (a1, jamal, True, "Clear and well-structured. Used it as a training reference for our Tier 2 team."),
            (a1, john, False, "The steps assume Entra Connect v2. We were on v1.6 and some cmdlets differed."),
            (a2, priya, True, ""),
            (a2, alex, True, "Saved us during a critical P1. CA exclusion for the Exchange app ID was the key detail missing from Microsoft docs."),
            (a2, amina, True, ""),
            (a3, tom, True, ""),
            (a3, chen, True, "The _msdcs SRV cleanup tip in the comments is gold. Should be part of the main article."),
            (a4, jamal, True, "Excellent security article. The vCenter Kerberos recommendation avoided a significant rework of our LDAPS certificate pipeline."),
            (a5, priya, True, ""),
            (a7, alex, True, "Running this in production across 14 clients. Solid and reliable."),
            (a7, chen, True, ""),
            (a7, tom, True, "The PS5/PS7 .Count quirk note in the comments is critical — burned us early on."),
            (a8, admin, True, "Approved for corporate-wide delivery use."),
            (a8, priya, True, ""),
            (a8, alex, True, "Used this for a 3,200 mailbox migration. Flawless with the bad item limit tip applied."),
            (a9, jamal, True, ""),
            (a9, chen, True, "The dynamic group membership rule for department assignment is clean. No more manual app assignment."),
            (a10, john, True, ""),
            (a10, amina, True, "Used this on our last three new client onboardings. Very complete."),
        ]
        fb_count = 0
        for art, user, helpful, text in feedback_data:
            _, created = ArticleFeedback.objects.get_or_create(
                article=art,
                user=user,
                defaults={"is_helpful": helpful, "feedback_text": text},
            )
            if created:
                fb_count += 1

        # Recalculate vote tallies
        for art in [a1, a2, a3, a4, a5, a6, a7, a8, a9, a10]:
            art.helpful_votes = ArticleFeedback.objects.filter(article=art, is_helpful=True).count()
            art.not_helpful_votes = ArticleFeedback.objects.filter(article=art, is_helpful=False).count()
            Article.objects.filter(pk=art.pk).update(
                helpful_votes=art.helpful_votes,
                not_helpful_votes=art.not_helpful_votes,
            )

        self.stdout.write(self.style.SUCCESS(f"    ✓ {fb_count} feedback records created"))

        # ──────────────────────────────────────────────────────────────────────
        # 8. ARTICLE VIEWS (analytics simulation)
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  8. Simulating article views…")
        view_scenarios = [
            (a1, alex, "192.168.1.100"),
            (a1, jamal, "192.168.1.101"),
            (a1, john, "192.168.1.105"),
            (a1, amina, "192.168.1.106"),
            (a2, priya, "192.168.1.102"),
            (a2, alex, "192.168.1.100"),
            (a2, john, "192.168.1.105"),
            (a2, amina, "192.168.1.106"),
            (a3, tom, "192.168.1.103"),
            (a3, chen, "192.168.1.104"),
            (a4, chen, "192.168.1.104"),
            (a4, admin, "192.168.1.1"),
            (a5, priya, "192.168.1.102"),
            (a5, john, "192.168.1.105"),
            (a7, alex, "192.168.1.100"),
            (a7, chen, "192.168.1.104"),
            (a8, priya, "192.168.1.102"),
            (a8, alex, "192.168.1.100"),
            (a9, jamal, "192.168.1.101"),
            (a9, chen, "192.168.1.104"),
            (a10, admin, "192.168.1.1"),
            (a10, john, "192.168.1.105"),
        ]
        for art, user, ip in view_scenarios:
            ArticleView.objects.create(article=art, user=user, ip_address=ip)

        self.stdout.write(self.style.SUCCESS(f"    ✓ {len(view_scenarios)} view events created"))

        # ──────────────────────────────────────────────────────────────────────
        # 9. SEARCH LOGS
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  9. Populating search logs…")
        search_scenarios = [
            ("Entra ID Sync Error", alex, 1, "192.168.1.100"),
            ("UPN conflict Azure AD", jamal, 1, "192.168.1.101"),
            ("Exchange Admin Center 403", priya, 1, "192.168.1.102"),
            ("Cannot access EAC", john, 1, "192.168.1.105"),
            ("LDAP signing Event 2886", chen, 1, "192.168.1.104"),
            ("DNS failure domain controller", tom, 1, "192.168.1.103"),
            ("Autopilot Hybrid Azure AD", jamal, 2, "192.168.1.101"),
            ("Exchange mailbox migration", priya, 3, "192.168.1.102"),
            ("PowerShell health check script", alex, 1, "192.168.1.100"),
            ("MFA registration loop", amina, 1, "192.168.1.106"),
            ("cluster network name failed", jamal, 1, "192.168.1.101"),
            ("Conditional Access block admin", admin, 2, "192.168.1.1"),
            ("MRS proxy migration batch", priya, 1, "192.168.1.102"),
            ("onboarding checklist new client", john, 1, "192.168.1.105"),
            ("TLS 1.0 disable registry", chen, 0, "192.168.1.104"),
        ]
        for query, user, count, ip in search_scenarios:
            SearchLog.objects.create(query=query, user=user, results_count=count, ip_address=ip)

        self.stdout.write(self.style.SUCCESS(f"    ✓ {len(search_scenarios)} search log entries created"))

        # ──────────────────────────────────────────────────────────────────────
        # 10. NOTIFICATIONS
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  10. Creating notifications…")
        notif_data = [
            (alex, Notification.NotificationType.COMMENT, "New reply on your article", f"{admin.full_name} replied to a comment on '{a1.title}'.", a1, False),
            (priya, Notification.NotificationType.ARTICLE_PUBLISHED, "Your article is live", f"'{a2.title}' has been published and is visible to all staff.", a2, True),
            (priya, Notification.NotificationType.COMMENT, "New comment on your article", f"{john.full_name} commented on '{a2.title}'.", a2, False),
            (admin, Notification.NotificationType.REVIEW_REQUEST, "Review requested", f"{alex.full_name} has requested a review of '{a12.title}'.", a12, False),
            (admin, Notification.NotificationType.REVIEW_REQUEST, "Review requested", f"{chen.full_name} has submitted '{a11.title}' for review.", a11, False),
            (chen, Notification.NotificationType.MENTION, "You were mentioned", f"{alex.full_name} mentioned you in a comment on '{a7.title}'.", a7, True),
            (tom, Notification.NotificationType.ARTICLE_UPDATED, "Article you contributed to was updated", f"'{a3.title}' was updated by {alex.full_name}.", a3, False),
            (jamal, Notification.NotificationType.COMMENT, "New comment on your article", f"{tom.full_name} commented on '{a9.title}'.", a9, False),
            (john, Notification.NotificationType.SYSTEM, "Welcome to MSP Knowledge Base", "Your account is active. Start exploring the knowledge base or use the search bar to find articles.", None, False),
            (amina, Notification.NotificationType.SYSTEM, "Welcome to MSP Knowledge Base", "Your account is active. Start exploring the knowledge base or use the search bar to find articles.", None, False),
        ]
        for user, n_type, title, message, article, is_read in notif_data:
            Notification.objects.create(
                user=user,
                notification_type=n_type,
                title=title,
                message=message,
                article=article,
                is_read=is_read,
                read_at=now if is_read else None,
            )

        self.stdout.write(self.style.SUCCESS(f"    ✓ {len(notif_data)} notifications created"))

        # ──────────────────────────────────────────────────────────────────────
        # 11. TAG USAGE COUNTS
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write("  11. Recalculating tag usage counts…")
        for tag in Tag.objects.all():
            Tag.objects.filter(pk=tag.pk).update(usage_count=tag.articles.count())

        # ── Final Summary ─────────────────────────────────────────────────────
        self.stdout.write("\n" + self.style.MIGRATE_HEADING("━━━  Seeding Complete  ━━━"))
        self.stdout.write(
            self.style.SUCCESS(
                f"\n  Users:         {User.objects.filter(is_superuser=False).count()}"
                f"\n  Categories:    {Category.objects.count()}"
                f"\n  Tags:          {Tag.objects.count()}"
                f"\n  Articles:      {Article.objects.count()} "
                f"(Published: {Article.objects.filter(status=Article.Status.PUBLISHED).count()}, "
                f"Draft: {Article.objects.filter(status=Article.Status.DRAFT).count()}, "
                f"In Review: {Article.objects.filter(status=Article.Status.IN_REVIEW).count()})"
                f"\n  Project Steps: {ProjectStep.objects.count()}"
                f"\n  Attachments:   {Attachment.objects.count()}"
                f"\n  Comments:      {Comment.objects.count()}"
                f"\n  Feedback:      {ArticleFeedback.objects.count()}"
                f"\n  Views:         {ArticleView.objects.count()}"
                f"\n  Search Logs:   {SearchLog.objects.count()}"
                f"\n  Notifications: {Notification.objects.count()}"
            )
        )
        self.stdout.write(
            self.style.NOTICE(
                "\n  Login credentials (all accounts):"
                "\n    admin@msp.com      / Password123!  (Administrator)"
                "\n    alex.m@msp.com     / Password123!  (Engineer)"
                "\n    chen.w@msp.com     / Password123!  (Engineer)"
                "\n    jamal.k@msp.com    / Password123!  (Engineer)"
                "\n    priya.r@msp.com    / Password123!  (Engineer)"
                "\n    tom.b@msp.com      / Password123!  (Engineer)"
                "\n    viewer.j@msp.com   / Password123!  (Viewer)"
                "\n    viewer.a@msp.com   / Password123!  (Viewer)\n"
            )
        )