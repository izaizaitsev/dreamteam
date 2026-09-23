FROM python:3.12-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY requirements-documents.txt .
RUN pip install --no-cache-dir --retries 10 --timeout 60 -r requirements-documents.txt
COPY . .
ENV PYTHONPATH=/code
