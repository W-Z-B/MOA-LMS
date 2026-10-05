"""Marking with a rubric or a marking guide (items 3.09, 3.10), and who may keep rubrics."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from rest_framework import serializers

from courses.access import can_teach, person_of
from courses.models import Membership
from iam.models import Role
from iam.services import SITE_ADMIN_ROLES, has_role
from rubrics.models import Rubric, RubricCriterion, RubricLevel

TWO_PLACES = Decimal("0.01")


def teaches_anywhere(user) -> bool:
    person = person_of(user)
    return has_role(user, Role.LECTURER) or (
        person is not None
        and Membership.objects.filter(
            person=person,
            is_active=True,
            role__in=[Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT],
        ).exists()
    )


def can_manage(user, rubric: Rubric) -> bool:
    """A site's rubrics: its teaching staff. The GSA library: course administrators."""
    if rubric.site_id:
        return can_teach(user, rubric.site)
    return has_role(user, *SITE_ADMIN_ROLES)


def can_read(user, rubric: Rubric) -> bool:
    """The library is open to everyone who teaches; a site's rubrics to its teaching staff."""
    if rubric.site_id:
        return can_teach(user, rubric.site)
    return has_role(user, *SITE_ADMIN_ROLES) or teaches_anywhere(user)


def in_use(rubric: Rubric) -> bool:
    """Marks have been given with it: it can no longer change, so the evidence of how work was marked stays
    true (item 3.19). Copy it to change it."""
    from assessments.models import Mark

    return Mark.objects.filter(submission__assignment__rubric=rubric).exclude(rubric_scores=[]).exists()


def replace_criteria(rubric: Rubric, criteria: list[dict]) -> None:
    with transaction.atomic():
        rubric.criteria.all().delete()
        for position, row in enumerate(criteria, start=1):
            criterion = RubricCriterion.objects.create(
                rubric=rubric,
                position=position,
                title=row["title"],
                description=row.get("description", ""),
                max_points=row.get("max_points") if rubric.kind == Rubric.Kind.GUIDE else None,
            )
            for level_position, level in enumerate(row.get("levels") or [], start=1):
                RubricLevel.objects.create(
                    criterion=criterion,
                    position=level_position,
                    points=level.get("points") or 0 if rubric.kind == Rubric.Kind.SCORED else 0,
                    description=level["description"],
                )


def copy_rubric(rubric: Rubric, site, user) -> Rubric:
    copy = Rubric.objects.create(
        site=site,
        title=rubric.title,
        description=rubric.description,
        kind=rubric.kind,
        copied_from=rubric,
        created_by=user,
        updated_by=user,
    )
    replace_criteria(
        copy,
        [
            {
                "title": c.title,
                "description": c.description,
                "max_points": c.max_points,
                "levels": [{"points": lv.points, "description": lv.description} for lv in c.levels.all()],
            }
            for c in rubric.criteria.prefetch_related("levels")
        ],
    )
    return copy


def score(rubric: Rubric, scores: list[dict], max_mark: Decimal) -> tuple[Decimal | None, list[dict]]:
    """Check a marker's scores against the rubric. Returns the mark it fills (None for a descriptive rubric,
    where the marker gives the mark) and the scores as they are kept with the mark.

    Every criterion must be scored once: a level of that criterion for a rubric, points from 0 to the
    criterion's maximum for a marking guide. The points are scaled to the assignment's maximum mark.
    """
    criteria = {c.id: c for c in rubric.criteria.prefetch_related("levels")}
    given = {}
    for row in scores:
        criterion = criteria.get(row.get("criterion"))
        if criterion is None:
            raise serializers.ValidationError(
                {"scores": [f"Criterion {row.get('criterion')} is not in this rubric."]}
            )
        if criterion.id in given:
            raise serializers.ValidationError({"scores": [f"'{criterion.title}' is scored twice."]})
        comment = str(row.get("comment") or "")[:2000]
        if rubric.kind == Rubric.Kind.GUIDE:
            try:
                points = Decimal(str(row.get("points")))
            except Exception as error:  # noqa: BLE001 - any unreadable number is the same refusal
                raise serializers.ValidationError(
                    {"scores": [f"Give points for '{criterion.title}'."]}
                ) from error
            if points < 0 or points > criterion.max_points:
                raise serializers.ValidationError(
                    {"scores": [f"'{criterion.title}' takes 0 to {criterion.max_points} points."]}
                )
            given[criterion.id] = {
                "criterion": criterion.id,
                "level": None,
                "points": str(points),
                "comment": comment,
            }
        else:
            level = next((lv for lv in criterion.levels.all() if lv.id == row.get("level")), None)
            if level is None:
                raise serializers.ValidationError(
                    {"scores": [f"Choose one of the levels of '{criterion.title}'."]}
                )
            given[criterion.id] = {
                "criterion": criterion.id,
                "level": level.id,
                "points": str(level.points) if rubric.kind == Rubric.Kind.SCORED else None,
                "comment": comment,
            }
    missing = [c.title for c_id, c in criteria.items() if c_id not in given]
    if missing:
        raise serializers.ValidationError({"scores": [f"Score every criterion: {', '.join(missing)}."]})
    kept = [given[c_id] for c_id in criteria]
    if rubric.kind == Rubric.Kind.DESCRIPTIVE:
        return None, kept
    total = sum((Decimal(row["points"]) for row in kept), Decimal(0))
    possible = rubric.max_points()
    if not possible:
        return Decimal(0), kept
    return (total / possible * max_mark).quantize(TWO_PLACES, rounding=ROUND_HALF_UP), kept
