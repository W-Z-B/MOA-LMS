"""Who may assess on a site: its teaching staff (courses.access.can_teach) and the field instructors or
assessors named on it (PracticalAssessor). Sign-off and release stay with the teaching staff."""

from django.db.models import Q

from courses.access import can_teach, person_of, taught_sites
from courses.models import CourseSite
from practicals.models import PracticalAssessor


def named_assessor(user, site) -> bool:
    person = person_of(user)
    return (
        person is not None
        and PracticalAssessor.objects.filter(site=site, person=person, is_active=True).exists()
    )


def can_assess(user, site) -> bool:
    return can_teach(user, site) or named_assessor(user, site)


def named_sites(user):
    """Sites on which the user is a named assessor."""
    person = person_of(user)
    if person is None:
        return CourseSite.objects.none()
    return CourseSite.objects.filter(practical_assessors__person=person, practical_assessors__is_active=True)


def assessed_sites(user):
    """Sites the user may assess on: those they teach and those they are named on."""
    return CourseSite.objects.filter(
        Q(pk__in=taught_sites(user).values("pk")) | Q(pk__in=named_sites(user).values("pk"))
    )
