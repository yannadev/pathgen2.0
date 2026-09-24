from __future__ import annotations

import os

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.core.services.audit import record_model_audit_event
from apps.core.services.settings import initialize_system_setting


class Command(BaseCommand):
    help = "Create one trusted PathGen administrator from an environment-supplied password."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--first-name", required=True)
        parser.add_argument("--last-name", required=True)
        parser.add_argument("--email", default="")
        parser.add_argument(
            "--password-env",
            default="PATHGEN_BOOTSTRAP_ADMIN_PASSWORD",
            help="Environment variable containing the initial password.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password_env = options["password_env"]
        password = os.environ.get(password_env, "")
        if not password:
            raise CommandError(f"{password_env} must be set and nonblank.")
        username = User.normalize_username(options["username"].strip())
        if User.objects.filter(username=username).exists():
            raise CommandError("A user with that username already exists.")
        admin = User(
            username=username,
            first_name=options["first_name"].strip(),
            last_name=options["last_name"].strip(),
            email=User.objects.normalize_email(options["email"].strip()),
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )
        if not admin.first_name or not admin.last_name:
            raise CommandError("First and last name must be nonblank.")
        try:
            password_validation.validate_password(password, user=admin)
            admin.set_password(password)
            admin.full_clean()
        except ValidationError as error:
            raise CommandError("Administrator details failed validation.") from error
        admin.save()
        record_model_audit_event(
            actor=admin,
            action="user.admin_bootstrapped",
            target=admin,
            target_snapshot={"role": admin.role, "is_active": True},
        )
        initialize_system_setting(actor=admin)
        self.stdout.write(self.style.SUCCESS(f"Created trusted administrator {admin.username}."))
