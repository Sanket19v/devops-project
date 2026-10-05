# build from this folder:  docker build -t copilot:local .
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY copilot.py .
ENV PYTHONPATH=/app
CMD ["uvicorn", "copilot:app", "--host", "0.0.0.0", "--port", "8000"]
