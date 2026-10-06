"""The audit viewer (item 1.17): every entry with filters, a CSV export, and the state of the chain.

For the auditor and administrators. Exports and checks of the chain are themselves audited.
"""

import csv
from datetime import datetime, time

from django.db.models import OuterRef, Q, Subquery
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_field
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit import chain as audit_chain
from audit import words
from audit.models import AuditCheck, AuditLog
from audit.services import record_event
from core.serializers import ErrorSerializer
from iam.models import Role
from iam.permissions import RolePermission
from people.models import PersonRef

AUDIT_ROLES = (Role.ADMINISTRATOR, Role.AUDITOR)
EXPORT_LIMIT = 100_000
FILTERS = [
    OpenApiParameter("action", OpenApiTypes.STR, description="What was done, as stored (for example update)"),
    OpenApiParameter(
        "record", OpenApiTypes.STR, description="Kind of record, as stored (courses.coursesite)"
    ),
    OpenApiParameter("who", OpenApiTypes.STR, description="Part of the username or name of whoever did it"),
    OpenApiParameter("person", OpenApiTypes.STR, description="Entries about this employee or student number"),
    OpenApiParameter("since", OpenApiTypes.DATE, description="From this day (YYYY-MM-DD)"),
    OpenApiParameter("until", OpenApiTypes.DATE, description="To this day, inclusive"),
    OpenApiParameter("q", OpenApiTypes.STR, description="Words in the reason given"),
]
# Spreadsheet programs run a cell that starts with one of these as a formula.
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


class ChangeSerializer(serializers.Serializer):
    field = serializers.CharField()
    before = serializers.JSONField(allow_null=True)
    after = serializers.JSONField(allow_null=True)


class AuditEntrySerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    actor_username = serializers.CharField(source="actor.username", default=None, read_only=True)
    action_name = serializers.SerializerMethodField()
    record = serializers.SerializerMethodField()
    person_number = serializers.CharField(
        read_only=True, default=None, help_text="Employee or student number of the person it is about"
    )
    changes = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "at",
            "actor",
            "actor_username",
            "action",
            "action_name",
            "entity",
            "record",
            "entity_id",
            "subject",
            "person_number",
            "reason",
            "source_ip",
            "changes",
            "before",
            "after",
            "chain",
        )
        read_only_fields = fields

    def get_actor(self, row) -> str:
        return words.actor_name(row)

    def get_action_name(self, row) -> str:
        return words.action_name(row.action)

    def get_record(self, row) -> str:
        return words.record_name(row.entity)

    @extend_schema_field(ChangeSerializer(many=True))
    def get_changes(self, row):
        return words.changes(row.before, row.after)


class AuditCheckSerializer(serializers.ModelSerializer):
    checked_by = serializers.SerializerMethodField()

    class Meta:
        model = AuditCheck
        fields = ("id", "checked_at", "checked_by", "rows", "intact", "last_id", "first_broken_id", "detail")
        read_only_fields = fields

    def get_checked_by(self, check) -> str:
        user = check.checked_by
        return (user.get_full_name() or user.get_username()) if user else "The nightly check"


class ChainStateSerializer(serializers.Serializer):
    entries = serializers.IntegerField()
    newest = serializers.IntegerField(allow_null=True)
    latest_check = AuditCheckSerializer(allow_null=True)


class ChoiceSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class ChoicesSerializer(serializers.Serializer):
    actions = ChoiceSerializer(many=True)
    records = ChoiceSerializer(many=True)


def _filtered(queryset, params):
    if params.get("action"):
        queryset = queryset.filter(action=params["action"])
    if params.get("record"):
        queryset = queryset.filter(entity=params["record"])
    who = (params.get("who") or "").strip()
    if who:
        queryset = queryset.filter(
            Q(actor__username__icontains=who)
            | Q(actor__first_name__icontains=who)
            | Q(actor__last_name__icontains=who)
        )
    number = (params.get("person") or "").strip()
    if number:
        ids = list(PersonRef.objects.filter(external_id__iexact=number).values_list("pk", flat=True))
        queryset = queryset.filter(Q(subject__in=ids) | Q(entity="people.personref", entity_id__in=ids))
    for name, lookup, edge in (("since", "at__gte", time.min), ("until", "at__lte", time.max)):
        raw = params.get(name)
        if not raw:
            continue
        try:
            day = parse_date(raw)
        except ValueError:
            day = None
        if day is None:
            raise serializers.ValidationError({name: ["Give a date as YYYY-MM-DD."]})
        queryset = queryset.filter(**{lookup: timezone.make_aware(datetime.combine(day, edge))})
    text = (params.get("q") or "").strip()
    if text:
        queryset = queryset.filter(reason__icontains=text)
    return queryset


def _cell(value) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_START) else text


def _shown(value) -> str:
    if value is None or value == "":
        return "blank"
    return str(value)


class _Echo:
    """A file-like object whose write hands the line back, so the CSV can be streamed."""

    def write(self, value):
        return value


@extend_schema(parameters=FILTERS)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Every audit entry, newest first."""

    permission_classes = [RolePermission]
    read_roles = AUDIT_ROLES
    write_roles = AUDIT_ROLES
    serializer_class = AuditEntrySerializer
    queryset = AuditLog.objects.none()
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        number = PersonRef.objects.filter(pk=OuterRef("subject")).values("external_id")[:1]
        entries = AuditLog.objects.select_related("actor").annotate(person_number=Subquery(number))
        return _filtered(entries, self.request.query_params).order_by("-id")

    @extend_schema(
        parameters=FILTERS,
        responses={(200, "text/csv"): OpenApiResponse(OpenApiTypes.STR), 400: ErrorSerializer},
        summary="The entries that match, as a CSV file for a spreadsheet (the export is audited)",
    )
    @action(detail=False, methods=["get"])
    def export(self, request):
        entries = self.get_queryset()[:EXPORT_LIMIT]
        count = entries.count()
        filters = {key: value for key, value in request.query_params.items() if value}
        record_event(request, "audit_exported", "audit.auditlog", after={"filters": filters, "rows": count})

        def lines():
            writer = csv.writer(_Echo())
            yield "﻿"  # tells spreadsheet programs the file is UTF-8
            yield writer.writerow(
                [
                    "Entry",
                    "When",
                    "Who",
                    "Username",
                    "What",
                    "Record",
                    "Record id",
                    "Person number",
                    "Reason",
                    "Address",
                    "Changes",
                    "Fingerprint",
                ]
            )
            for row in entries.iterator(1000):
                changes = "; ".join(
                    f"{c['field']}: {_shown(c['before'])} → {_shown(c['after'])}"
                    for c in words.changes(row.before, row.after)
                )
                yield writer.writerow(
                    [
                        _cell(value)
                        for value in (
                            row.id,
                            timezone.localtime(row.at).strftime("%d/%m/%Y %H:%M:%S"),
                            words.actor_name(row),
                            row.actor.get_username() if row.actor else "",
                            words.action_name(row.action),
                            words.record_name(row.entity),
                            row.entity_id,
                            row.person_number,
                            row.reason,
                            row.source_ip,
                            changes,
                            row.chain,
                        )
                    ]
                )

        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        response = StreamingHttpResponse(lines(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="gsa-lms-audit-{stamp}.csv"'
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(
        methods=["GET"],
        responses=ChainStateSerializer,
        summary="Whether the log is intact, from the latest check",
    )
    @extend_schema(
        methods=["POST"],
        request=None,
        responses=ChainStateSerializer,
        summary="Check every entry against its fingerprint now (the check is audited)",
    )
    @action(detail=False, methods=["get", "post"])
    def chain(self, request):
        if request.method == "POST":
            check = audit_chain.verify(checked_by=request.user)
            record_event(
                request,
                "audit_checked",
                "audit.auditcheck",
                after={"check": check.id, "intact": check.intact, "rows": check.rows},
            )
        latest = AuditCheck.objects.select_related("checked_by").first()
        state = {
            "entries": AuditLog.objects.count(),
            "newest": AuditLog.objects.order_by("-id").values_list("id", flat=True).first(),
            "latest_check": latest,
        }
        return Response(ChainStateSerializer(state).data)

    @extend_schema(responses=ChoicesSerializer, summary="What has been done, and to which kinds of record")
    @action(detail=False, methods=["get"])
    def choices(self, request):
        actions = AuditLog.objects.order_by().values_list("action", flat=True).distinct()
        records = AuditLog.objects.order_by().values_list("entity", flat=True).distinct()
        payload = {
            "actions": sorted(
                ({"code": code, "name": words.action_name(code)} for code in actions),
                key=lambda c: c["name"],
            ),
            "records": sorted(
                ({"code": code, "name": words.record_name(code)} for code in records),
                key=lambda c: c["name"],
            ),
        }
        return Response(ChoicesSerializer(payload).data)
