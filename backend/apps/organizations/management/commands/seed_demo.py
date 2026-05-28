from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from apps.organizations.models import Organization, OrganizationMembership
from apps.emissions.models import ActivityRecord
from django.utils import timezone
from datetime import timedelta
import random

class Command(BaseCommand):
    help = "Create demo organization, analyst user, and sample emission records"

    def add_arguments(self, parser):
        parser.add_argument("--password", default="breathe2025")

    def handle(self, *args, **options):
        password = options["password"]

        org, _ = Organization.objects.get_or_create(
            slug="acme-corp",
            defaults={"name": "Acme Corporation"},
        )

        user, created = User.objects.get_or_create(
            username="analyst",
            defaults={
                "email": "analyst@acmecorp.com",
                "first_name": "Demo",
                "last_name": "Analyst",
            },
        )
        if created:
            user.set_password(password)
            user.save()

        OrganizationMembership.objects.get_or_create(
            user=user,
            defaults={"organization": org, "role": "analyst"},
        )

        if ActivityRecord.objects.filter(organization=org).exists():
            self.stdout.write("Records already exist.")
        else:
            sources = [
                ("sap", 1, "fuel_combustion", ["WERK1 (Chicago)", "WERK2 (Austin)", "WERK3 (Dallas)"], "liters", "liters"),
                ("utility", 2, "electricity", ["UTL-001", "UTL-002", "UTL-003"], "kWh", "kWh"),
                ("travel", 3, "flight", ["JFK-LAX", "ORD-BCN", "GRU-LAX"], "km", "km"),
            ]

            records = []
            for i in range(30):
                source, scope, category, locations, unit, unit_canonical = random.choice(sources)
                start = timezone.now() - timedelta(days=random.randint(1, 180))
                qty = round(random.uniform(100, 5000), 4)
                records.append(ActivityRecord(
                    organization=org,
                    source_type=source,
                    scope=scope,
                    category=category,
                    location_ref=random.choice(locations),
                    period_start=start.date(),
                    period_end=(start + timedelta(days=random.randint(1, 30))).date(),
                    quantity=qty,
                    unit=unit,
                    quantity_normalized=qty,
                    unit_canonical=unit_canonical,
                    co2e_kg=round(random.uniform(50, 10000), 4),
                    review_status="pending",
                ))
            ActivityRecord.objects.bulk_create(records)
            self.stdout.write(self.style.SUCCESS(f"Created {len(records)} records!"))

        self.stdout.write(self.style.SUCCESS(f"\nDemo seed complete.\n  Login: analyst / {password}"))
