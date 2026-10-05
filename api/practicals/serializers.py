"""Serializers for practical tasks, observations, competency records and the logbook."""

import json

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from core.uploads import original_name, validate_upload
from courses.access import TaughtRecord, site_role, visible_sites
from courses.models import CourseSite, Membership
from people.models import PersonRef
from practicals.access import can_assess, named_sites
from practicals.models import (
    CompetencyElement,
    CompetencyFramework,
    CompetencyResult,
    CompetencyUnit,
    LogbookEntry,
    Observation,
    PerformanceCriterion,
    PracticalAssessor,
    PracticalCriterion,
    PracticalTask,
    SiteFramework,
)
from practicals.offline import check_client_time
from practicals.uploads import EVIDENCE, MAX_PHOTOS_PER_REQUEST

PHOTOS_HELP = (
    f"Up to {MAX_PHOTOS_PER_REQUEST} files, each a photograph (JPG, PNG, WEBP or HEIC) or a PDF, at most "
    "UPLOAD_LIMIT_EVIDENCE_MB (15 MB by default)"
)


def _filename(photo) -> str:
    return photo.original_name or photo.file.name.rsplit("/", 1)[-1]


def validate_photos(photos):
    if len(photos) > MAX_PHOTOS_PER_REQUEST:
        raise serializers.ValidationError(f"Send at most {MAX_PHOTOS_PER_REQUEST} files at a time.")
    return [validate_upload(p, EVIDENCE) for p in photos]


class PhotosSerializer(serializers.Serializer):
    photos = serializers.ListField(child=serializers.FileField(), allow_empty=False, help_text=PHOTOS_HELP)

    def validate_photos(self, photos):
        return validate_photos(photos)


class PhotoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    filename = serializers.CharField()
    download_url = serializers.CharField()


def photo_rows(photos, prefix: str) -> list[dict]:
    return [
        {"id": p.id, "filename": _filename(p), "download_url": f"/api/v1/{prefix}/{p.id}/download/"}
        for p in photos
    ]


class Latitude(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(
            max_digits=9,
            decimal_places=6,
            min_value=-90,
            max_value=90,
            required=False,
            allow_null=True,
            **kwargs,
        )


class Longitude(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(
            max_digits=9,
            decimal_places=6,
            min_value=-180,
            max_value=180,
            required=False,
            allow_null=True,
            **kwargs,
        )


@extend_schema_field(OpenApiTypes.INT)
class AssessedSite(serializers.PrimaryKeyRelatedField):
    """A site named by id in a write that its assessors make (teaching staff and named assessors). Settled
    before any other field, as courses.access.TaughtRecord: a site the caller cannot open reads as "does not
    exist"; one they can open but do not assess on is refused."""

    def get_queryset(self):
        request = self.context.get("request")
        if request is None:
            return CourseSite.objects.none()
        user = request.user
        return CourseSite.objects.filter(pk__in=visible_sites(user).values("pk")) | CourseSite.objects.filter(
            pk__in=named_sites(user).values("pk")
        )

    def to_internal_value(self, data):
        site = super().to_internal_value(data)
        if not can_assess(self.context["request"].user, site):
            raise PermissionDenied("Only the site's teaching staff and named assessors can do this.")
        return site


def site_student(site, person_id):
    """An active student of the site, or a "does not exist" refusal for any other id."""
    membership = Membership.objects.filter(
        site=site, person_id=person_id, is_active=True, role=Membership.SiteRole.STUDENT
    ).select_related("person")
    found = membership.first()
    if found is None:
        raise serializers.ValidationError({"student": [f'Invalid pk "{person_id}" - object does not exist.']})
    return found.person


# ---- Assessors and tasks ---------------------------------------------------------------------------------


class PracticalAssessorSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)
    person = serializers.PrimaryKeyRelatedField(
        queryset=PersonRef.objects.filter(kind=PersonRef.Kind.STAFF, is_active=True),
        help_text="A member of staff (HRMS employee) by LMS person id",
    )
    person_name = serializers.CharField(source="person.full_name", read_only=True)
    employee_no = serializers.CharField(source="person.external_id", read_only=True)

    class Meta:
        model = PracticalAssessor
        fields = ("id", "site", "person", "person_name", "employee_no", "note", "is_active")


class PracticalCriterionSerializer(serializers.ModelSerializer):
    task = TaughtRecord(PracticalTask, "site")
    performance_criteria = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=PerformanceCriterion.objects.all(),
        help_text="Performance criteria, of the frameworks the site follows, that this criterion "
        "gives evidence for",
    )

    class Meta:
        model = PracticalCriterion
        fields = (
            "id",
            "task",
            "position",
            "text",
            "kind",
            "max_score",
            "pass_score",
            "is_critical",
            "performance_criteria",
        )

    def validate(self, attrs):
        task = attrs.get("task") or self.instance.task
        kind = attrs.get("kind", getattr(self.instance, "kind", PracticalCriterion.Kind.PASS_FAIL))
        if kind == PracticalCriterion.Kind.PASS_FAIL:
            attrs["max_score"] = attrs["pass_score"] = 1
        else:
            max_score = attrs.get("max_score", getattr(self.instance, "max_score", 1))
            pass_score = attrs.get("pass_score", getattr(self.instance, "pass_score", 1))
            if max_score < 1:
                raise serializers.ValidationError(
                    {"max_score": ["A scored criterion needs a maximum of 1 or more."]}
                )
            if not 1 <= pass_score <= max_score:
                raise serializers.ValidationError(
                    {"pass_score": [f"Give a pass score from 1 to {max_score}."]}
                )
        allowed = set(SiteFramework.objects.filter(site=task.site).values_list("framework_id", flat=True))
        for pc in attrs.get("performance_criteria", []):
            if pc.element.unit.framework_id not in allowed:
                raise serializers.ValidationError(
                    {"performance_criteria": [f"{pc.code} is not in a framework this site follows."]}
                )
        return attrs


class PracticalTaskSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)
    criteria = serializers.SerializerMethodField()
    counts_in_coursework = serializers.SerializerMethodField()

    class Meta:
        model = PracticalTask
        fields = (
            "id",
            "site",
            "title",
            "instructions",
            "unit_type",
            "location",
            "weight",
            "counts_in_coursework",
            "opens_at",
            "closes_at",
            "max_attempts",
            "is_published",
            "criteria",
        )

    def get_criteria(self, obj) -> list[dict]:
        return [
            {
                "id": c.id,
                "position": c.position,
                "text": c.text,
                "kind": c.kind,
                "max_score": c.max_score,
                "pass_score": c.pass_score,
                "is_critical": c.is_critical,
                "performance_criteria": [pc.id for pc in c.performance_criteria.all()],
            }
            for c in obj.criteria.all()
        ]

    def get_counts_in_coursework(self, obj) -> bool:
        return obj.weight > 0

    def validate(self, attrs):
        opens = attrs.get("opens_at", getattr(self.instance, "opens_at", None))
        closes = attrs.get("closes_at", getattr(self.instance, "closes_at", None))
        if opens and closes and closes <= opens:
            raise serializers.ValidationError({"closes_at": ["The task must close after it opens."]})
        return attrs


# ---- Observations --------------------------------------------------------------------------------------


class ResultInput(serializers.Serializer):
    criterion = serializers.IntegerField()
    passed = serializers.BooleanField(
        required=False, allow_null=True, default=None, help_text="Pass or fail criteria"
    )
    score = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, help_text="Scored criteria"
    )
    comment = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class ResultsField(serializers.ListField):
    """The checklist as a list, or, in a multipart form sent with photographs, as that list in JSON."""

    child = ResultInput()

    def to_internal_value(self, data):
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], str):
            data = data[0]
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                raise serializers.ValidationError("Send the results as a JSON list.") from None
        return super().to_internal_value(data)


def checked_results(task, results) -> list[dict]:
    """Every criterion of the task once, each with a result of the right kind; pass worked out for scores."""
    criteria = {c.id: c for c in task.criteria.all()}
    seen = set()
    rows = []
    for row in results:
        criterion = criteria.get(row["criterion"])
        if criterion is None:
            raise serializers.ValidationError(
                {"results": [f"Criterion {row['criterion']} is not on this task."]}
            )
        if criterion.id in seen:
            raise serializers.ValidationError({"results": [f"Criterion {criterion.id} is given twice."]})
        seen.add(criterion.id)
        if criterion.kind == PracticalCriterion.Kind.SCORED:
            score = row.get("score")
            if score is None or score > criterion.max_score:
                raise serializers.ValidationError(
                    {"results": [f'Give "{criterion.text}" a score from 0 to {criterion.max_score}.']}
                )
            passed = score >= criterion.pass_score
        else:
            if row.get("passed") is None:
                raise serializers.ValidationError({"results": [f'Mark "{criterion.text}" as passed or not.']})
            passed, score = row["passed"], None
        rows.append(
            {"criterion": criterion, "passed": passed, "score": score, "comment": row.get("comment", "")}
        )
    left = [c.text for cid, c in criteria.items() if cid not in seen]
    if left:
        raise serializers.ValidationError(
            {"results": ["Every criterion needs a result. Missing: " + "; ".join(left)]}
        )
    return rows


class ObservationWriteSerializer(serializers.Serializer):
    student = serializers.IntegerField(help_text="The student's LMS person id; an active student of the site")
    observed_at = serializers.DateTimeField(
        help_text="When it was observed, by the phone's clock: no more than 7 days ago or 10 minutes ahead"
    )
    latitude = Latitude()
    longitude = Longitude()
    location_text = serializers.CharField(required=False, allow_blank=True, max_length=160)
    comments = serializers.CharField(required=False, allow_blank=True)
    results = ResultsField(help_text="One result for every criterion of the task")
    photos = serializers.ListField(child=serializers.FileField(), required=False, help_text=PHOTOS_HELP)

    def validate_observed_at(self, value):
        return check_client_time(value)

    def validate_photos(self, photos):
        return validate_photos(photos)

    def validate(self, attrs):
        task = self.context["task"]
        attrs["student"] = site_student(task.site, attrs["student"])
        if (attrs.get("latitude") is None) != (attrs.get("longitude") is None):
            raise serializers.ValidationError({"latitude": ["Send both latitude and longitude, or neither."]})
        attrs["results"] = checked_results(task, attrs["results"])
        return attrs


class ObservationUpdateSerializer(serializers.Serializer):
    """Corrections before release. The checklist, when sent, is sent whole."""

    comments = serializers.CharField(required=False, allow_blank=True)
    location_text = serializers.CharField(required=False, allow_blank=True, max_length=160)
    results = ResultsField(required=False)

    def validate(self, attrs):
        if "results" in attrs:
            attrs["results"] = checked_results(self.context["task"], attrs["results"])
        return attrs


class ObservationSerializer(serializers.ModelSerializer):
    task_title = serializers.CharField(source="task.title", read_only=True)
    site = serializers.IntegerField(source="task.site_id", read_only=True)
    student_no = serializers.CharField(source="student.external_id", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    assessor_name = serializers.CharField(source="assessor.full_name", read_only=True)
    results = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    critical_passed = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()

    class Meta:
        model = Observation
        fields = (
            "id",
            "task",
            "task_title",
            "site",
            "student",
            "student_no",
            "student_name",
            "attempt",
            "assessor_name",
            "observed_at",
            "recorded_at",
            "latitude",
            "longitude",
            "location_text",
            "comments",
            "results",
            "score",
            "critical_passed",
            "photos",
            "is_released",
            "released_at",
        )

    def get_results(self, obj) -> list[dict]:
        return [
            {
                "criterion": r.criterion_id,
                "text": r.criterion.text,
                "kind": r.criterion.kind,
                "is_critical": r.criterion.is_critical,
                "max_score": r.criterion.max_score,
                "passed": r.passed,
                "score": r.score,
                "comment": r.comment,
            }
            for r in obj.results.select_related("criterion")
        ]

    def get_score(self, obj) -> dict:
        earned, possible = obj.score()
        return {"earned": earned, "possible": possible}

    def get_critical_passed(self, obj) -> bool:
        return obj.critical_passed()

    @extend_schema_field(PhotoSerializer(many=True))
    def get_photos(self, obj):
        return photo_rows(obj.photos.all(), "observation-photos")


# ---- Competency frameworks and results ----------------------------------------------------------------


class FrameworkSerializer(serializers.ModelSerializer):
    units = serializers.SerializerMethodField()

    class Meta:
        model = CompetencyFramework
        fields = ("id", "code", "title", "source", "version", "is_active", "units")

    def get_units(self, obj) -> list[dict]:
        if not self.context.get("with_units", True):
            return []
        return [
            {
                "id": u.id,
                "code": u.code,
                "title": u.title,
                "elements": [
                    {
                        "id": e.id,
                        "code": e.code,
                        "title": e.title,
                        "criteria": [
                            {"id": pc.id, "code": pc.code, "text": pc.text} for pc in e.criteria.all()
                        ],
                    }
                    for e in u.elements.all()
                ],
            }
            for u in obj.units.prefetch_related("elements__criteria")
        ]


class ImportCriterion(serializers.Serializer):
    code = serializers.CharField(max_length=40)
    text = serializers.CharField(max_length=500)


class ImportElement(serializers.Serializer):
    code = serializers.CharField(max_length=40)
    title = serializers.CharField(max_length=300)
    criteria = ImportCriterion(many=True, allow_empty=False)


class ImportUnit(serializers.Serializer):
    code = serializers.CharField(max_length=40)
    title = serializers.CharField(max_length=300)
    elements = ImportElement(many=True, allow_empty=False)


CSV_COLUMNS = ("unit_code", "unit_title", "element_code", "element_title", "criterion_code", "criterion_text")


class FrameworkImportSerializer(serializers.Serializer):
    """A framework as JSON (units -> elements -> criteria), or the same fields with a CSV file of one row per
    performance criterion:
    unit_code, unit_title, element_code, element_title, criterion_code, criterion_text."""

    code = serializers.CharField(max_length=40)
    title = serializers.CharField(max_length=200)
    source = serializers.CharField(max_length=200, required=False, allow_blank=True)
    version = serializers.CharField(max_length=20, required=False, default="1")
    units = ImportUnit(many=True, required=False)
    csv = serializers.FileField(required=False, help_text="UTF-8 CSV with a header row; see the description")

    def validate_csv(self, upload):
        import csv
        import io

        if upload.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("The CSV file is larger than 2 MB.")
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise serializers.ValidationError("Save the CSV file as UTF-8 and send it again.") from None
        reader = csv.DictReader(io.StringIO(text))
        if tuple(reader.fieldnames or ())[: len(CSV_COLUMNS)] != CSV_COLUMNS:
            raise serializers.ValidationError("The first row must be: " + ", ".join(CSV_COLUMNS) + ".")
        units: dict[str, dict] = {}
        for number, row in enumerate(reader, start=2):
            if any(not (row.get(col) or "").strip() for col in CSV_COLUMNS):
                raise serializers.ValidationError(f"Row {number} has an empty cell.")
            unit = units.setdefault(
                row["unit_code"].strip(), {"title": row["unit_title"].strip(), "elements": {}}
            )
            element = unit["elements"].setdefault(
                row["element_code"].strip(), {"title": row["element_title"].strip(), "criteria": []}
            )
            element["criteria"].append(
                {"code": row["criterion_code"].strip(), "text": row["criterion_text"].strip()}
            )
        tree = [
            {
                "code": code,
                "title": u["title"],
                "elements": [
                    {"code": ec, "title": e["title"], "criteria": e["criteria"]}
                    for ec, e in u["elements"].items()
                ],
            }
            for code, u in units.items()
        ]
        checked = ImportUnit(data=tree, many=True)
        checked.is_valid(raise_exception=True)
        return checked.validated_data

    def validate(self, attrs):
        units = attrs.pop("csv", None) or attrs.get("units")
        if not units:
            raise serializers.ValidationError("Send the units, or a CSV file of them.")
        attrs["units"] = units
        if CompetencyFramework.objects.filter(code=attrs["code"], version=attrs["version"]).exists():
            raise serializers.ValidationError(
                {
                    "version": [
                        "This version of the framework is already here. Import the new version under its "
                        "own number."
                    ]
                }
            )
        return attrs

    def create(self, validated_data):
        units = validated_data.pop("units")
        framework = CompetencyFramework.objects.create(**validated_data)
        for u_pos, u in enumerate(units, start=1):
            unit = CompetencyUnit.objects.create(
                framework=framework, code=u["code"], title=u["title"], position=u_pos
            )
            for e_pos, e in enumerate(u["elements"], start=1):
                element = CompetencyElement.objects.create(
                    unit=unit, code=e["code"], title=e["title"], position=e_pos
                )
                PerformanceCriterion.objects.bulk_create(
                    PerformanceCriterion(element=element, code=c["code"], text=c["text"], position=c_pos)
                    for c_pos, c in enumerate(e["criteria"], start=1)
                )
        return framework


class SiteFrameworkSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)
    framework = serializers.PrimaryKeyRelatedField(
        queryset=CompetencyFramework.objects.filter(is_active=True)
    )
    framework_title = serializers.CharField(source="framework.__str__", read_only=True)

    class Meta:
        model = SiteFramework
        fields = ("id", "site", "framework", "framework_title")
        validators = []  # the pair is checked in validate, so the site is settled first

    def validate(self, attrs):
        if SiteFramework.objects.filter(site=attrs["site"], framework=attrs["framework"]).exists():
            raise serializers.ValidationError({"framework": ["The site already follows this framework."]})
        return attrs


class CompetencyResultSerializer(serializers.ModelSerializer):
    site = AssessedSite()
    student = serializers.IntegerField(source="student_id", help_text="The student's LMS person id")
    unit = serializers.PrimaryKeyRelatedField(queryset=CompetencyUnit.objects.all())
    decided_on = serializers.DateField(required=False)
    client_recorded_at = serializers.DateTimeField(
        required=False, allow_null=True, help_text="When it was recorded, by the phone's clock"
    )
    evidence_observations = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Observation.objects.all(), help_text="Released observations"
    )
    evidence_submissions = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        source="evidence_submission_ids",
        help_text="Submissions (assessments) by the student on this site",
    )
    student_no = serializers.CharField(source="student.external_id", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    unit_title = serializers.CharField(source="unit.title", read_only=True)
    assessor_name = serializers.CharField(source="assessor.full_name", read_only=True)

    class Meta:
        model = CompetencyResult
        fields = (
            "id",
            "site",
            "student",
            "student_no",
            "student_name",
            "unit",
            "unit_code",
            "unit_title",
            "status",
            "decided_on",
            "comments",
            "client_recorded_at",
            "evidence_observations",
            "evidence_submissions",
            "assessor_name",
            "updated_at",
        )
        read_only_fields = ("updated_at",)
        validators = []  # one row per site, student and unit: the view records over the existing one

    def validate_client_recorded_at(self, value):
        return check_client_time(value)

    def validate(self, attrs):
        from assessments.models import Submission

        site = attrs["site"]
        attrs["student"] = student = site_student(site, attrs.pop("student_id"))
        if not SiteFramework.objects.filter(site=site, framework_id=attrs["unit"].framework_id).exists():
            raise serializers.ValidationError({"unit": ["This unit is not in a framework the site follows."]})
        for observation in attrs.get("evidence_observations", []):
            if (
                observation.task.site_id != site.id
                or observation.student_id != student.id
                or not observation.is_released
            ):
                raise serializers.ValidationError(
                    {
                        "evidence_observations": [
                            f"Observation {observation.id} is not a released observation of this "
                            "student on this site."
                        ]
                    }
                )
        submission_ids = attrs.get("evidence_submission_ids", [])
        found = set(
            Submission.objects.filter(
                pk__in=submission_ids, student=student, assignment__site=site
            ).values_list("pk", flat=True)
        )
        if set(submission_ids) - found:
            raise serializers.ValidationError(
                {"evidence_submissions": ["Each submission must be the student's own work on this site."]}
            )
        attrs.setdefault("decided_on", timezone.localdate())
        return attrs


class AssignmentMapSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    assignment = serializers.IntegerField(source="assignment_id", help_text="An assignment id (assessments)")
    performance_criterion = serializers.PrimaryKeyRelatedField(queryset=PerformanceCriterion.objects.all())
    site = serializers.IntegerField(source="site_id", read_only=True)


# ---- Logbook ------------------------------------------------------------------------------------------


@extend_schema_field(OpenApiTypes.INT)
class StudentSite(serializers.PrimaryKeyRelatedField):
    """The site a logbook entry is kept on: settled before any other field. A site the caller cannot open
    reads as "does not exist"; one they can open but are not a student of is refused."""

    def get_queryset(self):
        request = self.context.get("request")
        return visible_sites(request.user) if request is not None else CourseSite.objects.none()

    def to_internal_value(self, data):
        site = super().to_internal_value(data)
        if site_role(self.context["request"].user, site) != Membership.SiteRole.STUDENT:
            raise PermissionDenied("Only students of this course keep a logbook on it.")
        return site


class LogbookEntrySerializer(serializers.ModelSerializer):
    site = StudentSite()
    latitude = Latitude()
    longitude = Longitude()
    client_recorded_at = serializers.DateTimeField(
        help_text="When it was written, by the phone's clock: no more than 7 days ago or 10 minutes ahead"
    )
    photos = serializers.ListField(
        child=serializers.FileField(), required=False, write_only=True, help_text=PHOTOS_HELP
    )
    photo_files = serializers.SerializerMethodField()
    student_no = serializers.CharField(source="student.external_id", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    supervisor_name = serializers.CharField(source="supervisor.full_name", read_only=True, default=None)

    class Meta:
        model = LogbookEntry
        fields = (
            "id",
            "site",
            "student_no",
            "student_name",
            "work_date",
            "unit_type",
            "unit_text",
            "task",
            "hours",
            "notes",
            "latitude",
            "longitude",
            "client_recorded_at",
            "created_at",
            "status",
            "supervisor_name",
            "reviewed_at",
            "review_comment",
            "photos",
            "photo_files",
        )
        read_only_fields = ("created_at", "status", "reviewed_at", "review_comment")

    @extend_schema_field(PhotoSerializer(many=True))
    def get_photo_files(self, obj):
        return photo_rows(obj.photos.all(), "logbook-photos")

    def validate_client_recorded_at(self, value):
        return check_client_time(value)

    def validate_photos(self, photos):
        return validate_photos(photos)

    def validate_hours(self, value):
        if not 0 < value <= 24:
            raise serializers.ValidationError("Give the hours worked that day, more than 0 and at most 24.")
        return value

    def validate_work_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("The work date cannot be in the future.")
        return value

    def validate(self, attrs):
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError({"latitude": ["Send both latitude and longitude, or neither."]})
        return attrs


class LogbookReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=[("sign", "Sign off"), ("return", "Return for correction")])
    comment = serializers.CharField(required=False, allow_blank=True)
    client_recorded_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_client_recorded_at(self, value):
        return check_client_time(value)

    def validate(self, attrs):
        if attrs["decision"] == "return" and not attrs.get("comment", "").strip():
            raise serializers.ValidationError({"comment": ["Say what needs correcting."]})
        return attrs


def store_photos(model, owner_field: str, owner, photos, user):
    return [
        model.objects.create(
            **{owner_field: owner}, file=p, original_name=original_name(p), created_by=user, updated_by=user
        )
        for p in photos
    ]
