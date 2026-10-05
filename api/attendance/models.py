"""Classes and attendance (items 4.14 and 4.15, decision D6 / ADR 0008).

A class session is a lecture, a practical or a field visit at a time: in a room, at a place, or online by a
meeting link (any meeting service GSA uses), with the recording added afterwards. It is shown on the
calendar. Attendance is recorded against it: by the lecturer on a phone, or by students scanning a code
shown in the room. The totals go to the SRMS for courses whose programme makes attendance a condition.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


def https_only(value: str) -> None:
    if value and not value.lower().startswith("https://"):
        raise ValidationError("Give a secure web address, starting https://.")


class ClassSession(TimeStampedModel):
    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="class_sessions")
    group = models.ForeignKey(
        "courses.SiteGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="For one group only (a lab or field group); empty for the whole class",
    )
    title = models.CharField(max_length=160)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    location = models.CharField(max_length=160, blank=True, help_text="Room, laboratory, farm or plot")
    meeting_url = models.URLField(max_length=500, blank=True, validators=[https_only])
    recording_url = models.URLField(
        max_length=500, blank=True, validators=[https_only], help_text="Added after the class"
    )
    takes_attendance = models.BooleanField(default=True)

    class Meta:
        ordering = ["starts_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="class_session_order")
        ]

    def __str__(self) -> str:
        return f"{self.site.code}: {self.title}"


class AttendanceRecord(TimeStampedModel):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"
        ABSENT = "absent", "Absent"

    class How(models.TextChoices):
        REGISTER = "register", "Marked by teaching staff"
        CHECK_IN = "check_in", "Checked in with the code in the room"
        CLOSED = "closed", "Absent when the register was closed"

    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name="records")
    student = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="attendance")
    status = models.CharField(max_length=10, choices=Status.choices)
    how = models.CharField(max_length=10, choices=How.choices)
    acted_at = models.DateTimeField(
        help_text="When the person acted: the phone's time for a register taken offline, else the server's"
    )
    client_recorded_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["session", "student__last_name"]
        constraints = [
            models.UniqueConstraint(fields=["session", "student"], name="attendance_once_per_session")
        ]

    def __str__(self) -> str:
        return f"{self.student} {self.status} at {self.session}"

    @property
    def person_id(self) -> int:  # the audit log's subject (audit.services.subject_of)
        return self.student_id


class AttendancePolicy(TimeStampedModel):
    """Whether a course's programme makes attendance a condition, so that its totals go to the SRMS."""

    site = models.OneToOneField(
        "courses.CourseSite", on_delete=models.CASCADE, related_name="attendance_policy"
    )
    send_to_srms = models.BooleanField(default=False, help_text="The programme makes attendance a condition")
    minimum_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="The programme's minimum, if any"
    )
    last_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Attendance policy of {self.site.code}"
