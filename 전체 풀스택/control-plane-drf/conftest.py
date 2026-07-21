import os


# pytest-django initializes Django before importing test modules. Select the
# lightweight test database here so local tests never require a MySQL driver.
os.environ.setdefault('DB_ENGINE', 'sqlite')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
