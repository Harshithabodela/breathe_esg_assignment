from decimal import Decimal
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from .models import DataIngestion, RawRecord
from .serializers import DataIngestionSerializer, DataIngestionListSerializer
from apps.emissions.models import ActivityRecord, AuditEvent
from apps.organizations.models import Organization


class DataIngestionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Handles file upload and ingestion listing.
    Upload via POST /api/ingestions/upload/ with multipart form.
    """
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DataIngestionSerializer
        return DataIngestionListSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "membership"):
            return DataIngestion.objects.filter(organization=user.membership.organization)
        return DataIngestion.objects.none()

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        file_obj = request.FILES.get("file")
        source_type = request.data.get("source_type")

        if not file_obj:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
        if source_type not in ("sap", "utility", "travel"):
            return Response(
                {"error": "source_type must be one of: sap, utility, travel"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not hasattr(request.user, "membership"):
            return Response({"error": "User has no organization"}, status=status.HTTP_403_FORBIDDEN)

        org = request.user.membership.organization
        content = file_obj.read()
        file_hash = DataIngestion.compute_hash(content)

        # Duplicate upload guard
        if DataIngestion.objects.filter(organization=org, file_hash=file_hash).exists():
            return Response(
                {"error": "This file has already been uploaded (duplicate file hash detected)"},
                status=status.HTTP_409_CONFLICT
            )

        ingestion = DataIngestion.objects.create(
            organization=org,
            source_type=source_type,
            filename=file_obj.name,
            file_hash=file_hash,
            uploaded_by=request.user,
            status=DataIngestion.Status.PROCESSING,
        )

        # Route to correct parser
        try:
            if source_type == "sap":
                from apps.ingestion.parsers import sap_parser
                records, errors = sap_parser.parse(content)
            elif source_type == "utility":
                from apps.ingestion.parsers import utility_parser
                records, errors = utility_parser.parse(content)
            else:
                from apps.ingestion.parsers import travel_parser
                records, errors = travel_parser.parse(content)
        except Exception as exc:
            ingestion.status = DataIngestion.Status.FAILED
            ingestion.error_summary = str(exc)
            ingestion.save()
            return Response(
                {"error": f"Parser crashed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Persist raw records and create ActivityRecords for successful parses
        ok_count = 0
        err_count = 0
        activity_records_created = []

        for rec in records:
            raw = RawRecord.objects.create(
                ingestion=ingestion,
                row_number=rec["row_number"],
                raw_data=rec["raw_data"],
                parse_status=rec["parse_status"],
                parse_error=rec.get("parse_error", ""),
            )

            if rec["parse_status"] == "error":
                err_count += 1
                continue

            ok_count += 1
            ar = ActivityRecord.objects.create(
                organization=org,
                raw_record=raw,
                source_type=rec["source_type"],
                scope=rec["scope"],
                category=rec["category"],
                period_start=rec["period_start"],
                period_end=rec["period_end"],
                quantity=Decimal(rec["quantity"]) if rec.get("quantity") else Decimal("0"),
                unit=rec["unit"],
                quantity_normalized=Decimal(rec["quantity_normalized"]) if rec.get("quantity_normalized") else Decimal("0"),
                unit_canonical=rec["unit_canonical"],
                co2e_kg=Decimal(rec["co2e_kg"]) if rec.get("co2e_kg") else None,
                emission_factor=Decimal(rec["emission_factor"]) if rec.get("emission_factor") else None,
                emission_factor_source=rec.get("emission_factor_source", ""),
                description=rec.get("description", ""),
                location_ref=rec.get("location_ref", ""),
                review_status=rec.get("review_status", "pending"),
                flag_reason=rec.get("flag_reason", ""),
            )
            AuditEvent.objects.create(
                activity_record=ar,
                event_type=AuditEvent.EventType.INGESTED,
                to_value=f"Created from {source_type} ingestion {ingestion.id}",
                actor=request.user,
            )
            activity_records_created.append(ar.id)

        ingestion.status = DataIngestion.Status.DONE
        ingestion.row_count = ok_count
        ingestion.error_count = err_count
        ingestion.error_summary = "\n".join(errors[:20])  # cap at 20 error lines
        ingestion.save()

        return Response({
            "ingestion_id": ingestion.id,
            "source_type": source_type,
            "rows_ok": ok_count,
            "rows_error": err_count,
            "activity_records_created": len(activity_records_created),
            "errors": errors[:20],
        }, status=status.HTTP_201_CREATED)
