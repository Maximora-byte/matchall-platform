FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py snapshot.py ./
COPY templates ./templates
COPY static ./static
COPY docs ./docs
RUN useradd --system --uid 10001 hub && mkdir -p /data/status /data/snapshots && chown -R hub:hub /data
USER hub
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
