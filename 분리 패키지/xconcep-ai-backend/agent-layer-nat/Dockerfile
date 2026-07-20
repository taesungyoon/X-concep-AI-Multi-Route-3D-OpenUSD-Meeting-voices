FROM python:3.12-slim
WORKDIR /app
ARG INSTALL_NAT=false
COPY requirements.txt requirements-nat.txt ./
RUN pip install --no-cache-dir -r requirements.txt && if [ "$INSTALL_NAT" = "true" ]; then pip install --no-cache-dir -r requirements-nat.txt; fi
COPY . .
CMD ["uvicorn","gateway:app","--host","0.0.0.0","--port","8010"]
