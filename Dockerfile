FROM node:20-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends bash python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip3 install --no-cache-dir -r /app/backend/requirements.txt

COPY whatsapp-gateway/package.json /app/whatsapp-gateway/package.json
COPY whatsapp-gateway/package-lock.json /app/whatsapp-gateway/package-lock.json
RUN cd /app/whatsapp-gateway && npm ci

COPY . /app

RUN cd /app/whatsapp-gateway && npm run build
RUN chmod +x /app/scripts/start-single-service.sh

ENV NODE_ENV=production
ENV INSTANCE_NAME=observer
ENV WHATSAPP_GATEWAY_PORT=10001
ENV WHATSAPP_AUTH_DIR=/var/data/baileys-auth
ENV QR_EXPIRES_SECONDS=60
ENV RECONNECT_DELAY_MS=5000

CMD ["bash", "/app/scripts/start-single-service.sh"]
