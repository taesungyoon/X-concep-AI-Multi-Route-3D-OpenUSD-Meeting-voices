from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Project, GenerationJob
from .serializers import ProjectSerializer, JobSerializer
from .clients import agent_client, knowledge_client
from . import services

def project_data(p): return ProjectSerializer(p).data

@api_view(['GET'])
def health(request):
    return Response({'status':'ok','service':'drf-control-plane','database':'connected'})

@api_view(['GET'])
def system_status(request):
    out={'control_plane':'ok'}
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
    assets=services.save_images(p,files)
    try: services.generate_2d(p,assets)
    except Exception as exc: return Response({'error':str(exc)},status=502)
    return Response({'project':project_data(p)},status=201)

@api_view(['POST'])
def meetings(request):
    category=(request.data.get('category') or 'equipment').strip()
    if category not in {'equipment','module','part'}: return Response({'error':'지원하지 않는 생성 유형임'},status=422)
    output_goal=(request.data.get('output_goal') or 'auto').strip(); quality_profile=(request.data.get('quality_profile') or 'standard').strip()
    p=services.new_project('회의 음성 분석 대기',category,meeting=True,output_goal=output_goal,quality_profile=quality_profile)
    return Response({'project':project_data(p)},status=201)

@api_view(['GET'])
def project_detail(request,project_id): return Response({'project':project_data(get_object_or_404(Project,pk=project_id))})

@api_view(['POST'])
def project_generate_3d(request,project_id):
    p=get_object_or_404(Project,pk=project_id); cid=(request.data.get('selected_2d_id') or '').strip(); selected=p.concepts.filter(concept_id=cid).first()
    if not selected: return Response({'error':'선택한 2D 결과가 올바르지 않음'},status=422)
    output_goal=(request.data.get('output_goal') or p.output_goal or 'auto').strip()
    quality_profile=(request.data.get('quality_profile') or p.quality_profile or 'standard').strip()
    engine_override=(request.data.get('engine_override') or '').strip() or None
    try: services.generate_3d(p,selected,output_goal,quality_profile,engine_override)
    except Exception as exc: return Response({'error':str(exc)},status=502)
    return Response({'project':project_data(p)})

@api_view(['POST'])
@parser_classes([MultiPartParser,FormParser])
def meeting_chunk(request,project_id):
    p=get_object_or_404(Project,pk=project_id); f=request.FILES.get('audio')
    if not f: return Response({'error':'회의 음성 파일이 없음'},status=422)
    idx=int(request.data.get('chunk_index',p.meeting.chunk_count)); rel=services.save_audio_chunk(p,f,idx)
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
