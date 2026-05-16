# KubeEdge LLM Inference Infrastructure

This repository provides an reference architecture for deploying, managing, and benchmarking small-parameter Large Language Models (LLMs) on resource-constrained edge nodes using KubeEdge.



## Architecture & Core Features

* **Decoupled Health Probes & Cache Pre-Warming:** Manages large model cold-starts on constraint-heavy edge hardware by isolating health checks:
    * `livenessProbe` (`/health/live`): Instantly confirms operational status of the sidecar process.
    * `readinessProbe` (`/health/ready`): Blocks external edge routing via an initialization state latch. It executes a single-token internal warmup request to absorb initial prefill latencies before changing state to `200 OK`.


* **Concurrency Protection:** A strict asynchronous semaphore restricts execution to a single inference thread, dropping excess requests with an HTTP `429` status code to safeguard core edge node management daemons (`EdgeCore`) from CPU thrashing.
* **Resource Isolation Boundaries:** Embedded Kubernetes `ResourceQuota` and `LimitRange` manifests limit container resources (capped at 2GiB RAM for the model engine) to ensure cluster stability.
* **Automated Profiling Suite:** An automated telemetry collection engine tracks Time to First Token (TTFT), decoding throughput, request execution success, and network latency.

## Baseline Performance Benchmarks

The following evaluation dataset represents execution telemetry captured during automated stress testing cycles on the edge device node (`Qwen2.5-0.5B-Instruct-GGUF` via CPU inference):

| Iteration | Status | TTFT (ms) | Total Time (ms) | Tokens Generated | Throughput (Tokens/Sec) |
| --- | --- | --- | --- | --- | --- |
| 1 | SUCCESS | 510.46 | 8159.39 | 103 | 13.47 |
| 2 | SUCCESS | 94.84 | 7872.07 | 100 | 12.86 |
| 3 | SUCCESS | 65.70 | 8079.24 | 125 | 15.60 |
| 4 | SUCCESS | 97.06 | 6326.50 | 79 | 12.68 |
| 5 | SUCCESS | 98.43 | 7949.72 | 110 | 14.01 |

> *Note: The elevated Time to First Token (TTFT) observed during Iteration 1 reflects the initial KV-cache compilation overhead, which stabilizes below 100ms across subsequent transaction requests.*



## Directory Structure

```text
.
├── Makefile                     # Automation pipeline orchestration
├── benchmarks/                  # Metric scraping engines and saved telemetry data
├── deployments/
│   ├── apps/                    # Dual-container LLM Edge Pod deployment spec
│   └── system/                  # Compute quota boundaries and network service configurations
├── example/                     # Interactive verification gateway (Chat & Summarize)
└── src/
    ├── engine/                  # llama-cpp-python server with cached model weights
    └── sidecar/                 # FastAPI reverse proxy managing probes and traffic throttling

```



## Workflow Execution

### 1. Provision Infrastructure

Build images from local source: 
```bash
make build-images REGISTRY_NAME="docker.io/your-username"
```

or apply deployment configurations directly to your KubeEdge node:
```bash
make deploy-workload
```


### 2. Run Performance Evaluation

The initialization phase handles cold-start pre-warming automatically. The sidecar proxy returns HTTP `503` while mapping weights into RAM. Once the prefill sequence completes, the deployment enters a ready state and triggers the evaluation runner:

```bash
make run-evaluation NODE_IP="10.63.49.91"
```

```text
[INIT] Waiting for edge node sidecar to clear cold-start pre-warming...
[WAIT] Mapping GGUF weights into host RAM (HTTP Status: 503)...
[READY] Model runtime cache is warm. Starting evaluation cycle.

RUN    | STATUS   | TTFT (ms)  | TOTAL TIME    | TOKENS   | TOKENS/SEC 
-----------------------------------------------------------------=
#1     | SUCCESS  | 510.46ms   | 8159.39ms     | 103      | 13.47     
#2     | SUCCESS  | 94.84ms    | 7872.07ms     | 100      | 12.86     

```

### 3. Edge-Scenario Validation

An interactive verification client validates specific lightweight edge workloads against the deployed proxy:

```bash
python3 example/main.py
```

* **Pathway 1 (Log Summarization):** Transmits raw text to `/v1/tasks/summarize`, triggering a low-temperature configuration (`0.1`) to generate deterministic single-sentence summaries.
* **Pathway 2 (Interactive Streaming):** Connects to `/v1/chat/completions` for real-time, token-by-token terminal delivery.


## Resource Budget Allocations

| Component | Compute Request | Compute Limit |
| --- | --- | --- |
| **Inference Engine (CPU)** | `1.0 Core` | `1.5 Cores` |
| **Inference Engine (RAM)** | `1Gi` | `2Gi` |
| **Stability Sidecar (CPU)** | `0.2 Core` | `0.2 Cores` |
| **Stability Sidecar (RAM)** | `256Mi` | `256Mi` |



## Infrastructure Teardown

To clear pods, namespace isolates, service configurations, and temporary evaluation logs:

```bash
make clean-all
```