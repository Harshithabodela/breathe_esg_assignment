from rest_framework import serializers
from .models import DataIngestion, RawRecord


class RawRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRecord
        fields = ["id", "row_number", "raw_data", "parse_status", "parse_error"]


class DataIngestionSerializer(serializers.ModelSerializer):
    raw_records = RawRecordSerializer(many=True, read_only=True)
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True, default=None)

    class Meta:
        model = DataIngestion
        fields = [
            "id", "organization", "source_type", "source_type_display",
            "filename", "file_hash", "uploaded_by_username",
            "uploaded_at", "status", "status_display",
            "row_count", "error_count", "error_summary",
            "raw_records",
        ]
        read_only_fields = [
            "file_hash", "uploaded_by_username", "uploaded_at",
            "status", "row_count", "error_count", "error_summary",
        ]


class DataIngestionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the list view (no raw_records)."""
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True, default=None)

    class Meta:
        model = DataIngestion
        fields = [
            "id", "source_type", "source_type_display",
            "filename", "uploaded_by_username", "uploaded_at",
            "status", "status_display", "row_count", "error_count",
        ]
