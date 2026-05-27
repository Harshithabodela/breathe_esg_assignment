"""
Management command: seed demo organization and analyst account.
Run once after migrations on a fresh database.

Usage:
    python manage.py seed_demo
    python manage.py seed_demo --password mypassword
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from apps.organizations.models import Organization, OrganizationMembership


class Command(BaseCommand):
    help = "Create demo organization and analyst user"

    def add_arguments(self, parser):
        parser.add_argument("--password", default="breathe2025", help="Password for demo analyst account")

    def handle(self, *args, **options):
        password = options["password"]

        org, created = Organization.objects.get_or_create(
            slug="acme-corp",
            defaults={"name": "Acme Corporation"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created organization: {org.name}"))
        else:
            self.stdout.write(f"Organization already exists: {org.name}")

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
            self.stdout.write(self.style.SUCCESS(f"Created user: analyst (password: {password})"))
        else:
            self.stdout.write(f"User already exists: analyst")

        membership, created = OrganizationMembership.objects.get_or_create(
            user=user,
            defaults={"organization": org, "role": "analyst"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Linked analyst to {org.name}"))

        self.stdout.write(self.style.SUCCESS("\nDemo seed complete."))
        self.stdout.write(f"  Login: analyst / {password}")
        self.stdout.write(f"  Organization: {org.name} (slug: {org.slug})")
