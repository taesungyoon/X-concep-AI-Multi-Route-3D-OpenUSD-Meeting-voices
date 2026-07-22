import os
from unittest.mock import patch
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
os.environ.setdefault('DB_ENGINE','sqlite')
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient
from api.models import Concept2D, GenerationJob, Project
@pytest.mark.django_db
def test_health():
    r=APIClient().get('/health'); assert r.status_code==200; assert r.json()['service']=='drf-control-plane'
@pytest.mark.django_db
def test_meeting_project():
    r=APIClient().post('/api/meetings',{'category':'equipment'},format='json'); assert r.status_code==201; assert r.json()['project']['meeting']['status']=='recording_ready'


@pytest.mark.django_db
@override_settings(INTERNAL_API_TOKEN='local-service-token')
def test_internal_api_token_boundary():
    client=APIClient()
    assert client.get('/health').status_code == 200
    assert client.get('/api/projects').status_code == 401
    client.credentials(HTTP_X_INTERNAL_TOKEN='local-service-token')
    assert client.get('/api/projects').status_code == 200


@pytest.mark.django_db
def test_rejects_fake_image_upload():
    fake=SimpleUploadedFile('fake.png',b'not-an-image',content_type='image/png')
    response=APIClient().post('/api/projects',{
        'prompt':'유효하지 않은 이미지 업로드 검증용 프롬프트',
        'category':'equipment',
        'images[]':fake,
    },format='multipart')
    assert response.status_code == 422
    assert Project.objects.count() == 0


@pytest.mark.django_db
@override_settings(SYNC_PIPELINE=False)
def test_async_generation_is_queued():
    with patch('api.views.generate_2d_task.delay') as delay:
        response=APIClient().post('/api/projects',{
            'prompt':'비동기 작업 큐 등록을 확인하는 테스트 프롬프트',
            'category':'equipment',
        },format='multipart')
    assert response.status_code == 202
    job=GenerationJob.objects.get(pk=response.json()['job']['id'])
    assert job.status == 'queued'
    assert job.project.status == 'queued_2d'
    delay.assert_called_once()


@pytest.mark.django_db
@override_settings(SYNC_PIPELINE=False)
def test_partial_regeneration_scope_is_queued():
    project=Project.objects.create(
        id='PRJ-PARTIAL-QUEUE',
        prompt='부분 재생성 범위 전달을 확인하는 충분히 긴 테스트 프롬프트',
        category='equipment',
        status='2d_ready',
        selected_2d_id='CONCEPT-1',
    )
    concept=Concept2D.objects.create(
        project=project,
        concept_id='CONCEPT-1',
        title='Safety Cover',
        public_url='/storage/projects/PRJ-PARTIAL-QUEUE/concepts/concept-1.png',
        relative_path='projects/PRJ-PARTIAL-QUEUE/concepts/concept-1.png',
    )
    with patch('api.views.generate_3d_task.delay') as delay:
        response=APIClient().post(
            f'/api/projects/{project.id}/generate-3d',
            {
                'selected_2d_id':concept.concept_id,
                'output_goal':'structural',
                'engine_override':'openscad_equipment',
                'regeneration_scope':['vision_camera','servo_motor'],
                'regeneration_reason':'multiview_contract_failure',
            },
            format='json',
        )

    assert response.status_code == 202
    job=GenerationJob.objects.get(pk=response.json()['job']['id'])
    assert job.payload['regeneration_scope'] == ['vision_camera','servo_motor']
    assert job.payload['regeneration_reason'] == 'multiview_contract_failure'
    delay.assert_called_once_with(
        str(job.id),
        concept.pk,
        'structural',
        'standard',
        'openscad_equipment',
        ['vision_camera','servo_motor'],
        'multiview_contract_failure',
    )


@pytest.mark.django_db
def test_partial_regeneration_scope_rejects_unsafe_tokens():
    project=Project.objects.create(
        id='PRJ-PARTIAL-INVALID',
        prompt='잘못된 부분 재생성 범위를 거부하는 충분히 긴 테스트 프롬프트',
        category='equipment',
        status='2d_ready',
    )
    concept=Concept2D.objects.create(
        project=project,
        concept_id='CONCEPT-1',
        title='Safety Cover',
        public_url='/storage/concept-1.png',
        relative_path='projects/PRJ-PARTIAL-INVALID/concepts/concept-1.png',
    )

    response=APIClient().post(
        f'/api/projects/{project.id}/generate-3d',
        {
            'selected_2d_id':concept.concept_id,
            'regeneration_scope':['../../unsafe'],
        },
        format='json',
    )

    assert response.status_code == 422
