from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core import signing
from django.db import connections


TOKEN_SALT = 'xconcep.corporate-auth.v1'
IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


class CorporateAuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CorporateUser:
    id: str
    username: str
    display_name: str
    email: str

    def public(self) -> dict[str, str]:
        return asdict(self)


def _quoted(connection, value: str, *, allow_path: bool = False) -> str:
    parts = value.split('.') if allow_path else [value]
    if not parts or any(not IDENTIFIER.fullmatch(part) for part in parts):
        raise CorporateAuthenticationError(f'Invalid corporate auth DB identifier: {value!r}')
    return '.'.join(connection.ops.quote_name(part) for part in parts)


def _is_active(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'active', 'enabled'}


def _verify_password(password: str, encoded: str) -> bool:
    scheme = settings.AUTH_DB_PASSWORD_SCHEME
    if scheme != 'django_hash':
        raise CorporateAuthenticationError(
            f'Unsupported AUTH_DB_PASSWORD_SCHEME: {scheme}. Use django_hash or implement a company-specific verifier.'
        )
    return check_password(password, encoded)


def _authenticate_internal_user(username: str, password: str) -> CorporateUser:
    User = get_user_model()
    lookup = {'username': username} if settings.AUTH_DB_USERNAME_CASE_SENSITIVE else {'username__iexact': username}
    try:
        user = User.objects.using('default').get(**lookup)
    except (User.DoesNotExist, User.MultipleObjectsReturned) as exc:
        raise CorporateAuthenticationError('Invalid username or password') from exc
    if not user.is_active or not user.check_password(password):
        raise CorporateAuthenticationError('Invalid username or password')
    display_name = user.get_full_name().strip() or user.get_username()
    return CorporateUser(
        id=str(user.pk),
        username=str(user.get_username()),
        display_name=display_name,
        email=str(user.email or ''),
    )


def authenticate_corporate_user(username: str, password: str) -> CorporateUser:
    username = username.strip()
    if not username or not password:
        raise CorporateAuthenticationError('Invalid username or password')
    if settings.AUTH_MODE == 'internal_db':
        return _authenticate_internal_user(username, password)
    if settings.AUTH_MODE != 'corporate_db':
        raise CorporateAuthenticationError('Database authentication is not enabled')
    if 'corporate_auth' not in connections:
        raise CorporateAuthenticationError('Corporate authentication database is not configured')
    connection = connections['corporate_auth']
    table = _quoted(connection, settings.AUTH_DB_TABLE, allow_path=True)
    columns = [
        settings.AUTH_DB_ID_COLUMN,
        settings.AUTH_DB_USERNAME_COLUMN,
        settings.AUTH_DB_PASSWORD_COLUMN,
        settings.AUTH_DB_DISPLAY_NAME_COLUMN,
        settings.AUTH_DB_EMAIL_COLUMN,
        settings.AUTH_DB_ACTIVE_COLUMN,
    ]
    selected = ', '.join(_quoted(connection, column) for column in columns)
    username_column = _quoted(connection, settings.AUTH_DB_USERNAME_COLUMN)
    where = f'{username_column} = %s' if settings.AUTH_DB_USERNAME_CASE_SENSITIVE else f'LOWER({username_column}) = LOWER(%s)'
    query = f'SELECT {selected} FROM {table} WHERE {where}'
    with connection.cursor() as cursor:
        cursor.execute(query, [username])
        row = cursor.fetchone()
        duplicate = cursor.fetchone() if row is not None else None
    if row is None or duplicate is not None:
        raise CorporateAuthenticationError('Invalid username or password')
    user_id, stored_username, password_hash, display_name, email, active = row
    if not _is_active(active) or not _verify_password(password, str(password_hash or '')):
        raise CorporateAuthenticationError('Invalid username or password')
    return CorporateUser(
        id=str(user_id),
        username=str(stored_username),
        display_name=str(display_name or stored_username),
        email=str(email or ''),
    )


def issue_token(user: CorporateUser) -> str:
    return signing.dumps(user.public(), salt=TOKEN_SALT, compress=True)


def verify_token(token: str) -> CorporateUser:
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=settings.AUTH_TOKEN_TTL_SECONDS)
        return CorporateUser(
            id=str(payload['id']),
            username=str(payload['username']),
            display_name=str(payload.get('display_name') or payload['username']),
            email=str(payload.get('email') or ''),
        )
    except (signing.BadSignature, signing.SignatureExpired, KeyError, TypeError) as exc:
        raise CorporateAuthenticationError('Authentication token is invalid or expired') from exc


def probe_corporate_database() -> bool:
    if settings.AUTH_MODE == 'internal_db':
        alias = 'default'
    elif settings.AUTH_MODE == 'corporate_db':
        alias = 'corporate_auth'
    else:
        return False
    with connections[alias].cursor() as cursor:
        cursor.execute('SELECT 1')
        return cursor.fetchone() == (1,)
