from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

from .communication import COMMUNICATION_ERROR_MESSAGE, is_communication_error


class CommunicationErrorMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        if not is_communication_error(exception):
            return None
        # Render without request context processors: they may need the failed DB.
        response = render(None, 'crowd_app/communication_error.html', {
            'error_message': COMMUNICATION_ERROR_MESSAGE,
        }, status=503)
        response['Cache-Control'] = 'no-store'
        return response
