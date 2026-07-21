from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


PLACEHOLDER_TOKENS = ('replace-', 'change-me', 'your-')


class Command(BaseCommand):
    help = 'Create or update the internal-MySQL test login without printing its password.'

    def handle(self, *args, **options):
        if settings.AUTH_MODE != 'internal_db':
            self.stdout.write('Internal authentication bootstrap skipped (AUTH_MODE is not internal_db).')
            return
        if not settings.INTERNAL_AUTH_BOOTSTRAP_ENABLED:
            self.stdout.write('Internal authentication bootstrap disabled.')
            return

        username = settings.INTERNAL_AUTH_USERNAME.strip()
        password = settings.INTERNAL_AUTH_PASSWORD
        display_name = settings.INTERNAL_AUTH_DISPLAY_NAME.strip()
        email = settings.INTERNAL_AUTH_EMAIL.strip()
        if not username:
            raise CommandError('INTERNAL_AUTH_USERNAME is required')
        if not password or any(token in password.lower() for token in PLACEHOLDER_TOKENS):
            raise CommandError('Set a non-placeholder INTERNAL_AUTH_PASSWORD in the git-ignored .env file')
        if len(display_name) > 150:
            raise CommandError('INTERNAL_AUTH_DISPLAY_NAME must be 150 characters or fewer')

        User = get_user_model()
        with transaction.atomic(using='default'):
            user = User.objects.using('default').filter(username__iexact=username).first()
            created = user is None
            if created:
                user = User(username=username)
            user.username = username
            user.first_name = display_name
            user.last_name = ''
            user.email = email
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False
            user.set_password(password)
            user.save(using='default')

        action = 'created' if created else 'updated'
        self.stdout.write(self.style.SUCCESS(f'Internal authentication user {action}: {username}'))
