from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ActivityRecord, AuditEvent
from .serializers import ActivityRecordSerializer, ActivityRecordListSerializer


class ActivityRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only list/detail plus custom actions for review workflow.
    Analysts approve or flag records; locked records cannot be changed.
    """

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ActivityRecordSerializer
        return ActivityRecordListSerializer

    def get_queryset(self):
        user = self.request.user
        if not hasattr(user, "membership"):
            return ActivityRecord.objects.none()

        qs = ActivityRecord.objects.filter(organization=user.membership.organization)

        # Filters
        source_type = self.request.query_params.get("source_type")
        if source_type:
            qs = qs.filter(source_type=source_type)

        scope = self.request.query_params.get("scope")
        if scope:
            qs = qs.filter(scope=scope)

        review_status = self.request.query_params.get("review_status")
        if review_status:
            qs = qs.filter(review_status=review_status)

        date_from = self.request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(period_start__gte=date_from)

        date_to = self.request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(period_end__lte=date_to)

        return qs.select_related("raw_record", "reviewed_by")

    def _check_not_locked(self, record):
        if record.review_status == ActivityRecord.ReviewStatus.LOCKED:
            return Response(
                {"error": "Record is locked for audit and cannot be modified"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        record = self.get_object()
        err = self._check_not_locked(record)
        if err:
            return err

        old_status = record.review_status
        record.review_status = ActivityRecord.ReviewStatus.APPROVED
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.flag_reason = ""
        record.save()

        AuditEvent.objects.create(
            activity_record=record,
            event_type=AuditEvent.EventType.STATUS_CHANGE,
            field_name="review_status",
            from_value=old_status,
            to_value=ActivityRecord.ReviewStatus.APPROVED,
            actor=request.user,
            note=request.data.get("note", ""),
        )
        return Response({"ok": True, "review_status": "approved"})

    @action(detail=True, methods=["post"])
    def flag(self, request, pk=None):
        record = self.get_object()
        err = self._check_not_locked(record)
        if err:
            return err

        reason = request.data.get("reason", "").strip()
        if not reason:
            return Response({"error": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        old_status = record.review_status
        record.review_status = ActivityRecord.ReviewStatus.FLAGGED
        record.flag_reason = reason
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.save()

        AuditEvent.objects.create(
            activity_record=record,
            event_type=AuditEvent.EventType.STATUS_CHANGE,
            field_name="review_status",
            from_value=old_status,
            to_value=ActivityRecord.ReviewStatus.FLAGGED,
            actor=request.user,
            note=reason,
        )
        return Response({"ok": True, "review_status": "flagged"})

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        record = self.get_object()
        if record.review_status != ActivityRecord.ReviewStatus.APPROVED:
            return Response(
                {"error": "Only approved records can be locked for audit"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_status = record.review_status
        record.review_status = ActivityRecord.ReviewStatus.LOCKED
        record.save()

        AuditEvent.objects.create(
            activity_record=record,
            event_type=AuditEvent.EventType.STATUS_CHANGE,
            field_name="review_status",
            from_value=old_status,
            to_value=ActivityRecord.ReviewStatus.LOCKED,
            actor=request.user,
            note="Locked for audit",
        )
        return Response({"ok": True, "review_status": "locked"})

    @action(detail=True, methods=["patch"], url_path="edit")
    def edit_field(self, request, pk=None):
        """
        Allow analyst to correct a quantity or description.
        Every edit is logged in AuditEvent. Locked records cannot be edited.
        Only co2e_kg, quantity_normalized, description, emission_factor_source are editable.
        """
        record = self.get_object()
        err = self._check_not_locked(record)
        if err:
            return err

        editable_fields = {"co2e_kg", "quantity_normalized", "description", "emission_factor_source"}
        note = request.data.get("note", "")
        changes = []

        for field in editable_fields:
            if field in request.data:
                old_value = str(getattr(record, field, ""))
                new_value = str(request.data[field])
                setattr(record, field, request.data[field])
                AuditEvent.objects.create(
                    activity_record=record,
                    event_type=AuditEvent.EventType.FIELD_EDIT,
                    field_name=field,
                    from_value=old_value,
                    to_value=new_value,
                    actor=request.user,
                    note=note,
                )
                changes.append(field)

        if not changes:
            return Response({"error": f"No editable fields provided. Editable: {sorted(editable_fields)}"},
                            status=status.HTTP_400_BAD_REQUEST)

        # If record was approved, editing moves it back to pending for re-review
        if record.review_status == ActivityRecord.ReviewStatus.APPROVED:
            old_status = record.review_status
            record.review_status = ActivityRecord.ReviewStatus.PENDING
            AuditEvent.objects.create(
                activity_record=record,
                event_type=AuditEvent.EventType.STATUS_CHANGE,
                field_name="review_status",
                from_value=old_status,
                to_value=ActivityRecord.ReviewStatus.PENDING,
                actor=request.user,
                note="Status reset to pending after field edit",
            )

        record.save()
        return Response({"ok": True, "fields_updated": changes})

    @action(detail=False, methods=["post"], url_path="bulk-approve")
    def bulk_approve(self, request):
        """Approve multiple records at once."""
        ids = request.data.get("ids", [])
        if not ids:
            return Response({"error": "ids list required"}, status=status.HTTP_400_BAD_REQUEST)

        records = self.get_queryset().filter(id__in=ids).exclude(
            review_status=ActivityRecord.ReviewStatus.LOCKED
        )
        now = timezone.now()
        audit_events = []
        updated = 0

        for record in records:
            if record.review_status != ActivityRecord.ReviewStatus.APPROVED:
                old = record.review_status
                record.review_status = ActivityRecord.ReviewStatus.APPROVED
                record.reviewed_by = request.user
                record.reviewed_at = now
                record.flag_reason = ""
                audit_events.append(AuditEvent(
                    activity_record=record,
                    event_type=AuditEvent.EventType.STATUS_CHANGE,
                    field_name="review_status",
                    from_value=old,
                    to_value=ActivityRecord.ReviewStatus.APPROVED,
                    actor=request.user,
                    note="Bulk approved",
                ))
                updated += 1

        ActivityRecord.objects.bulk_update(
            records, ["review_status", "reviewed_by", "reviewed_at", "flag_reason"]
        )
        AuditEvent.objects.bulk_create(audit_events)
        return Response({"ok": True, "approved_count": updated})

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Dashboard summary counts."""
        qs = self.get_queryset()
        total = qs.count()
        by_status = {
            "pending": qs.filter(review_status="pending").count(),
            "flagged": qs.filter(review_status="flagged").count(),
            "approved": qs.filter(review_status="approved").count(),
            "locked": qs.filter(review_status="locked").count(),
        }
        by_source = {
            "sap": qs.filter(source_type="sap").count(),
            "utility": qs.filter(source_type="utility").count(),
            "travel": qs.filter(source_type="travel").count(),
        }
        by_scope = {
            "1": qs.filter(scope=1).count(),
            "2": qs.filter(scope=2).count(),
            "3": qs.filter(scope=3).count(),
        }

        from django.db.models import Sum
        total_co2e = qs.filter(co2e_kg__isnull=False).aggregate(total=Sum("co2e_kg"))["total"]

        return Response({
            "total": total,
            "by_status": by_status,
            "by_source": by_source,
            "by_scope": by_scope,
            "total_co2e_kg": float(total_co2e) if total_co2e else 0,
        })
