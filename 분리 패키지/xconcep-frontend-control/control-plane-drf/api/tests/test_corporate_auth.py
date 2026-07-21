from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.db import connections
from django.test import override_settings
from rest_framework.test import APIClient
from io import StringIO
import pytest


pytestmark = pytest.mark.django_db(databases='__all__')


@pytest.fixture
def corporate_db(tmp_path, django_db_blocker):
    configured = connections.configure_settings({
        'default': connections.databases['default'],
        'corporate_auth': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': tmp_path / 'corporate-auth.sqlite3',
        }
    })['corporate_auth']
    connections.databases['corporate_auth'] = configured
    with django_db_blocker.unblock():
        try:
            yield
        finally:
            connection = connections['corporate_auth']
            connection.close()
            delattr(connections._connections, 'corporate_auth')
            del connections.databases['corporate_auth']


def _auth_settings(tmp_path):
    return {
        'AUTH_MODE': 'corporate_db',
        'AUTH_TOKEN_TTL_SECONDS': 300,
        'AUTH_DB_TABLE': 'employees',
        'AUTH_DB_ID_COLUMN': 'id',
        'AUTH_DB_USERNAME_COLUMN': 'username',
        'AUTH_DB_PASSWORD_COLUMN': 'password_hash',
        'AUTH_DB_DISPLAY_NAME_COLUMN': 'display_name',
        'AUTH_DB_EMAIL_COLUMN': 'email',
        'AUTH_DB_ACTIVE_COLUMN': 'is_active',
        'AUTH_DB_PASSWORD_SCHEME': 'django_hash',
        'AUTH_DB_USERNAME_CASE_SENSITIVE': False,
        'INTERNAL_API_TOKEN': '',
    }


def test_corporate_db_login_and_bearer_boundary(tmp_path, corporate_db):
    with override_settings(**_auth_settings(tmp_path)):
        with connections['corporate_auth'].cursor() as cursor:
            cursor.execute(
                'CREATE TABLE employees ('
                'id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, '
                'display_name TEXT, email TEXT, is_active INTEGER)'
            )
            cursor.execute(
                'INSERT INTO employees VALUES (%s, %s, %s, %s, %s, %s)',
                [1, 'engineer', make_password('correct-secret'), '김엔지니어', 'engineer@example.test', 1],
            )

        client = APIClient()
        assert client.get('/api/projects').status_code == 401
        rejected = client.post('/api/auth/login', {'username': 'engineer', 'password': 'wrong'}, format='json')
        assert rejected.status_code == 401
        login = client.post(
            '/api/auth/login', {'username': 'ENGINEER', 'password': 'correct-secret'}, format='json'
        )
        assert login.status_code == 200
        assert login.json()['user']['display_name'] == '김엔지니어'
        token = login.json()['token']
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        assert client.get('/api/auth/me').json()['authenticated'] is True
        assert client.get('/api/projects').status_code == 200


def test_auth_config_is_public_when_auth_is_enabled(tmp_path, corporate_db):
    with override_settings(**_auth_settings(tmp_path)):
        response = APIClient().get('/api/auth/config')
        assert response.status_code == 200
        assert response.json()['required'] is True


def test_internal_db_bootstrap_login_and_bearer_boundary():
    password = 'local-test-secret-2026'
    output = StringIO()
    with override_settings(
        AUTH_MODE='internal_db',
        AUTH_REQUIRED_MODES={'internal_db', 'corporate_db'},
        INTERNAL_AUTH_BOOTSTRAP_ENABLED=True,
        INTERNAL_AUTH_USERNAME='internal_admin',
        INTERNAL_AUTH_PASSWORD=password,
        INTERNAL_AUTH_DISPLAY_NAME='내부 테스트 관리자',
        INTERNAL_AUTH_EMAIL='internal@example.test',
        INTERNAL_API_TOKEN='',
    ):
        call_command('bootstrap_internal_auth', stdout=output)
        assert password not in output.getvalue()
        user = get_user_model().objects.get(username='internal_admin')
        assert user.is_active is True
        assert user.is_staff is False
        assert user.check_password(password)

        client = APIClient()
        assert client.get('/api/auth/config').json() == {
            'mode': 'internal_db',
            'required': True,
            'token_ttl_seconds': settings.AUTH_TOKEN_TTL_SECONDS,
        }
        assert client.get('/api/projects').status_code == 401
        login = client.post(
            '/api/auth/login',
            {'username': 'INTERNAL_ADMIN', 'password': password},
            format='json',
        )
        assert login.status_code == 200
        assert login.json()['user']['display_name'] == '내부 테스트 관리자'
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
        assert client.get('/api/auth/me').json()['authenticated'] is True
        assert client.get('/api/projects').status_code == 200
