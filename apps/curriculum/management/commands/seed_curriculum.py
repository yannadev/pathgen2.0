from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from apps.curriculum.seed import (
    SeedValidationError,
    import_seed_package,
    load_and_validate_seed_package,
)


class Command(BaseCommand):
    help = "Validate and transactionally import the approved PathGen curriculum package."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, help="Override the approved JSON package directory.")

    def handle(self, *args, **options):
        try:
            package = load_and_validate_seed_package(options.get("source"))
            counts = import_seed_package(package)
        except SeedValidationError as error:
            raise CommandError("Curriculum validation failed:\n- " + "\n- ".join(error.errors)) from error
        except (ValidationError, DatabaseError) as error:
            raise CommandError(f"Curriculum import was rolled back: {error}") from error

        self.stdout.write(self.style.SUCCESS("Curriculum seed import complete."))
        self.stdout.write(
            "Imported: {lessons} lessons, {skills} skills, {questions} questions, "
            "{choices} choices, {question_sets} sets, {videos} videos".format(**counts)
        )
        self.stdout.write("The command is idempotent and all published records remain read-only.")
