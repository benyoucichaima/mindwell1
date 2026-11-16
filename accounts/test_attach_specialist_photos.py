from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.management.commands.attach_specialist_photos import (
    matching_images,
    normalize_name,
)
from accounts.models import CustomUser, PsychologueProfile


class AttachSpecialistPhotosMatchingTests(TestCase):
    def test_normalize_name_removes_accents_and_unifies_separators(self):
        self.assertEqual(normalize_name("  Élodie_Méry--Benali "), "elodie mery benali")

    def test_matching_images_accepts_both_name_orders_but_not_fuzzy_matches(self):
        image_paths = [
            Path("Amélie_Benali.jpg"),
            Path("Benali-Amélie.png"),
            Path("Amélie Benali extra.jpg"),
        ]

        matches = matching_images("Amélie", "Benali", image_paths)

        self.assertEqual(
            {path.name for path in matches},
            {"Amélie_Benali.jpg", "Benali-Amélie.png"},
        )

    def test_dry_run_reports_exact_match_without_saving_photo(self):
        specialist = CustomUser.objects.create_user(
            username="dry-run-specialist",
            first_name="Élodie",
            last_name="Benali",
            user_type="psychologue",
        )
        profile = PsychologueProfile.objects.create(user=specialist)

        with TemporaryDirectory() as source:
            image_path = Path(source) / "Benali_Elodie.jpg"
            image_path.write_bytes(b"test image")
            output = StringIO()

            call_command(
                "attach_specialist_photos",
                "--source",
                source,
                "--dry-run",
                stdout=output,
            )

        self.assertIn("Matched: 1", output.getvalue())
        self.assertIn("Specialists with no image found: 0", output.getvalue())
        profile.refresh_from_db()
        self.assertFalse(profile.photo)

    def test_command_saves_through_photo_field_and_never_overwrites(self):
        specialist = CustomUser.objects.create_user(
            username="attach-specialist",
            first_name="Élodie",
            last_name="Benali",
            user_type="psychologue",
        )
        profile = PsychologueProfile.objects.create(user=specialist)

        with TemporaryDirectory() as source, TemporaryDirectory() as media_root:
            image_path = Path(source) / "Benali_Elodie.jpg"
            image_path.write_bytes(b"new image")
            output = StringIO()
            with override_settings(MEDIA_ROOT=media_root):
                call_command(
                    "attach_specialist_photos",
                    "--source",
                    source,
                    stdout=output,
                )

                profile.refresh_from_db()
                self.assertEqual(
                    profile.photo.name,
                    "psychologues/photos/Benali_Elodie.jpg",
                )
                self.assertEqual(profile.photo.read(), b"new image")

                profile.photo.save(
                    "existing.jpg",
                    ContentFile(b"keep this image"),
                    save=True,
                )
                existing_photo_name = profile.photo.name
                existing_photo_path = Path(media_root) / existing_photo_name

                call_command(
                    "attach_specialist_photos",
                    "--source",
                    source,
                    stdout=output,
                )

                profile.refresh_from_db()
                self.assertEqual(profile.photo.name, existing_photo_name)
                self.assertEqual(existing_photo_path.read_bytes(), b"keep this image")

        self.assertIn("Skipped (already has photo): 1", output.getvalue())
