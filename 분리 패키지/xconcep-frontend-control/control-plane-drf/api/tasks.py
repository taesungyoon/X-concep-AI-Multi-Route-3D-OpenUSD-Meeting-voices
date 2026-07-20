from celery import shared_task
@shared_task(name='xconcep.health_task')
def health_task(): return {'status':'ok'}
