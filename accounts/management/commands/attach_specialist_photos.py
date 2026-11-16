import re
import unicodedata
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from accounts.models import PsychologueProfile


IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def normalize_name(value):
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in normalized
        if not unicodedata.combining(character)
    )
    return re.sub(r"[\s_-]+", " ", without_accents).strip()


def matching_images(first_name, last_name, image_paths):
    if not first_name.strip() or not last_name.strip():
        return []

    expected_names = {
        normalize_name(f"{first_name} {last_name}"),
        normalize_name(f"{last_name} {first_name}"),
    }
    return sorted(
        {
            path
            for path in image_paths
            if normalize_name(path.stem) in expected_names
        },
        key=lambda path: str(path).casefold(),
    )


class Command(BaseCommand):
    help = "Attach matching image files to specialists with no profile photo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            required=True,
            help="Folder containing specialist images (searched recursively).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report matches without saving any photos.",
        )

    def handle(self, *args, **options):
        source = Path(options["source"]).expanduser()
        if not source.is_dir():
            raise CommandError(f"Image source folder does not exist: {source}")

        image_paths = [
            path
            for path in source.rglob("*")
            if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS
        ]
        report = {
            "matched": [],
            "skipped": [],
            "ambiguous": [],
            "not_found": [],
        }

        profiles = (
            PsychologueProfile.objects.select_related("user")
            .filter(user__user_type="psychologue")
            .order_by("user__last_name", "user__first_name", "user_id")
        )
        for profile in profiles:
            specialist_name = (
                f"{profile.user.first_name} {profile.user.last_name}".strip()
                or profile.user.username
            )
            if profile.photo:
                report["skipped"].append((specialist_name, profile.photo.name))
                continue

            matches = matching_images(
                profile.user.first_name,
                profile.user.last_name,
                image_paths,
            )
            if len(matches) > 1:
                report["ambiguous"].append((specialist_name, matches))
                continue
            if not matches:
                report["not_found"].append(specialist_name)
                continue

            image_path = matches[0]
            report["matched"].append((specialist_name, image_path))
            if not options["dry_run"]:
                with image_path.open("rb") as image_file:
                    profile.photo.save(image_path.name, File(image_file), save=True)

        self.stdout.write(
            "DRY RUN — no photos were changed."
            if options["dry_run"]
            else "Photos attached."
        )
        self.stdout.write(f"Matched: {len(report['matched'])}")
        for name, image_path in report["matched"]:
            self.stdout.write(f"  {name} <- {image_path}")
        self.stdout.write(f"Skipped (already has photo): {len(report['skipped'])}")
        for name, photo_name in report["skipped"]:
            self.stdout.write(f"  {name} ({photo_name})")
        self.stdout.write(f"Ambiguous (multiple matches): {len(report['ambiguous'])}")
        for name, image_paths in report["ambiguous"]:
            self.stdout.write(f"  {name}:")
            for image_path in image_paths:
                self.stdout.write(f"    {image_path}")
        self.stdout.write(f"Specialists with no image found: {len(report['not_found'])}")
        for name in report["not_found"]:
            self.stdout.write(f"  {name}")
