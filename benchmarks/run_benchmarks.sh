#!/usr/bin/env bash
set -euo pipefail

# Fallback to local loopback if edge node target IP isn't explicitly defined
TARGET_NODE_IP=${1:-"127.0.0.1"}
HEALTH_ENDPOINT="http://${TARGET_NODE_IP}:8001/health/ready"
INFERENCE_ENDPOINT="http://${TARGET_NODE_IP}:8001/v1/chat/completions"
OUTPUT_FILE="benchmarks/reports/results.csv"

# Define standard ANSI color codes for terminal formatting
COLOR_RESET="\033[0m"
COLOR_INFO="\033[0;36m"    # Cyan
COLOR_WARN="\033[1;33m"    # Yellow
COLOR_SUCCESS="\033[0;32m" # Green
COLOR_FAIL="\033[0;31m"    # Red
COLOR_BOLD="\033[1m"       # Bold White

mkdir -p benchmarks/reports

echo -e "${COLOR_BOLD}=====================================================================${COLOR_RESET}"
echo -e "${COLOR_INFO}KUBEDGE STANDALONE LLM PERFORMANCE EVALUATION SUITE${COLOR_RESET}"
echo -e "${COLOR_BOLD}=====================================================================${COLOR_RESET}"
echo -e "${COLOR_INFO}Target Node IP :${COLOR_RESET} ${TARGET_NODE_IP}"
echo -e "${COLOR_INFO}Endpoint URL   :${COLOR_RESET} ${INFERENCE_ENDPOINT}"
echo -e "${COLOR_INFO}Output Target  :${COLOR_RESET} ${OUTPUT_FILE}"
echo -e "${COLOR_BOLD}--------------------------------------------------------------------=${COLOR_RESET}"

# 1. Operational Gatekeeper Check
echo -e "${COLOR_WARN}[INIT] Waiting for edge node sidecar to clear cold-start pre-warming...${COLOR_RESET}"
while true; do
    STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_ENDPOINT" || echo "000")
    if [ "$STATUS_CODE" == "200" ]; then
        echo -e "${COLOR_SUCCESS}[READY] Model runtime cache is warm. Starting evaluation cycle.${COLOR_RESET}"
        break
    fi
    echo -e "   [WAIT] Mapping GGUF weights into host RAM (HTTP Status: ${COLOR_FAIL}${STATUS_CODE}${COLOR_RESET})..."
    sleep 3
done

# Initialize fresh report with structured schema headers
echo "Iteration,Status,TTFT_ms,TotalTime_ms,Tokens,TokensPerSec" > "$OUTPUT_FILE"

echo -e "\n${COLOR_BOLD}=====================================================================${COLOR_RESET}"
echo -e "${COLOR_INFO}LIVE TELEMETRY STREAMING OUTPUT${COLOR_RESET}"
echo -e "${COLOR_BOLD}=====================================================================${COLOR_RESET}"
# Format console header rows cleanly using strict padding widths
printf "${COLOR_BOLD}%-6s | %-8s | %-10s | %-13s | %-8s | %-10s${COLOR_RESET}\n" "RUN" "STATUS" "TTFT (ms)" "TOTAL TIME" "TOKENS" "TOKENS/SEC"
echo -e "${COLOR_BOLD}--------------------------------------------------------------------=${COLOR_RESET}"

# 2. Automated Workload Progression
for i in {1..5}; do
    # Execute metric scraping engine
    RESULT=$(python3 benchmarks/benchmark.py "$INFERENCE_ENDPOINT" 2>/dev/null || echo '{"status": "FAILED"}')
    STATUS=$(echo "$RESULT" | grep -o '"status": "[^"]*' | grep -o '[^"]*$')
    
    if [ "$STATUS" == "SUCCESS" ]; then
        TTFT=$(echo "$RESULT" | grep -o '"ttft_ms": [0-9.]*' | awk '{print $2}')
        TOTAL=$(echo "$RESULT" | grep -o '"total_time_ms": [0-9.]*' | awk '{print $2}')
        TOKENS=$(echo "$RESULT" | grep -o '"tokens_generated": [0-9]*' | awk '{print $2}')
        TPS=$(echo "$RESULT" | grep -o '"throughput_tokens_per_sec": [0-9.]*' | awk '{print $2}')
        
        # Save raw numbers cleanly to file csv
        echo "$i,$STATUS,$TTFT,$TOTAL,$TOKENS,$TPS" >> "$OUTPUT_FILE"
        
        # Print formatted color console row
        printf "%-6s | ${COLOR_SUCCESS}%-8s${COLOR_RESET} | %-10s | %-13s | %-8s | ${COLOR_INFO}%-10s${COLOR_RESET}\n" \
            "#$i" "$STATUS" "${TTFT}ms" "${TOTAL}ms" "$TOKENS" "$TPS"
    else
        echo "$i,FAILED,0,0,0,0" >> "$OUTPUT_FILE"
        printf "%-6s | ${COLOR_FAIL}%-8s${COLOR_RESET} | %-10s | %-13s | %-8s | %-10s\n" \
            "#$i" "FAILED" "0.00ms" "0.00ms" "0" "0.00"
    fi
    sleep 2
done

echo -e "${COLOR_BOLD}=====================================================================${COLOR_RESET}"
echo -e "${COLOR_SUCCESS}Profiling cycle complete. Extracted data saved to target file.${COLOR_RESET}"
echo -e "${COLOR_BOLD}=====================================================================${COLOR_RESET}\n"