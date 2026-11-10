# Linkin 內網骨架

階段 0 的清單。映像 `linkin/scaffold/<name>:0.0.0` 尚未發布，套用後不會拉起可用行程。

預設 12 個服務加 `frontend`。團隊小於 5 人時，把 `context-service` 併進 `route-service`、`reflection-service` 併進 `company-orchestrator`，功能清單仍按模組保留。

```bash
kubectl apply -k deploy/k8s/linkin
```

`istio-mtls.yaml` 與 `keda-seat-executor.yaml` 需要對應 CRD，預設 kustomization 不含它們。裝了 Istio 或 KEDA 再單獨套用。

內網 Ingress 只進 `api-gateway`。`seat-executor` 只出站到 `tool-gateway` 與 NATS。OPC 寫入埠 8081 只接受 `guardrail-service`。服務間 mTLS 用 Istio STRICT。

契約見 [服務契約](../../../docs/architecture/service-contracts.md)。
