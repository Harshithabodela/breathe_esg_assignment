from django.db import models
from django.contrib.auth.models import User
from apps.organizations.models import Organization
from apps.ingestion.models import RawRecord


class ActivityRecord(models.Model):
    """
    Normalized emission activity. One row per discrete activity event
    (a fuel purchase, a billing period, a trip segment).

    Separated from RawRecord so we can:
    - Preserve the original data forever (RawRecord)
    - Allow analyst corrections without losing provenance (AuditEvent)
    - Compare across sources using canonical units
    """

    class Scope(models.IntegerChoices):
        SCOPE_1 = 1, "Scope 1 — Direct emissions"
        SCOPE_2 = 2, "Scope 2 — Purchased electricity"
        SCOPE_3 = 3, "Scope 3 — Value chain"

    class Category(models.TextChoices):
        FUEL_COMBUSTION = "fuel_combustion", "Fuel Combustion"
        ELECTRICITY = "electricity", "Purchased Electricity"
        FLIGHT = "flight", "Air Travel"
        HOTEL = "hotel", "Hotel Stay"
        CAR_RENTAL = "car_rental", "Car Rental"
        RAIL = "rail", "Rail Travel"
        PROCUREMENT = "procurement", "Procurement"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending Review"
        FLAGGED = "flagged", "Flagged"
        APPROVED = "approved", "Approved"
        LOCKED = "locked", "Locked for Audit"

    # Provenance
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="activity_records")
    raw_record = models.OneToOneField(
        RawRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_record",
        help_text="Null only for manually entered records"
    )
    source_type = models.CharField(max_length=10, choices=[
        ("sap", "SAP"), ("utility", "Utility"), ("travel", "Travel")
    ])

    # Classification
    scope = models.IntegerField(choices=Scope.choices)
    category = models.CharField(max_length=20, choices=Category.choices)

    # Temporal — billing periods don't align with calendar months
    period_start = models.DateField()
    period_end = models.DateField()

    # Quantity as received (after unit normalization from source)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit = models.CharField(max_length=20, help_text="e.g. liters, kWh, km, nights")

    # Canonical normalized quantity for cross-source comparison
    quantity_normalized = models.DecimalField(max_digits=18, decimal_places=4)
    unit_canonical = models.CharField(max_length=20, help_text="liters | kWh | km | nights")

    # Computed emissions
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    emission_factor = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    emission_factor_source = models.CharField(max_length=255, blank=True, default="")

    # Human-readable identifiers
    description = models.CharField(max_length=500, blank=True, default="")
    location_ref = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Plant code, meter ID, airport pair — source-specific identifier"
    )

    # Review workflow
    review_status = models.CharField(max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    flag_reason = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_records"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_start", "organization"]

    def __str__(self):
        return f"{self.get_category_display()} | {self.quantity_normalized} {self.unit_canonical} | {self.period_start}"


class AuditEvent(models.Model):
    """
    Append-only log of every state change and field edit on an ActivityRecord.
    Nothing is ever deleted from this table.
    """

    class EventType(models.TextChoices):
        STATUS_CHANGE = "status_change", "Status Change"
        FIELD_EDIT = "field_edit", "Field Edit"
        INGESTED = "ingested", "Record Ingested"

    activity_record = models.ForeignKey(ActivityRecord, on_delete=models.CASCADE, related_name="audit_events")
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    field_name = models.CharField(max_length=100, blank=True, default="")
    from_value = models.TextField(blank=True, default="")
    to_value = models.TextField(blank=True, default="")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.event_type} on record {self.activity_record_id} at {self.timestamp}"
