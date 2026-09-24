from django.db import migrations
from django.utils import timezone


def initialize_for_existing_admin(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    SystemSetting = apps.get_model("core", "SystemSetting")
    admin = User.objects.filter(role="admin", is_active=True).order_by("created_at", "pk").first()
    if admin is not None:
        SystemSetting.objects.get_or_create(
            singleton_key=1,
            defaults={
                "study_access_enabled": True,
                "posttest_access_enabled": False,
                "changed_by": admin,
                "changed_at": timezone.now(),
                "revision": 0,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0002_protect_audit_events")]

    operations = [
        migrations.RunPython(initialize_for_existing_admin, migrations.RunPython.noop),
    ]
