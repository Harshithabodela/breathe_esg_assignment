import hashlib
from django.db import models
from django.contrib.auth.models import User
from apps.organizations.models import Organization


class DataIngestion(models.Model):
    """Represents a single file upload event. One per file, immutable after creation."""

    class SourceType(models.TextChoices):
        SAP = "sap", "SAP (Fuel & Procurement)"
        UTILITY = "utility", "Utility (Electricity)"
        TRAVEL = "travel", "Corporate Travel"

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="ingestions")
    source_type = models.CharField(max_length=10, choices=SourceType.choices)
    filename = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64, help_text="SHA-256 of raw file content; prevents duplicate uploads")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PROCESSING)
    row_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    error_summary = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_source_type_display()} — {self.filename} ({self.uploaded_at:%Y-%m-%d})"

    @staticmethod
    def compute_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()


class RawRecord(models.Model):
    """
    Immutable as-ingested row. Never modified after creation.
    The source-of-truth for what we received from the client.
    """

    class ParseStatus(models.TextChoices):
        OK = "ok", "OK"
        ERROR = "error", "Error"

    ingestion = models.ForeignKey(DataIngestion, on_delete=models.CASCADE, related_name="raw_records")
    row_number = models.IntegerField(help_text="1-indexed row number in the source file")
    raw_data = models.JSONField(help_text="Exact key-value pairs from the source row, unmodified")
    parse_status = models.CharField(max_length=10, choices=ParseStatus.choices, default=ParseStatus.OK)
    parse_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["ingestion", "row_number"]
        unique_together = [("ingestion", "row_number")]

    def __str__(self):
        return f"Row {self.row_number} of {self.ingestion}"
