from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.curriculum.seed import SeedValidationError, load_and_validate_seed_package


class Command(BaseCommand):
    help = "Validate the approved PathGen curriculum JSON package without importing it."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, help="Override the approved JSON package directory.")

    def handle(self, *args, **options):
        try:
            package = load_and_validate_seed_package(options.get("source"))
        except SeedValidationError as error:
            raise CommandError("Curriculum validation failed:\n- " + "\n- ".join(error.errors)) from error

        digest = package.prepost["source_sha256"]
        self.stdout.write(self.style.SUCCESS("Curriculum validation passed."))
        self.stdout.write("JSON schemas: manifest, 3 lessons, activity, media, and pre/post passed")
        self.stdout.write("Counts: 3 lessons, 6 skills, 135 questions (30 pre/post, 30 regular, 30 additional, 30 foundational, 15 activity)")
        self.stdout.write("Rules: four distinct A-D choices with one correct answer; Bloom and activity distributions passed")
        self.stdout.write(f"Protected PDF SHA-256 verified: {digest}")
