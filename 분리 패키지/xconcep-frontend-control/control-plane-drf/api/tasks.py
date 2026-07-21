from celery import shared_task


@shared_task(name='xconcep.health_task')
def health_task():
    return {'status':'ok'}


@shared_task(name='xconcep.generate_2d')
def generate_2d_task(job_id, asset_ids=None, meeting_analysis=None):
    from .models import Asset, GenerationJob
    from . import services

    job=GenerationJob.objects.select_related('project').get(pk=job_id)
    assets=list(Asset.objects.filter(project=job.project,pk__in=asset_ids or []))
    return services.generate_2d(job.project,assets,meeting_analysis,job=job)


@shared_task(name='xconcep.generate_3d')
def generate_3d_task(job_id, concept_pk, output_goal, quality_profile, engine_override=None):
    from .models import Concept2D, GenerationJob
    from . import services

    job=GenerationJob.objects.select_related('project').get(pk=job_id)
    selected=Concept2D.objects.get(pk=concept_pk,project=job.project)
    return services.generate_3d(
        job.project,selected,output_goal,quality_profile,engine_override,job=job,
    )
