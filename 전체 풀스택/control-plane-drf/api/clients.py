from django.conf import settings
import httpx

class ServiceClient:
    def __init__(self, base_url: str): self.base_url = base_url.rstrip('/')
    def health(self):
        with httpx.Client(timeout=10) as c: r=c.get(self.base_url+'/health'); r.raise_for_status(); return r.json()
    def post(self, path: str, payload: dict, timeout: int=3600):
        with httpx.Client(timeout=timeout) as c: r=c.post(self.base_url+path,json=payload); r.raise_for_status(); return r.json()
    def post_file(self, path: str, *, filename: str, content: bytes, content_type: str, data: dict | None=None, timeout: int=3600):
        files={'file':(filename,content,content_type or 'application/octet-stream')}
        with httpx.Client(timeout=timeout) as c:
            r=c.post(self.base_url+path,files=files,data=data or {}); r.raise_for_status(); return r.json()

agent_client = ServiceClient(settings.AGENT_GATEWAY_URL)
knowledge_client = ServiceClient(settings.KNOWLEDGE_SERVICE_URL)
