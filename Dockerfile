FROM python:3.13-slim

ARG AGENT_MODULE
ENV AGENT_MODULE=${AGENT_MODULE} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 agent \
    && chown -R agent:agent /app

USER agent
EXPOSE 8088

CMD ["sh", "-c", "exec python -m \"$AGENT_MODULE\""]