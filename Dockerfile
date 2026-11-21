FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY config.yaml .
COPY topics/ topics/
COPY evidence/ evidence/
COPY entrypoint.sh .
ENV PORT=8080
ENTRYPOINT ["./entrypoint.sh"]
CMD ["serve"]
