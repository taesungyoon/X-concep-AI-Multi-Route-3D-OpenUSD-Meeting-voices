from django.urls import path
from . import views
urlpatterns=[
 path('health',views.health), path('api/system-status',views.system_status),
 path('api/auth/config',views.auth_config), path('api/auth/login',views.auth_login), path('api/auth/me',views.auth_me),
 path('api/projects',views.projects), path('api/meetings',views.meetings),
 path('api/projects/<str:project_id>',views.project_detail), path('api/projects/<str:project_id>/generate-3d',views.project_generate_3d), path('api/projects/<str:project_id>/review-grade',views.project_review_grade),
 path('api/projects/<str:project_id>/meeting/chunks',views.meeting_chunk), path('api/projects/<str:project_id>/meeting/analyze',views.meeting_analyze),
 path('api/projects/<str:project_id>/meeting/generate-2d',views.meeting_generate_2d), path('api/projects/<str:project_id>/meeting/patch',views.meeting_patch),
 path('api/jobs/<uuid:job_id>',views.job_detail), path('api/knowledge/ingest',views.knowledge_ingest), path('api/knowledge/ingest-file',views.knowledge_ingest_file), path('api/knowledge/search',views.knowledge_search),
 path('api/vision/events',views.vision_event),
]
