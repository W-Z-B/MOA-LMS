"""The retention schedule, disposal runs and the breach register (item 1.19).

Administrators and the Data Protection Officer keep the schedule, propose runs and approve them; a run is
approved by someone other than whoever proposed it. The auditor reads everything. Every change is audited.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from core.views import AuditedModelViewSet
from iam.models import Role
from iam.permissions import RolePermission
from notifications.models import Notification
from notifications.services import notify, users_with_role
from privacy import retention
from privacy.models import Breach, DisposalItem, DisposalRun, RetentionRule

KEEPERS = (Role.ADMINISTRATOR, Role.DPO)
READERS = KEEPERS + (Role.AUDITOR,)


def _name(user) -> str | None:
    return (user.get_full_name() or user.get_username()) if user else None


class RuleSerializer(serializers.ModelSerializer):
    action_name = serializers.CharField(source="get_action_display", read_only=True)
    confirmed = serializers.SerializerMethodField()
    confirmed_by_name = serializers.SerializerMethodField()
    open_run = serializers.SerializerMethodField(help_text="The run waiting for approval, if any")

    class Meta:
        model = RetentionRule
        fields = (
            "id",
            "code",
            "name",
            "keep_months",
            "counted_from",
            "action",
            "action_name",
            "automatic",
            "confirmed",
            "confirmed_by_name",
            "confirmed_at",
            "note",
            "open_run",
        )
        read_only_fields = ("code", "name", "counted_from", "action", "automatic", "confirmed_at")

    def get_confirmed(self, rule) -> bool:
        return rule.confirmed_at is not None

    def get_confirmed_by_name(self, rule) -> str | None:
        return _name(rule.confirmed_by)

    def get_open_run(self, rule) -> int | None:
        run = rule.runs.filter(state=DisposalRun.State.PROPOSED).first()
        return run.id if run else None

    def validate_keep_months(self, value):
        if self.instance is not None and self.instance.keep_months is None and value is not None:
            raise serializers.ValidationError("This rule takes the date set on each record.")
        if value is not None and value < 1:
            raise serializers.ValidationError("Keep records for one month at least.")
        return value


class ItemSerializer(serializers.ModelSerializer):
    person_number = serializers.CharField(source="person.external_id", read_only=True, default=None)

    class Meta:
        model = DisposalItem
        fields = ("id", "description", "person", "person_number", "due_since", "keep_reason", "disposed_at")
        read_only_fields = fields


class RunSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    proposed_by = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    proposed_by_me = serializers.SerializerMethodField(help_text="So someone else must approve it")
    items = ItemSerializer(many=True, read_only=True)

    class Meta:
        model = DisposalRun
        fields = (
            "id",
            "rule",
            "rule_name",
            "state",
            "state_name",
            "created_at",
            "proposed_by",
            "approved_by_name",
            "approved_at",
            "proposed_by_me",
            "items",
        )
        read_only_fields = fields

    def get_proposed_by(self, run) -> str | None:
        return _name(run.created_by)

    def get_approved_by_name(self, run) -> str | None:
        return _name(run.approved_by)

    def get_proposed_by_me(self, run) -> bool:
        request = self.context.get("request")
        return bool(request) and run.created_by_id == request.user.pk


class FoundSerializer(serializers.Serializer):
    detail = serializers.CharField()
    run = RunSerializer(allow_null=True)


class KeepSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    reason = serializers.CharField(
        max_length=300, error_messages={"blank": "Say why it is kept.", "required": "Say why it is kept."}
    )


class BreachSerializer(serializers.ModelSerializer):
    risk_name = serializers.CharField(source="get_risk_display", read_only=True)
    recorded_by = serializers.SerializerMethodField()

    class Meta:
        model = Breach
        fields = (
            "id",
            "reference",
            "discovered_at",
            "happened",
            "summary",
            "data_affected",
            "people_affected",
            "minors_affected",
            "risk",
            "risk_name",
            "contained_at",
            "commissioner_told_at",
            "people_told_at",
            "actions",
            "closed_at",
            "recorded_by",
            "created_at",
        )
        read_only_fields = ("reference", "closed_at", "recorded_by", "created_at")

    def get_recorded_by(self, breach) -> str | None:
        return _name(breach.created_by)


class RuleViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """The retention schedule: what is kept, for how long, and what happens then."""

    permission_classes = [RolePermission]
    read_roles = READERS
    write_roles = KEEPERS
    serializer_class = RuleSerializer
    queryset = RetentionRule.objects.select_related("confirmed_by")
    http_method_names = ["get", "patch", "post", "head", "options"]
    pagination_class = None

    @transaction.atomic
    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        rule = serializer.save(confirmed_by=None, confirmed_at=None)  # a changed period is confirmed again
        record(self.request, "retention_changed", rule, before=before, after=snapshot(rule))

    @extend_schema(request=None, responses=RuleSerializer, summary="Confirm that GSA has agreed this period")
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        rule = self.get_object()
        with transaction.atomic():
            rule.confirmed_by = request.user
            rule.confirmed_at = timezone.now()
            rule.save(update_fields=["confirmed_by", "confirmed_at"])
            record(request, "retention_confirmed", rule, after={"keep_months": rule.keep_months})
        return Response(self.get_serializer(rule).data)

    @extend_schema(
        request=None,
        responses={200: FoundSerializer, 201: FoundSerializer, 409: ErrorSerializer},
        summary="List the records now due under this rule, for a second person to approve",
    )
    @action(detail=True, methods=["post"])
    def find(self, request, pk=None):
        rule = self.get_object()
        if rule.automatic:
            return Response(
                {
                    "code": "automatic",
                    "detail": "These records are removed every night; there is nothing to approve.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        if rule.action == RetentionRule.Action.REVIEW:
            return Response(
                {
                    "code": "review_only",
                    "detail": "GSA reviews these records itself; the system does not dispose of them.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        found = retention.due(rule)
        if not found:
            return Response({"detail": "Nothing is due under this rule.", "run": None})
        try:
            with transaction.atomic():
                run = DisposalRun.objects.create(rule=rule, created_by=request.user, updated_by=request.user)
                DisposalItem.objects.bulk_create(
                    DisposalItem(
                        run=run,
                        entity=d.entity,
                        entity_id=d.entity_id,
                        person_id=d.person_id,
                        description=d.description[:300],
                        due_since=d.due_since,
                    )
                    for d in found
                )
                record(request, "disposal_proposed", run, after={"rule": rule.code, "records": len(found)})
        except IntegrityError:
            return Response(
                {"code": "open_run", "detail": "A run for this rule is already waiting for approval."},
                status=status.HTTP_409_CONFLICT,
            )
        approvers = {u for code in KEEPERS for u in users_with_role(code) if u.pk != request.user.pk}
        notify(
            approvers,
            title=f"Records to dispose of: {rule.name}",
            body=f"{len(found)} records are past their retention period. A second person approves disposal.",
            link="/admin/retention",
            kind=Notification.Kind.APPROVAL,
            dedupe_key=f"disposal:{run.id}",
        )
        run = DisposalRun.objects.prefetch_related("items__person").get(pk=run.pk)
        detail = f"{len(found)} records are due. Someone else approves before anything is destroyed."
        data = RunSerializer(run, context={"request": request}).data
        return Response({"detail": detail, "run": data}, status=status.HTTP_201_CREATED)


class RunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Disposal runs: proposed, then approved by a second person, or cancelled."""

    permission_classes = [RolePermission]
    read_roles = READERS
    write_roles = KEEPERS
    serializer_class = RunSerializer
    queryset = DisposalRun.objects.select_related("rule", "created_by", "approved_by").prefetch_related(
        "items__person"
    )

    def _open(self, request):
        run = self.get_object()
        if run.state != DisposalRun.State.PROPOSED:
            return run, Response(
                {"code": "decided", "detail": "This run has been decided."}, status=status.HTTP_409_CONFLICT
            )
        return run, None

    @extend_schema(
        request=KeepSerializer,
        responses={200: RunSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
        summary="Keep one record after all, saying why (a legal hold)",
    )
    @action(detail=True, methods=["post"])
    def keep(self, request, pk=None):
        run, refusal = self._open(request)
        if refusal:
            return refusal
        data = KeepSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        item = run.items.filter(pk=data.validated_data["item"]).first()
        if item is None:
            return Response({"code": "not_found", "detail": "No such record in this run."}, status=404)
        with transaction.atomic():
            item.keep_reason = data.validated_data["reason"].strip()
            item.save(update_fields=["keep_reason"])
            record(request, "disposal_kept", run, after={"item": item.description}, reason=item.keep_reason)
        return Response(self.get_serializer(self.get_queryset().get(pk=run.pk)).data)

    @extend_schema(
        request=None,
        responses={200: RunSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Approve the run: every record not kept is destroyed, and each one is recorded",
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        run, refusal = self._open(request)
        if refusal:
            return refusal
        if run.created_by_id == request.user.pk:
            return Response(
                {"code": "same_person", "detail": "A second person approves: you proposed this run."},
                status=status.HTTP_403_FORBIDDEN,
            )
        today = timezone.localdate()
        disposed = kept = 0
        with transaction.atomic():
            for item in run.items.select_for_update():
                if item.keep_reason:
                    kept += 1
                elif not retention.still_due(item, run.rule, today):
                    item.keep_reason = "No longer due when the run was approved"
                    item.save(update_fields=["keep_reason"])
                    kept += 1
                else:
                    retention.dispose(request, item, run.rule)
                    disposed += 1
            run.state = DisposalRun.State.DONE
            run.approved_by = request.user
            run.approved_at = timezone.now()
            run.updated_by = request.user
            run.save()
            record(request, "disposal_approved", run, after={"disposed": disposed, "kept": kept})
        return Response(self.get_serializer(self.get_queryset().get(pk=run.pk)).data)

    @extend_schema(
        request=None, responses={200: RunSerializer, 409: ErrorSerializer}, summary="Cancel the run"
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        run, refusal = self._open(request)
        if refusal:
            return refusal
        with transaction.atomic():
            run.state = DisposalRun.State.CANCELLED
            run.updated_by = request.user
            run.save(update_fields=["state", "updated_by", "updated_at"])
            record(request, "disposal_cancelled", run)
        return Response(self.get_serializer(run).data)


class BreachViewSet(AuditedModelViewSet):
    """The breach register. Recording one alerts the administrators and the DPO at once."""

    serializer_class = BreachSerializer
    queryset = Breach.objects.select_related("created_by")
    read_roles = READERS
    write_roles = KEEPERS
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        year = timezone.localdate().year
        count = Breach.objects.filter(reference__startswith=f"BR-{year}-").count()
        serializer.validated_data["reference"] = f"BR-{year}-{count + 1:03d}"
        super().perform_create(serializer)
        breach = serializer.instance
        notify(
            {u for code in KEEPERS for u in users_with_role(code) if u.pk != self.request.user.pk},
            title=f"Personal data breach recorded: {breach.reference}",
            body=f"{breach.summary[:200]} Risk: {breach.get_risk_display().lower()}.",
            link="/admin/breaches",
            kind=Notification.Kind.ALERT,
            dedupe_key=f"breach:{breach.id}",
        )

    @extend_schema(
        request=None, responses={200: BreachSerializer, 409: ErrorSerializer}, summary="Close the breach"
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        breach = self.get_object()
        if breach.closed_at is not None:
            return Response({"code": "closed", "detail": "Already closed."}, status=status.HTTP_409_CONFLICT)
        if breach.contained_at is None:
            return Response(
                {"code": "not_contained", "detail": "Record when it was contained before closing it."},
                status=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            before = snapshot(breach)
            breach.closed_at = timezone.now()
            breach.updated_by = request.user
            breach.save()
            record(request, "breach_closed", breach, before=before, after=snapshot(breach))
        return Response(self.get_serializer(breach).data)
