from unittest.mock import patch

from django.db.utils import InterfaceError, OperationalError
from django.test import SimpleTestCase
from django.urls import reverse

from .communication import COMMUNICATION_ERROR_MESSAGE, is_communication_error
from .middleware import CommunicationErrorMiddleware


class CommunicationErrorTests(SimpleTestCase):
    def test_db_connection_failure_has_safe_message_on_data_pages(self):
        for name in ('home', 'prediction', 'weekly'):
            with self.subTest(page=name), patch(
                'crowd_app.models.LocationMaster.objects.order_by',
                side_effect=OperationalError(2003, 'private connection details'),
            ):
                response = self.client.get(reverse(name))
            self.assertContains(response, COMMUNICATION_ERROR_MESSAGE, status_code=503)
            self.assertNotContains(response, 'private connection details', status_code=503)
            self.assertEqual(response['Cache-Control'], 'no-store')

    def test_sql_and_application_errors_are_not_treated_as_connection_failures(self):
        middleware = CommunicationErrorMiddleware(lambda request: None)
        for error in (OperationalError(1146, 'missing table'), ValueError('bad value')):
            self.assertIsNone(middleware.process_exception(None, error))
        self.assertTrue(is_communication_error(InterfaceError(0, '')))
        self.assertTrue(is_communication_error(TimeoutError()))
        self.assertTrue(is_communication_error(ConnectionError()))

    def test_help_and_admin_login_load_offline_indicator(self):
        for path in (reverse('help'), '/admin/login/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, 'crowd_app/communication.js')
