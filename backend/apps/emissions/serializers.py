from rest_framework import serializers
from .models import ActivityRecord, AuditEvent
from apps.ingestion.serializers import RawRecordSerializer


class AuditEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)

    class Meta:
        model = AuditEvent
        fields = ["id", "event_type", "field_name", "from_value", "to_value",
                  "actor_username", "timestamp", "note"]


class ActivityRecordSerializer(serializers.ModelSerializer):
    raw_record_data = RawRecordSerializer(source="raw_record", read_only=True)
    audit_events = AuditEventSerializer(many=True, read_only=True)
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    review_status_display = serializers.CharField(source="get_review_status_display", read_only=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", read_only=True, default=None)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = ActivityRecord
        fields = [
            "id", "organization", "organization_name", "source_type",
            "scope", "scope_display", "category", "category_display",
            "period_start", "period_end",
            "quantity", "unit",
            "quantity_normalized", "unit_canonical",
            "co2e_kg", "emission_factor", "emission_factor_source",
            "description", "location_ref",
            "review_status", "review_status_display",
            "flag_reason", "reviewed_by_username", "reviewed_at",
            "created_at", "updated_at",
            "raw_record_data", "audit_events",
        ]
        read_only_fields = [
            "organization", "source_type", "scope", "category",
            "period_start", "period_end",
            "quantity", "unit", "quantity_normalized", "unit_canonical",
            "emission_factor", "emission_factor_source",
            "review_status", "reviewed_by_username", "reviewed_at",
            "created_at", "updated_at",
            "raw_record_data", "audit_events",
        ]


class ActivityRecordListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — no nested data."""
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    review_status_display = serializers.CharField(source="get_review_status_display", read_only=True)

    class Meta:
        model = ActivityRecord
        fields = [
            "id", "source_type", "scope", "scope_display",
            "category", "category_display",
            "period_start", "period_end",
            "quantity_normalized", "unit_canonical",
            "co2e_kg", "description", "location_ref",
            "review_status", "review_status_display",
            "flag_reason", "created_at",
        ]
