# Kubernetes setup (Kind)

Kind is used instead of Minikube because Minikube's Docker driver is **not supported on Windows** (`DRV_UNSUPPORTED_OS`). Kind runs the control plane as a Docker container and behaves identically for this workload.

## 1. Cluster

```powershell
kind create cluster --config kubernetes/kind-config.yaml
kubectl cluster-info --context kind-gitops-platform
kubectl get nodes
```

The config creates one control-plane node labelled `ingress-ready=true` and maps host ports **18080 → 80** and **18443 → 443**. Non-default ports avoid collisions with other local stacks (8080/8443 were already taken on the development machine).

Verify Kind is reachable from the host:

```powershell
kubectl get ns
```

## 2. Namespaces

```powershell
kubectl apply -f kubernetes/namespaces/namespaces.yaml
kubectl get ns platform monitoring logging argocd security platform-prod
```

`platform` and `platform-prod` enforce **restricted** Pod Security Standards; `monitoring`, `logging`, `argocd` and `security` enforce baseline.

## 3. Ingress controller and metrics server

```powershell
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.0/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=available deployment/ingress-nginx-controller --timeout=300s

kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json `
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl -n kube-system rollout status deployment/metrics-server --timeout=180s
```

`--kubelet-insecure-tls` is required because Kind kubelets use self-signed certificates. HPA cannot compute utilisation without metrics-server.

## 4. Images

```powershell
docker compose build
foreach ($img in @('api-gateway','user-service','product-service','order-service',
                   'notification-service','frontend','platform-api')) {
  kind load docker-image "platform/$img:1.0.0" --name gitops-platform
}
kind get nodes | ForEach-Object { docker exec $_ crictl images | Select-String "platform/" }
```

All manifests use `imagePullPolicy: IfNotPresent`, so loaded images are used without a registry.

## 5. Secrets

```powershell
./scripts/create-dev-secrets.ps1
kubectl -n platform get secret platform-secrets -o jsonpath='{.data}' | Out-String
```

Random values are generated in memory and passed to `kubectl create secret`; nothing is written to disk or Git. `kubernetes/core/secret.example.yaml` documents the shape only.

Also create the Grafana admin secret if you want a non-default password:

```powershell
kubectl -n monitoring create secret generic grafana-admin --from-literal=admin-password=<strong-password>
```

## 6. Deploy the application

```powershell
kubectl apply -k kubernetes/overlays/development
kubectl -n platform rollout status deployment/api-gateway --timeout=180s
kubectl -n platform get deploy,pods,svc,hpa,pdb
```

What the overlay contains: 7 Deployments + Services, PostgreSQL StatefulSet with a 1 Gi PVC, ConfigMap, Ingress, 7 PDBs, 3 HPAs, ResourceQuota, LimitRange, 11 NetworkPolicies, RBAC.

## 7. Verify from outside the cluster

```powershell
curl http://localhost:18080/                        # frontend HTML
curl http://localhost:18080/platform/api/health     # platform API + cluster connection
curl http://localhost:18080/gateway/api/health      # dependency health
```

The platform API health response includes `cluster.connected: true` and `data_source: "cluster"` when in-cluster RBAC is working.

## 8. Add monitoring and logging

```powershell
kubectl apply -k monitoring
kubectl apply -k logging
kubectl -n monitoring get pods
kubectl -n logging get pods
```

Dashboards: `kubectl -n monitoring port-forward svc/grafana 3000:3000` → http://localhost:3000.

## 9. Autoscaling

```powershell
kubectl -n platform get hpa
kubectl -n platform top pods
kubectl -n platform describe hpa api-gateway
```

If `TARGETS` shows `<unknown>`, metrics-server is not ready or the container has no CPU **request** (HPA percentages are relative to requests).

## 10. Failure drills

```powershell
# Crash loop
kubectl -n platform set env deployment/notification-service NOTIFICATION_FAILURE_RATE=1
kubectl -n platform rollout status deployment/notification-service
kubectl -n platform logs deployment/notification-service --previous | Select-Object -Last 20
kubectl -n platform set env deployment/notification-service NOTIFICATION_FAILURE_RATE=0

# Drift detection (Argo CD self-heal reverts it)
kubectl -n platform scale deployment/api-gateway --replicas=3
kubectl -n argocd get application api-gateway -w

# Rollback
kubectl -n platform rollout undo deployment/api-gateway
kubectl -n platform rollout history deployment/api-gateway
```

## 11. Teardown

```powershell
kind delete cluster --name gitops-platform
docker compose --profile observability down -v
```

## Minikube alternative (Linux/macOS)

```bash
minikube start --driver=docker --cpus=4 --memory=6g --addons=ingress,metrics-server
kubectl config use-context minikube
# load images instead of kind load:
minikube image load platform/api-gateway:1.0.0
```

On Windows use the Hyper-V or VirtualBox driver, or stay on Kind. Adjust ingress host ports accordingly — Minikube's ingress addon binds `127.0.0.1:80/443` through `minikube tunnel`.
