FROM node:20-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends bash python3 python3-pip python3-venv \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY whatsapp-gateway/package.json /app/whatsapp-gateway/package.json
COPY whatsapp-gateway/package-lock.json /app/whatsapp-gateway/package-lock.json
RUN cd /app/whatsapp-gateway && npm ci

COPY . /app

RUN cd /app/whatsapp-gateway && npm run build
RUN chmod +x /app/scripts/start-single-service.sh

ENV NODE_ENV=production
ENV INSTANCE_NAME=observer
ENV WHATSAPP_GATEWAY_PORT=10001
ENV QR_EXPIRES_SECONDS=60
ENV RECONNECT_DELAY_MS=5000

CMD ["bash", "/app/scripts/start-single-service.sh"]
