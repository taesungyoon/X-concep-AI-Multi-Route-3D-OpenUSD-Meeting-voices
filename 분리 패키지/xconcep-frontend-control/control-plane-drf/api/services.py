from pathlib import Path
import os, secrets
from django.conf import settings
from django.db import transaction
from .models import Project, Asset, Concept2D, MeetingSession, TranscriptSegment, GenerationJob
from .clients import agent_client, knowledge_client

ALLOWED_IMAGE_MIMES={'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}
ALLOWED_AUDIO_EXTS={'webm','wav','mp3','m4a','ogg','flac'}

def public_url(relative: str) -> str: return '/storage/' + relative.replace(os.sep,'/')
def project_dir(project_id: str) -> Path:
    p=Path(settings.MEDIA_ROOT)/'projects'/project_id; p.mkdir(parents=True,exist_ok=True); return p

def new_project(prompt='', category='equipment', meeting=False, output_goal='auto', quality_profile='standard'):
    pid='PRJ-'+secrets.token_hex(5).upper()
    p=Project.objects.create(id=pid,prompt=prompt,category=category,status='created',progress=0,step='input',output_goal=output_goal,quality_profile=quality_profile)
    MeetingSession.objects.create(project=p,status='recording_ready' if meeting else 'idle')
    return p

def save_images(project, files):
    saved=[]; folder=project_dir(project.id)/'uploads'; folder.mkdir(parents=True,exist_ok=True)
    for i,f in enumerate(files[:4]):
        ext=ALLOWED_IMAGE_MIMES.get(getattr(f,'content_type',''))
        if not ext: continue
        name=f'source-{i+1:02d}-{secrets.token_hex(3)}.{ext}'; dest=folder/name
        with dest.open('wb') as out:
            for chunk in f.chunks(): out.write(chunk)
        rel=dest.relative_to(settings.MEDIA_ROOT).as_posix()
        asset=Asset.objects.create(project=project,kind='source_image',original_name=f.name,relative_path=rel,public_url=public_url(rel))
        saved.append(asset)
    return saved

def create_job(project, job_type, payload):
    return GenerationJob.objects.create(project=project,job_type=job_type,status='running',progress=10,payload=payload)

def complete_job(job,result):
    job.status='completed'; job.progress=100; job.result=result; job.save(update_fields=['status','progress','result','updated_at'])
def fail_job(job,exc):
    job.status='failed'; job.error=str(exc); job.save(update_fields=['status','error','updated_at'])

def generate_2d(project, image_assets=None, meeting_analysis=None):
    image_assets=image_assets if image_assets is not None else list(project.assets.filter(kind='source_image'))
    payload={'project_id':project.id,'prompt':project.prompt,'category':project.category,'image_paths':[a.relative_path for a in image_assets],'meeting_analysis':meeting_analysis}
    job=create_job(project,'generate_2d',payload)
    project.status='generating_2d'; project.progress=25; project.step='compare'; project.save()
    try:
        result=agent_client.post('/v1/workflows/generate-2d',payload,1800)
        project.concepts.all().delete()
        for item in result.get('results',[]):
            raw_path = Path(str(item.get('absolute_path','')))
            try:
                rel_path = raw_path.relative_to(settings.MEDIA_ROOT).as_posix()
            except Exception:
                rel_path = str(item.get('path') or item.get('absolute_path') or '').lstrip('/')
            Concept2D.objects.create(project=project,concept_id=item.get('id',''),title=item.get('title',''),description=item.get('description',''),public_url=item.get('url',''),relative_path=rel_path,metadata={k:v for k,v in item.items() if k not in {'id','title','description','url','absolute_path','path'}})
        project.analysis=result.get('analysis'); project.pipeline=result.get('pipeline'); project.status='2d_ready'; project.progress=100; project.save()
        complete_job(job,result); return result
    except Exception as exc:
        project.status='failed'; project.save(update_fields=['status','updated_at']); fail_job(job,exc); raise

def generate_3d(project, selected, output_goal=None, quality_profile=None, engine_override=None):
    output_goal=(output_goal or project.output_goal or 'auto').strip()
    quality_profile=(quality_profile or project.quality_profile or 'standard').strip()
    if output_goal not in {'auto','fast','structural','high_quality','motion_openusd'}:
        raise ValueError('지원하지 않는 결과 방식임')
    if quality_profile not in {'preview','standard','final'}:
        raise ValueError('지원하지 않는 품질 프로필임')
    payload={
        'project_id':project.id,
        'prompt':project.prompt,
        'category':project.category,
        'selected_2d_id':selected.concept_id,
        'selected_image_path':selected.relative_path,
        'meeting_analysis':project.meeting.analysis,
        'source_analysis':project.analysis,
        'revision':project.revision,
        'output_goal':output_goal,
        'quality_profile':quality_profile,
        'engine_override':engine_override or None,
        'previous_design_state':project.design_state,
    }
    job=create_job(project,'generate_3d',payload)
    project.status='generating_3d'; project.progress=35; project.step='result'; project.selected_2d_id=selected.concept_id
    project.output_goal=output_goal; project.quality_profile=quality_profile
    project.save()
    try:
        result=agent_client.post('/v1/workflows/generate-3d',payload,7200)
        result.pop('absolute_paths', None)
        current=project.result_3d or {'assets':{},'history':[]}
        current_assets=dict(current.get('assets') or {})
        current_assets.update(result.get('assets') or {})
        route_key=result.get('route_key') or result.get('active_asset') or output_goal
        current.update(result)
        current['assets']=current_assets
        current['active_asset']=route_key
        history=list(project.generation_history or [])
        history.append({
            'revision':project.revision,
            'output_goal':output_goal,
            'quality_profile':quality_profile,
            'active_asset':route_key,
            'validation_grade':result.get('validation_grade','concept'),
            'score':(result.get('validation') or {}).get('score'),
        })
        project.generation_history=history[-50:]
        project.result_3d=current
        project.design_state=result.get('design_state')
        project.generation_plan=result.get('generation_plan')
        project.validation_report=result.get('validation')
        project.validation_grade=result.get('validation_grade','concept')
        project.status='completed'; project.progress=100; project.save()
        complete_job(job,result)
        try: knowledge_client.post('/v1/assets/index',{'project_id':project.id,'prompt':project.prompt,'analysis':project.analysis or {},'design_state':project.design_state or {},'result':result},120)
        except Exception: pass
        return result
    except Exception as exc:
        project.status='failed'; project.save(update_fields=['status','updated_at']); fail_job(job,exc); raise


def apply_review_grade(project, requested_grade, reviewer, note=''):
    allowed={'engineer_reviewed','manufacturing_approved'}
    if requested_grade not in allowed:
        raise ValueError('지원하지 않는 검토 등급임')
    validation=dict(project.validation_report or {})
    current=project.validation_grade or validation.get('grade','concept')
    order=['concept','structured','validated','engineer_reviewed','manufacturing_approved']
    if order.index(requested_grade) <= order.index(current):
        raise ValueError('현재 등급보다 높은 검토 등급만 적용할 수 있음')
    validation['grade']=requested_grade
    validation['grade_label']={'engineer_reviewed':'엔지니어 검토 완료','manufacturing_approved':'제조 승인 완료'}[requested_grade]
    validation['manual_review']={'reviewer':reviewer,'note':note}
    project.validation_grade=requested_grade
    project.validation_report=validation
    if project.result_3d:
        result=dict(project.result_3d)
        result['validation_grade']=requested_grade
        result['validation_grade_label']=validation['grade_label']
        result['validation']=validation
        project.result_3d=result
    project.save()
    return validation

def save_audio_chunk(project, file, chunk_index):
    ext=Path(file.name).suffix.lower().lstrip('.') or 'webm'
    if ext not in ALLOWED_AUDIO_EXTS: ext='webm'
    folder=project_dir(project.id)/'meeting'/'audio'; folder.mkdir(parents=True,exist_ok=True)
    dest=folder/f'chunk-{chunk_index:04d}-{secrets.token_hex(3)}.{ext}'
    with dest.open('wb') as out:
        for chunk in file.chunks(): out.write(chunk)
    return dest.relative_to(settings.MEDIA_ROOT).as_posix()

def transcribe_chunk(project, relative_path, chunk_index, language='ko'):
    payload={'project_id':project.id,'audio_path':relative_path,'chunk_index':chunk_index,'language':language}
    result=agent_client.post('/v1/workflows/meeting-transcribe',payload,900)
    meeting=project.meeting
    for segment in result.get('segments',[]):
        TranscriptSegment.objects.create(meeting=meeting,chunk_index=chunk_index,start=segment.get('start',0),end=segment.get('end',0),speaker=segment.get('speaker','SPEAKER_00'),text=segment.get('text',''),confidence=segment.get('confidence',0))
    text=(result.get('text') or '').strip(); meeting.transcript=(meeting.transcript+' '+text).strip(); meeting.chunk_count=max(meeting.chunk_count,chunk_index+1); meeting.status='transcribing'; meeting.provider=result.get('provider',''); meeting.save(); return result

def analyze_meeting(project, transcript):
    meeting=project.meeting; meeting.transcript=transcript.strip(); meeting.save(update_fields=['transcript','updated_at'])
    context=[]
    try: context=knowledge_client.post('/v1/search',{'query':meeting.transcript,'limit':5},60).get('items',[])
    except Exception: pass
    payload={'project_id':project.id,'category':project.category,'transcript':meeting.transcript,'segments':list(meeting.segments.values('start','end','speaker','text','confidence')),'previous_analysis':meeting.analysis,'retrieval_context':context,'reference_image_paths':[]}
    result=agent_client.post('/v1/workflows/meeting-analyze',payload,900)
    meeting.analysis=result.get('analysis'); meeting.status='analyzed'; meeting.save(); project.prompt=result.get('generation_prompt') or meeting.transcript; project.save(update_fields=['prompt','updated_at']); return result

def patch_meeting(project, transcript):
    payload={'project_id':project.id,'base_revision':project.revision,'transcript':transcript,'current_analysis':project.meeting.analysis or {}}
    result=agent_client.post('/v1/workflows/meeting-patch',payload,900)
    project.revision=result.get('next_revision',project.revision+1); project.meeting.analysis=result.get('analysis',project.meeting.analysis); project.meeting.save(); project.prompt=(project.meeting.analysis or {}).get('generation_prompt',project.prompt); project.save(); return result
