import sys
import time
import json
import requests

BASE_URL = "http://10.63.49.91:8001"

def print_separator():
    print("\n" + "="*60 + "\n")

def handle_summarization():
    print_separator()
    print("--- Industrial Log Summarization Client ---")
    print("Paste or type your raw log entry below. Press Enter when done.")
    raw_text = input("> ").strip()
    
    if not raw_text:
        print("Error: Input text cannot be empty.")
        return

    url = f"{BASE_URL}/v1/tasks/summarize"
    payload = {"text": raw_text}
    
    print("\nSending document payload to edge sidecar task wrapper...")
    try:
        start_time = time.time()
        response = requests.post(url, json=payload, timeout=40)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            print("\n[Execution Summary]")
            print(f"Summary: {result['summary']}")
            print(f"Sidecar Measured Latency: {result['latency_ms']}ms")
            print(f"Tokens Generated: {result['tokens_generated']}")
            print(f"Total Network Roundtrip: {int(elapsed * 1000)}ms")
        elif response.status_code == 503:
            print("Error: The inference engine is still warming up or loading models.")
        elif response.status_code == 429:
            print("Error: Node concurrency limit reached. Your request was throttled to protect EdgeCore.")
        else:
            print(f"Error: Sidecar returned status code {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Network error encountered: {e}")

def handle_chatbot():
    print_separator()
    print("--- Edge Core Chatbot Interface (Streaming Proxy) ---")
    print("Type your prompt or question below. Type 'exit' to return to menu.")
    
    url = f"{BASE_URL}/v1/chat/completions"
    
    while True:
        prompt = input("\nYou: ").strip()
        if not prompt:
            continue
        if prompt.lower() == 'exit':
            break
            
        payload = {
            "model": "qwen2.5-0.5b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": True
        }
        
        print("AI: ", end="", flush=True)
        try:
            response = requests.post(url, json=payload, stream=True, timeout=15)
            if response.status_code != 200:
                print(f"\nError: Server returned status code {response.status_code}")
                continue
                
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8').strip()
                    if decoded.startswith("data:"):
                        data_str = decoded[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            if "choices" in data_json and len(data_json["choices"]) > 0:
                                chunk = data_json["choices"][0].get("delta", {}).get("content", "")
                                print(chunk, end="", flush=True)
                        except Exception:
                            continue
            print() # Print newline after stream terminates
        except Exception as e:
            print(f"\nNetwork connection failed during streaming operation: {e}")

def main():
    while True:
        print_separator()
        print("KubeEdge LLM Verification Gateway Client")
        print("1. Run Document Summarization Task (/v1/tasks/summarize)")
        print("2. Launch Interactive Streaming Chatbot (/v1/chat/completions)")
        print("3. Exit Client Application")
        
        choice = input("\nSelect an operational mode [1-3]: ").strip()
        
        if choice == "1":
            handle_summarization()
        elif choice == "2":
            handle_chatbot()
        elif choice == "3":
            print("Exiting evaluation environment.")
            sys.exit(0)
        else:
            print("Invalid input context. Please select a valid option.")

if __name__ == "__main__":
    main()