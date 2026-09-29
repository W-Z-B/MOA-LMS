"""Load demonstration teaching content into the course sites, plus one staff-development site.

For staging and development databases only. The LMS owns no person and no class list, so this
command first pulls sites and class lists from the SRMS and names from the HRMS, then adds content,
assignments, submissions and marks for whoever is in each class. Run it after the demonstration data
of the HRMS and the SRMS are loaded. Idempotent: running it again adds nothing.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from assessments.models import Assignment, Mark, Submission
from courses.models import Announcement, Completion, ContentItem, CourseSite, Membership, Module
from integration.client import IntegrationError

# Two weeks of material per course: course, module, page, body. Modules and pages keep this order.
PAGES = [
    ("AGR101", "Week 1: What a crop needs", "Course outline", "How crops grow, from seed to harvest."),
    ("AGR101", "Week 1: What a crop needs", "Light, water, air and nutrients", "Notes for lecture one."),
    ("AGR101", "Week 2: Seed and germination", "Germination trial: method", "Work in pairs; record daily."),
    ("AGR102", "Week 1: What soil is made of", "Course outline", "Texture, structure, water and fertility."),
    ("AGR102", "Week 1: What soil is made of", "Sand, silt and clay", "Notes, with the jar test."),
    ("AGR102", "Week 2: Taking a soil sample", "Sampling a field", "Walk a zigzag; take fifteen cores."),
    ("AGR110", "Week 1: Why farms keep records", "Course outline", "Measuring land and counting costs."),
    (
        "AGR110",
        "Week 1: Why farms keep records",
        "Units and conversions",
        "Acres and hectares; pounds and kilos.",
    ),
    ("AGR110", "Week 2: The farm diary", "A week in a farm diary", "A worked example for your own plot."),
    ("LIV101", "Week 1: Animals on the farm", "Course outline", "Housing, feeding, health and handling."),
    ("LIV101", "Week 1: Animals on the farm", "Handling animals safely", "Read before your first session."),
    ("LIV101", "Week 2: Feed and water", "Reading a feed label", "Protein, energy and fibre."),
]

# title, maximum mark, weight, days from today to the due date
ASSIGNMENTS = {
    "AGR101": [("Germination trial report", 50, 2, -14), ("Crop calendar for a kitchen garden", 100, 3, 14)],
    "AGR102": [("Soil texture by the jar test", 50, 2, -14), ("Soil sampling report", 100, 3, 14)],
    "AGR110": [("Measuring a plot", 40, 1, -14), ("One month of farm records", 100, 2, 14)],
    "LIV101": [
        ("Housing checklist for a small flock", 50, 2, -14),
        ("Feeding plan for ten goats", 100, 3, 14),
    ],
}

# Marks for the first assignment as a share of the maximum, given to the class in name order. The
# last student has not submitted (counts as zero once overdue); the one before is still to be marked.
SHARES = [Decimal(s) for s in ("0.84", "0.76", "0.90", "0.62", "0.94", "0.70", "0.80", "0.56")]

STAFF_SITE = {
    "code": "SD-101",
    "title": "Records management for HR officers",
    "description": "A short course for administrative staff on keeping personnel records.",
    "members": ["E0006", "E0007"],
    "completed_by": "E0006",
    "completed_on": date(2026, 9, 18),
}


class Command(BaseCommand):
    help = "Load demonstration teaching content (staging and development only). Requires --fictional."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fictional",
            action="store_true",
            help="Required: confirms this database is for demonstration, never for real records",
        )

    def handle(self, *args, **options):
        if not options["fictional"]:
            raise CommandError(
                "This loads invented coursework. "
                "Pass --fictional to confirm the database is for demonstration only."
            )
        self._pull()
        with transaction.atomic():
            sites = [s for s in CourseSite.objects.filter(source=CourseSite.Source.SRMS) if self._course(s)]
            for site in sites:
                self._teach(site)
            staff_members = self._staff_site()
        if not sites:
            self.stdout.write(
                self.style.WARNING(
                    "No course sites yet: load the SRMS demonstration data, check SRMS_API_URL and "
                    "SRMS_API_KEY, then run this command again."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Demonstration data applied: content in {len(sites)} course sites, "
                f"{Submission.objects.count()} submissions, {Mark.objects.count()} marks, "
                f"staff-development site with {staff_members} members."
            )
        )

    def _pull(self) -> None:
        if not settings.SRMS_API_URL or not settings.SRMS_API_KEY:
            return
        from integration import srms

        try:
            self.stdout.write(f"sites: {srms.sync_sites()}")
        except IntegrationError as exc:
            self.stdout.write(self.style.WARNING(f"The SRMS could not be reached: {exc}"))

    @staticmethod
    def _course(site: CourseSite) -> str | None:
        code = site.code.split("-")[0]
        return code if code in ASSIGNMENTS else None

    def _teach(self, site: CourseSite) -> None:
        course = self._course(site)
        lecturer = (
            Membership.objects.filter(site=site, role=Membership.SiteRole.LECTURER, is_active=True)
            .select_related("person")
            .first()
        )
        author = lecturer.person if lecturer else None
        if not site.is_published:
            site.is_published = True
            site.save(update_fields=["is_published", "updated_at"])
        modules: dict[str, Module] = {}
        for order, (_, title, page, body) in enumerate((p for p in PAGES if p[0] == course), start=1):
            if title not in modules:
                modules[title], _ = Module.objects.get_or_create(
                    site=site, title=title, defaults={"position": len(modules) + 1}
                )
            ContentItem.objects.get_or_create(
                module=modules[title], title=page, defaults={"body": body, "position": order}
            )
        Announcement.objects.get_or_create(
            site=site,
            title="Welcome to the course",
            defaults={
                "body": "The outline and the notes for week one are in Content. Assignment one is open.",
                "author": author,
            },
        )
        now = timezone.now()
        for index, (title, maximum, weight, days) in enumerate(ASSIGNMENTS[course]):
            assignment, created = Assignment.objects.get_or_create(
                site=site,
                title=title,
                defaults={
                    "instructions": "Submit one document. Show your working and name your sources.",
                    "opens_at": now + timedelta(days=days - 21),
                    "due_at": now + timedelta(days=days),
                    "max_mark": maximum,
                    "weight": weight,
                    "is_published": True,
                },
            )
            if created and index == 0:
                self._mark(assignment, author)

    def _mark(self, assignment: Assignment, marker) -> None:
        members = list(
            Membership.objects.filter(site=assignment.site, role=Membership.SiteRole.STUDENT, is_active=True)
            .select_related("person")
            .order_by("person__last_name", "person__first_name")
        )
        for index, membership in enumerate(members):
            if len(members) > 2 and index == len(members) - 1:
                continue  # not submitted
            late = index == 1
            submission = Submission.objects.create(
                assignment=assignment,
                student=membership.person,
                text="Demonstration submission.",
                submitted_at=assignment.due_at + timedelta(hours=6 if late else -30),
                is_late=late,
            )
            if len(members) > 3 and index == len(members) - 2:
                continue  # submitted, waiting to be marked
            Mark.objects.create(
                submission=submission,
                mark=(assignment.max_mark * SHARES[index % len(SHARES)]).quantize(Decimal("1")),
                feedback="Clear method and tidy records. Say more about what the results mean.",
                marked_by=marker,
                is_released=True,
            )

    def _staff_site(self) -> int:
        site, _ = CourseSite.objects.get_or_create(
            code=STAFF_SITE["code"],
            defaults={
                "title": STAFF_SITE["title"],
                "description": STAFF_SITE["description"],
                "kind": CourseSite.Kind.STAFF_DEVELOPMENT,
                "source": CourseSite.Source.LOCAL,
                "is_published": True,
            },
        )
        module, _ = Module.objects.get_or_create(site=site, title="Keeping a personnel file")
        ContentItem.objects.get_or_create(
            module=module,
            title="What belongs in the file",
            defaults={
                "body": "Appointment letters, contracts, leave records and certificates, in date order."
            },
        )
        for person in self._staff(STAFF_SITE["members"]):
            Membership.objects.get_or_create(site=site, person=person)
            if person.external_id == STAFF_SITE["completed_by"]:
                Completion.objects.get_or_create(
                    site=site,
                    person=person,
                    defaults={
                        "completed_on": STAFF_SITE["completed_on"],
                        "certificate": "Certificate of completion",
                    },
                )
        return site.memberships.count()

    def _staff(self, employee_nos: list[str]) -> list:
        if not settings.HRMS_API_URL or not settings.HRMS_API_KEY:
            return []
        from integration import hrms

        try:
            return hrms.staff_refs(employee_nos)
        except IntegrationError as exc:
            self.stdout.write(self.style.WARNING(f"The HRMS could not be reached: {exc}"))
            return []
