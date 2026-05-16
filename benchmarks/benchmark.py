import time
import json
import sys
import requests

def run_streaming_benchmark(url, prompt):
    payload = {
        "model": "qwen2.5-0.5b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": True
    }
    
    start_time = time.time()
    ttft = None
    total_tokens = 0
    
    try:
        # Route streaming request directly through the sidecar proxy guardrail
        response = requests.post(url, json=payload, stream=True, timeout=15)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8').strip()
                if decoded_line.startswith("data:"):
                    # Capture exact delta when the first token chunk drops
                    if ttft is None:
                        ttft = (time.time() - start_time) * 1000
                    
                    data_str = decoded_line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data_json = json.loads(data_str)
                        if "choices" in data_json and len(data_json["choices"]) > 0:
                            delta = data_json["choices"][0].get("delta", {})
                            if "content" in delta:
                                total_tokens += 1
                    except Exception:
                        pass

        total_time = (time.time() - start_time) * 1000
        
        # Calculate true decoding throughput (excluding prefill time)
        decoding_time_sec = (total_time - (ttft or 0)) / 1000
        throughput = total_tokens / decoding_time_sec if decoding_time_sec > 0 else 0
        
        metrics = {
            "status": "SUCCESS",
            "ttft_ms": round(ttft, 2) if ttft else 0,
            "total_time_ms": round(total_time, 2),
            "tokens_generated": total_tokens,
            "throughput_tokens_per_sec": round(throughput, 2)
        }
        print(json.dumps(metrics))

    except Exception as e:
        print(json.dumps({"status": "FAILED", "error": str(e)}))

if __name__ == "__main__":
    # Points to the sidecar validation proxy port 8001 by default
    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://10.63.49.91:8001/v1/chat/completions"
    test_prompt = "Summarize industrial edge sensor anomalies in 3 bullet points."
    run_streaming_benchmark(target_url, test_prompt)