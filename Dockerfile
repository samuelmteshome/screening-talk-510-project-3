# One image for training and serving.
#   docker build -t screening-talk .
#   docker run -p 8080:8080 screening-talk            # serve the API on :8080
#   docker run screening-talk train --topic prostate  # train (needs the bucket or --data-uri)
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY config.yaml schema.yaml ./
COPY topics/ topics/
COPY evidence/ evidence/
# Trained models, if present at build time (models/<topic>/model.joblib). Otherwise set MODEL_URI_<TOPIC>.
COPY models/ models/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh && useradd --create-home app && chown -R app /app
USER app
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT
EXPOSE 8080
ENTRYPOINT ["./entrypoint.sh"]
CMD ["serve"]
