FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/server.py backend/sciences.py backend/sites.py backend/projects.py backend/auth.py backend/dashboard_api.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "server.py"]
