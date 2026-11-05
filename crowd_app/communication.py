"""Recognize connection failures without hiding SQL or application errors."""
from django.db.utils import InterfaceError, OperationalError


COMMUNICATION_ERROR_MESSAGE = 'エラーが発生しました'
MYSQL_CONNECTION_ERRORS = {1040, 1042, 2002, 2003, 2005, 2006, 2013, 2055}


def is_communication_error(error):
    if isinstance(error, (ConnectionError, TimeoutError)):
        return True
    if isinstance(error, (OperationalError, InterfaceError)):
        code = error.args[0] if error.args else None
        return code in MYSQL_CONNECTION_ERRORS or (
            isinstance(error, InterfaceError) and code == 0
        )
    return False
