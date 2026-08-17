FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY database /app/database
COPY data /app/data
COPY docs /app/docs
COPY frontend/dist /app/frontend/dist
COPY .env.example /app/.env.example

ENV PYTHONPATH=/app/backend
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
