FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
ARG INSTALL_SPEECH=false
ARG INSTALL_NEMO_SPEECH=false
ARG INSTALL_OPENSCAD=false
ARG INSTALL_BLENDER=false
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 ca-certificates \
 && if [ "$INSTALL_OPENSCAD" = "true" ]; then apt-get install -y --no-install-recommends openscad; fi \
 && if [ "$INSTALL_BLENDER" = "true" ]; then apt-get install -y --no-install-recommends blender; fi \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-openusd.txt requirements-speech.txt requirements-nemo-speech.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$INSTALL_SPEECH" = "true" ]; then pip install --no-cache-dir -r requirements-speech.txt; fi \
 && if [ "$INSTALL_NEMO_SPEECH" = "true" ]; then pip install --no-cache-dir -r requirements-nemo-speech.txt; fi
COPY app ./app
COPY scripts ./scripts
EXPOSE 8001
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8001"]
