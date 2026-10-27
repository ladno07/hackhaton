FROM python:3.12-slim
WORKDIR /workspace
COPY backend/requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app /workspace/backend/app
COPY bot /workspace/bot
ENV PYTHONPATH=/workspace:/workspace/backend
CMD ["python", "-m", "bot"]
