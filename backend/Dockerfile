FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /workspace

COPY backend/pyproject.toml /workspace/backend/pyproject.toml
RUN python -c "import subprocess,sys,tomllib; deps=tomllib.load(open('/workspace/backend/pyproject.toml','rb'))['project']['dependencies']; subprocess.check_call([sys.executable,'-m','pip','install','--no-cache-dir',*deps])"

COPY backend/app /workspace/app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
