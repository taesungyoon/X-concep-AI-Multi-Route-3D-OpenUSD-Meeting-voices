"""HTTP control plane for authenticated, queued generation workflows.

The frontend talks only to these endpoints. This layer owns MySQL project/job
state and uploads, then delegates heavy work through Celery -> agent gateway ->
Python worker. Meeting audio follows create -> chunk/transcribe -> analyze ->
generate-2D, after which it rejoins the normal select-2D -> generate-3D flow.
"""

import re
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import connections
from .models import Project, GenerationJob
from .serializers import ProjectSerializer, JobSerializer
from .clients import agent_client, knowledge_client
from . import services
from .tasks import generate_2d_task, generate_3d_task
from .corporate_auth import (
    CorporateAuthenticationError,
    authenticate_corporate_user,
    issue_token,
    probe_corporate_database,
)

def project_data(p): return ProjectSerializer(p).data

def queued_response(project, job):
    """Return the stable HTTP 202 contract consumed by UI/smoke-test polling."""
    return Response({'project':project_data(project),'job':JobSerializer(job).data},status=202)

def queue_2d(project, assets, meeting_analysis=None):
    """Persist the job before dispatch so queue failures remain observable."""
    payload={'asset_ids':[a.pk for a in assets],'meeting_analysis':meeting_analysis}
    job=services.create_queued_job(project,'generate_2d',payload)
    project.status='queued_2d'; project.progress=0; project.step='compare'; project.save()
    try: generate_2d_task.delay(str(job.id),payload['asset_ids'],meeting_analysis)
    except Exception as exc:
        services.fail_job(job,exc); project.status='failed'; project.save(update_fields=['status','updated_at']); raise
    return job

@api_view(['GET'])
def health(request):
    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT 1')
        database_ok = cursor.fetchone() == (1,)
    return Response({'status':'ok','service':'drf-control-plane','database':'connected' if database_ok else 'degraded'})


@api_view(['GET'])
def auth_config(request):
    return Response({
        'mode': settings.AUTH_MODE,
        'required': settings.AUTH_MODE in settings.AUTH_REQUIRED_MODES,
        'token_ttl_seconds': settings.AUTH_TOKEN_TTL_SECONDS,
    })


@api_view(['POST'])
def auth_login(request):
    if settings.AUTH_MODE not in settings.AUTH_REQUIRED_MODES:
        return Response({'error':'DB 인증이 활성화되지 않음'}, status=409)
    try:
        user = authenticate_corporate_user(
            str(request.data.get('username') or ''),
            str(request.data.get('password') or ''),
        )
    except CorporateAuthenticationError:
        return Response({'error':'아이디 또는 비밀번호가 올바르지 않음'}, status=401)
    return Response({
        'token': issue_token(user),
        'token_type': 'Bearer',
        'expires_in': settings.AUTH_TOKEN_TTL_SECONDS,
        'user': user.public(),
    })


@api_view(['GET'])
def auth_me(request):
    user = getattr(request, 'corporate_user', None)
    if user is None:
        return Response({'authenticated': False}, status=401)
    return Response({'authenticated': True, 'user': user.public()})

@api_view(['GET'])
def system_status(request):
    auth_status = {'mode': settings.AUTH_MODE, 'required': settings.AUTH_MODE in settings.AUTH_REQUIRED_MODES}
    if settings.AUTH_MODE in settings.AUTH_REQUIRED_MODES:
        try: auth_status['database_connected'] = probe_corporate_database()
        except Exception as exc:
            auth_status.update({'database_connected': False, 'error': type(exc).__name__})
    out={'control_plane':'ok', 'authentication': auth_status}
    try:
        agent=agent_client.health()
        out.update(agent.get('worker') or {})
        out['agent_layer']={'status':agent.get('status'),'runtime':agent.get('runtime'),'nat_profile_available':agent.get('nat_profile_available')}
    except Exception as exc:
        out['agent_layer']={'status':'degraded','error':str(exc)}
    try: out['knowledge']=knowledge_client.health()
    except Exception as exc: out['knowledge']={'status':'degraded','error':str(exc)}
    return Response({'worker':out})

@api_view(['GET','POST'])
@parser_classes([MultiPartParser,FormParser,JSONParser])
def projects(request):
    """List recent work or create a prompt/image project and start 2D generation."""
    if request.method=='GET':
        qs=Project.objects.order_by('-updated_at')[:20]
        items=[]
        for p in qs:
            data=project_data(p); thumb=None
            if p.result_3d: thumb=p.result_3d.get('preview_url')
            elif p.concepts.exists(): thumb=p.concepts.first().public_url
            items.append({'id':p.id,'prompt':p.prompt,'category':p.category,'status':p.status,'step':p.step,'thumbnail':thumb,'updated_at':p.updated_at})
        return Response({'items':items})
    prompt=(request.data.get('prompt') or '').strip(); category=(request.data.get('category') or 'equipment').strip()
    output_goal=(request.data.get('output_goal') or 'auto').strip(); quality_profile=(request.data.get('quality_profile') or 'standard').strip()
    if len(prompt)<8: return Response({'error':'프롬프트를 8자 이상 입력해야 함'},status=422)
    if category not in {'equipment','module','part'}: return Response({'error':'지원하지 않는 생성 유형임'},status=422)
    if output_goal not in {'auto','fast','structural','high_quality','motion_openusd'}: return Response({'error':'지원하지 않는 결과 방식임'},status=422)
    if quality_profile not in {'preview','standard','final'}: return Response({'error':'지원하지 않는 품질 프로필임'},status=422)
    p=services.new_project(prompt,category,output_goal=output_goal,quality_profile=quality_profile)
    files=request.FILES.getlist('images[]') or request.FILES.getlist('images')
    try: assets=services.save_images(p,files)
    except ValueError as exc:
        p.delete(); return Response({'error':str(exc)},status=422)
    if not settings.SYNC_PIPELINE:
        try: return queued_response(p,queue_2d(p,assets))
        except Exception as exc: return Response({'error':f'작업 큐 등록 실패: {exc}'},status=503)
    try: services.generate_2d(p,assets)
    except Exception as exc: return Response({'error':str(exc)},status=502)
    return Response({'project':project_data(p)},status=201)

@api_view(['POST'])
def meetings(request):
    """Create the project shell used by streamed meeting-audio workflows."""
    category=(request.data.get('category') or 'equipment').strip()
    if category not in {'equipment','module','part'}: return Response({'error':'지원하지 않는 생성 유형임'},status=422)
    output_goal=(request.data.get('output_goal') or 'auto').strip(); quality_profile=(request.data.get('quality_profile') or 'standard').strip()
    p=services.new_project('회의 음성 분석 대기',category,meeting=True,output_goal=output_goal,quality_profile=quality_profile)
    return Response({'project':project_data(p)},status=201)

@api_view(['GET'])
def project_detail(request,project_id): return Response({'project':project_data(get_object_or_404(Project,pk=project_id))})

@api_view(['POST'])
def project_generate_3d(request,project_id):
    """Validate a selected concept and enqueue the planned multi-route 3D job."""
    p=get_object_or_404(Project,pk=project_id); cid=(request.data.get('selected_2d_id') or '').strip(); selected=p.concepts.filter(concept_id=cid).first()
    if not selected: return Response({'error':'선택한 2D 결과가 올바르지 않음'},status=422)
    output_goal=(request.data.get('output_goal') or p.output_goal or 'auto').strip()
    quality_profile=(request.data.get('quality_profile') or p.quality_profile or 'standard').strip()
    engine_override=(request.data.get('engine_override') or '').strip() or None
    raw_scope=request.data.get('regeneration_scope') or []
    if isinstance(raw_scope,str): raw_scope=[raw_scope]
    if not isinstance(raw_scope,list):
        return Response({'error':'부분 재생성 범위는 배열이어야 함'},status=422)
    regeneration_scope=[str(value).strip() for value in raw_scope if str(value).strip()]
    if len(regeneration_scope)>32 or any(len(value)>80 or not re.fullmatch(r'[A-Za-z0-9_:-]+',value) for value in regeneration_scope):
        return Response({'error':'부분 재생성 범위 형식이 올바르지 않음'},status=422)
    regeneration_reason=str(request.data.get('regeneration_reason') or '').strip()
    if len(regeneration_reason)>500:
        return Response({'error':'부분 재생성 사유가 너무 김'},status=422)
    if not settings.SYNC_PIPELINE:
        payload={'concept_pk':selected.pk,'output_goal':output_goal,'quality_profile':quality_profile,'engine_override':engine_override,'regeneration_scope':regeneration_scope,'regeneration_reason':regeneration_reason}
        job=services.create_queued_job(p,'generate_3d',payload)
        p.status='queued_3d'; p.progress=0; p.step='result'; p.save()
        try: generate_3d_task.delay(str(job.id),selected.pk,output_goal,quality_profile,engine_override,regeneration_scope,regeneration_reason)
        except Exception as exc:
            services.fail_job(job,exc); p.status='failed'; p.save(update_fields=['status','updated_at'])
            return Response({'error':f'작업 큐 등록 실패: {exc}'},status=503)
        return queued_response(p,job)
    try: services.generate_3d(p,selected,output_goal,quality_profile,engine_override,regeneration_scope,regeneration_reason)
    except Exception as exc: return Response({'error':str(exc)},status=502)
    return Response({'project':project_data(p)})

@api_view(['POST'])
@parser_classes([MultiPartParser,FormParser])
def meeting_chunk(request,project_id):
    p=get_object_or_404(Project,pk=project_id); f=request.FILES.get('audio')
    if not f: return Response({'error':'회의 음성 파일이 없음'},status=422)
    try:
        idx=int(request.data.get('chunk_index',p.meeting.chunk_count))
        if idx < 0 or idx > 999999: raise ValueError('음성 청크 번호가 범위를 벗어남')
        rel=services.save_audio_chunk(p,f,idx)
    except (TypeError,ValueError) as exc: return Response({'error':str(exc)},status=422)
    try: result=services.transcribe_chunk(p,rel,idx)
    except Exception as exc: return Response({'error':str(exc)},status=502)
    return Response({'project':project_data(p),'chunk':result})

@api_view(['POST'])
def meeting_analyze(request,project_id):
    p=get_object_or_404(Project,pk=project_id); transcript=(request.data.get('transcript') or p.meeting.transcript or '').strip()
    if len(transcript)<2: return Response({'error':'분석할 회의 내용이 없음'},status=422)
    try: services.analyze_meeting(p,transcript)
    except Exception as exc: return Response({'error':str(exc)},status=502)
    return Response({'project':project_data(p)})

@api_view(['POST'])
def meeting_generate_2d(request,project_id):
    p=get_object_or_404(Project,pk=project_id)
    if not p.meeting.analysis: return Response({'error':'회의 분석을 먼저 수행해야 함'},status=422)
    if not settings.SYNC_PIPELINE:
        try: return queued_response(p,queue_2d(p,[],p.meeting.analysis))
        except Exception as exc: return Response({'error':f'작업 큐 등록 실패: {exc}'},status=503)
    try: services.generate_2d(p,[],p.meeting.analysis); p.meeting.status='2d_ready'; p.meeting.save()
    except Exception as exc: return Response({'error':str(exc)},status=502)
    return Response({'project':project_data(p)})

@api_view(['POST'])
def meeting_patch(request,project_id):
    p=get_object_or_404(Project,pk=project_id); transcript=(request.data.get('transcript') or p.meeting.transcript or '').strip()
    if not p.meeting.analysis: return Response({'error':'기존 회의 분석이 없음'},status=422)
    try: patch=services.patch_meeting(p,transcript)
    except Exception as exc: return Response({'error':str(exc)},status=502)
    return Response({'project':project_data(p),'patch':patch})

@api_view(['POST'])
def project_review_grade(request,project_id):
    p=get_object_or_404(Project,pk=project_id)
    requested=(request.data.get('requested_grade') or '').strip()
    reviewer=(request.data.get('reviewer') or '').strip()
    note=(request.data.get('note') or '').strip()
    if len(reviewer)<2: return Response({'error':'검토자 이름을 입력해야 함'},status=422)
    try: validation=services.apply_review_grade(p,requested,reviewer,note)
    except Exception as exc: return Response({'error':str(exc)},status=422)
    return Response({'project':project_data(p),'validation':validation})

@api_view(['GET'])
def job_detail(request,job_id): return Response({'job':JobSerializer(get_object_or_404(GenerationJob,pk=job_id)).data})

@api_view(['POST'])
def knowledge_ingest(request):
    try: return Response(knowledge_client.post('/v1/ingest',request.data,300))
    except Exception as exc: return Response({'error':str(exc)},status=502)
@api_view(['POST'])
def knowledge_search(request):
    try: return Response(knowledge_client.post('/v1/search',request.data,120))
    except Exception as exc: return Response({'error':str(exc)},status=502)
@api_view(['POST'])
def vision_event(request):
    # DeepStream/Metropolis events are optional extensions; store or route upstream here.
    return Response({'accepted':True,'event':request.data},status=202)

@api_view(['POST'])
@parser_classes([MultiPartParser,FormParser])
def knowledge_ingest_file(request):
    f=request.FILES.get('file')
    if not f: return Response({'error':'인제스트할 파일이 없음'},status=422)
    try:
        result=knowledge_client.post_file(
            '/v1/ingest/file',filename=f.name,content=f.read(),content_type=getattr(f,'content_type','application/octet-stream'),
            data={'project_id':request.data.get('project_id',''),'metadata_json':request.data.get('metadata_json','{}')},timeout=3600,
        )
        return Response(result)
    except Exception as exc: return Response({'error':str(exc)},status=502)
