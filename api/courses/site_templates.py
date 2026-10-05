"""Course templates (item 2.17): the GSA standard layout given to every new, empty site.

Every course then has the same shape, so a student moving between courses knows where things are: a
course overview, the course outline, one module for each teaching week, and assessment. The pages come in
as drafts, unseen by students, for the lecturer to fill in and publish.
"""

from django.db import transaction

from audit.services import record, snapshot
from courses import richtext
from courses.models import ContentItem, CourseSite, Module, SiteTemplate

WEEKS = 12


def gsa_standard(weeks: int = WEEKS) -> dict:
    """The GSA standard layout as a template structure."""

    def page(title: str, body: str) -> dict:
        return {"kind": "page", "title": title, "body": body}

    modules = [
        {
            "title": "Course overview",
            "items": [
                page(
                    "Welcome and how this course works",
                    "<p>Say who the course is for, how it is taught, and how students should work each "
                    "week.</p>",
                ),
                page(
                    "Your lecturer and how to reach them",
                    "<p>Give your name, office hours, and the best way to contact you.</p>",
                ),
            ],
        },
        {
            "title": "Course outline",
            "items": [
                page(
                    "Course outline",
                    "<h2>Aims</h2><p>What the course sets out to do.</p>"
                    "<h2>Learning outcomes</h2><ul><li>By the end of the course, students will be able "
                    "to ...</li></ul><h2>Schedule</h2><p>The topic of each week.</p>"
                    "<h2>Reading</h2><p>Books and other material, with where to find them.</p>",
                ),
            ],
        },
    ]
    for week in range(1, weeks + 1):
        modules.append(
            {
                "title": f"Week {week}",
                "items": [page(f"Week {week} notes", "<p>This week's topic, notes and tasks.</p>")],
            }
        )
    modules.append(
        {
            "title": "Assessment",
            "items": [
                page(
                    "How you are assessed",
                    "<p>The coursework, its weights and dates, and how the coursework mark is combined "
                    "with the examination.</p>",
                )
            ],
        }
    )
    return {"modules": modules}


def default_template() -> SiteTemplate | None:
    return SiteTemplate.objects.filter(is_default=True).first()


@transaction.atomic
def apply_template(site: CourseSite, template: SiteTemplate | None = None, request=None) -> int:
    """Give an empty site the template's modules and draft pages. Returns the modules made; a site that
    already has a module is left alone."""
    template = template or default_template()
    if template is None or site.modules.exists():
        return 0
    user = getattr(request, "user", None)
    user = user if user is not None and getattr(user, "pk", None) else None
    made = 0
    for position, spec in enumerate(template.structure.get("modules", []), start=1):
        module = Module.objects.create(
            site=site, title=spec["title"][:160], position=position, created_by=user, updated_by=user
        )
        record(request, "create", module, after={**snapshot(module), "template": template.name})
        for order, item in enumerate(spec.get("items", []), start=1):
            created = ContentItem.objects.create(
                module=module,
                kind=ContentItem.Kind.PAGE,
                title=item["title"][:160],
                body=richtext.clean(item.get("body", "")),
                position=order,
                is_published=False,
                licence=ContentItem.Licence.GSA_OWN,
                created_by=user,
                updated_by=user,
            )
            record(request, "create", created, after=snapshot(created))
        made += 1
    return made
