FROM python:3.12-slim
WORKDIR /app
ARG INSTALL_NEMO_RETRIEVER=false
COPY requirements.txt requirements-nemo-retriever.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$INSTALL_NEMO_RETRIEVER" = "true" ]; then pip install --no-cache-dir -r requirements-nemo-retriever.txt; fi
COPY . .
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8020"]
