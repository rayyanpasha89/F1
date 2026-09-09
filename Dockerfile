FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/* \
 && curl --fail --silent --show-error https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -o /usr/local/share/ca-certificates/rds-global.pem \
 && useradd --uid 10001 --create-home app
COPY requirements.runtime.lock .
RUN pip install --no-cache-dir -r requirements.runtime.lock
COPY backend backend
COPY knowledge knowledge
COPY scripts scripts
COPY reports/data_audit.json reports/data_audit.json
COPY models/*.joblib models/
USER app
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
