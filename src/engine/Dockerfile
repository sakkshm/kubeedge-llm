FROM python:3.11-slim-bookworm

WORKDIR /workspace

# Install system compilation utilities safely
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install the server flavor of llama-cpp-python optimized for CPU execution
RUN pip install --no-cache-dir 'llama-cpp-python[server]'

# Pre-download and cache the 4-bit quantized GGUF weights during build phase
RUN curl -L https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf \
    -o /workspace/qwen2.5-0.5b-instruct-q4_k_m.gguf

EXPOSE 8000

ENV MODEL=/workspace/qwen2.5-0.5b-instruct-q4_k_m.gguf
ENV HOST=0.0.0.0
ENV PORT=8000

# Fixed context window sizing ensures predictable memory ceilings on tight nodes
ENTRYPOINT ["python3", "-m", "llama_cpp.server", "--model", "/workspace/qwen2.5-0.5b-instruct-q4_k_m.gguf", "--n_ctx", "2048"]