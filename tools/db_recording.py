"""Explicitly enabled Django ORM integration for the camera process."""
import os
from pathlib import Path
import sys


class CrowdRecorder:
    def __init__(self, location_id):
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        import django
        django.setup()
        from crowd_app.models import LocationMaster
        self.location = LocationMaster.objects.get(pk=location_id)

    def save(self, count, measured_at):
        from django.db import close_old_connections, connection
        from crowd_app.models import CrowdLog
        if not connection.in_atomic_block:
            close_old_connections()
        # create() invokes the existing model save() and shared rate calculation.
        return CrowdLog.objects.create(
            location_id=self.location.pk, user_count=count, recorded_at=measured_at,
        )
