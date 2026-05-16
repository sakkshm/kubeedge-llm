FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi==0.110.0 \
    uvicorn==0.28.0 \
    httpx==0.27.0 \
    pydantic==2.6.4

COPY main.py .

EXPOSE 8001

ENTRYPOINT ["python3", "main.py"]