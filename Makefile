.PHONY: all build-images push-images deploy-workload run-evaluation clean-all

REGISTRY_NAME ?= docker.io/sakkshm
TARGET_NAMESPACE ?= edge-apps
NODE_IP ?= 10.63.49.91
DEPLOYMENT_NAME ?= edge-llm

# The default target running the entire pipeline end-to-end
all: deploy-workload run-evaluation

build-images:
	@echo "Building application containers from local sources..."
	docker build -t $(REGISTRY_NAME)/kubeedge-llm:v1 ./src/engine
	docker build -t $(REGISTRY_NAME)/kubeedge-llm-sidecar:v1 ./src/sidecar

push-images: build-images
	@echo "Pushing container images to online registry $(REGISTRY_NAME)..."
	docker push $(REGISTRY_NAME)/kubeedge-llm:v1
	docker push $(REGISTRY_NAME)/kubeedge-llm-sidecar:v1

deploy-workload:
	@echo "Ensuring target namespace '$(TARGET_NAMESPACE)' exists..."
	kubectl create namespace $(TARGET_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	@echo "Applying system governance and network exposure guardrails..."
	kubectl apply -f deployments/system/resource-guardrails.yaml -n $(TARGET_NAMESPACE)
	kubectl apply -f deployments/system/service-exposure-edge.yaml -n $(TARGET_NAMESPACE)
	@echo "Applying application orchestration manifests to the cluster control plane..."
	kubectl apply -f deployments/apps/edge-deployment.yaml -n $(TARGET_NAMESPACE)

run-evaluation:
	@echo "Waiting for edge node sidecar to complete cold-start pre-warming..."
	kubectl rollout status deployment/$(DEPLOYMENT_NAME) -n $(TARGET_NAMESPACE) --timeout=5m
	@echo "Executing automated performance metrics collection suite..."
	bash benchmarks/run_benchmarks.sh $(NODE_IP)

clean-all:
	@echo "Tearing down remote edge workloads and system boundaries from '$(TARGET_NAMESPACE)'..."
	kubectl delete -f deployments/apps/edge-deployment.yaml -n $(TARGET_NAMESPACE) --ignore-not-found=true
	kubectl delete -f deployments/system/service-exposure-edge.yaml -n $(TARGET_NAMESPACE) --ignore-not-found=true
	kubectl delete -f deployments/system/resource-guardrails.yaml -n $(TARGET_NAMESPACE) --ignore-not-found=true
	@echo "Removing metrics logs..."
	rm -f benchmarks/reports/results.csv