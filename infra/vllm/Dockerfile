FROM vllm/vllm-openai:latest

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN mkdir -p /models

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PORT=8000 \
    MODEL_NAME="Qwen/Qwen2.5-7B-Instruct" \
    MODEL_PATH="/models/best_model" \
    GPU_MEMORY_UTILIZATION="0.90" \
    MAX_MODEL_LEN="8192"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
