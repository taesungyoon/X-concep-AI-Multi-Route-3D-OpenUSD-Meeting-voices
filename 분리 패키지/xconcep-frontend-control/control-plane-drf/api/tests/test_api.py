import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
os.environ.setdefault('DB_ENGINE','sqlite')
import pytest
from rest_framework.test import APIClient
@pytest.mark.django_db
def test_health():
    r=APIClient().get('/health'); assert r.status_code==200; assert r.json()['service']=='drf-control-plane'
@pytest.mark.django_db
def test_meeting_project():
    r=APIClient().post('/api/meetings',{'category':'equipment'},format='json'); assert r.status_code==201; assert r.json()['project']['meeting']['status']=='recording_ready'
