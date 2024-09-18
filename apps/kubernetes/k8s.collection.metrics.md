# Metrics Useful For Monitoring Or Sizing Kubernetes Collection
Sumologic Kubernetes Collection app includes a 'Healthcheck' dashboard to help diagnose current state.

The otel agent exports it's own metrics that can be used for monitoring see: https://opentelemetry.io/docs/collector/internal-telemetry/#use-internal-telemetry-to-monitor-the-collector

If you are only sending logs to sumologic not metrics you will need to use the metrics below in another tool (eg. grafana or similar) to ensure you have correct data to size/ monitor the collectoin infrastructure pipoline.

Sumo k8s collection pipeline needs to be sized for scaling correctly to handle possible load spikes seeL
- https://help.sumologic.com/docs/send-data/kubernetes/best-practices/#opentelemetry-collector-autoscaling
- https://help.sumologic.com/docs/send-data/kubernetes/best-practices/#opentelemetry-collector-queueing-and-batching
  

There are two otel container sets in the architecure:
- level 1 - on each node gets logs (and metrics) from local pods and k8s
- level 2 - stateful set in cluster to do metadata enrichment and forwarding to sumo
- some metrics also require extra containers like prometheus operator/kube-state-metrics 
  
## Level 1 - daemonset metrics (otel pods collect logs from each node)
```
daemonset = *sumologic-otelcol-logs-collector _contentType = \"Prometheus\" metric = up 
daemonset = *sumologic-otelcol-logs-collector metric = container_cpu_usage_seconds_total 
daemonset = *sumologic-otelcol-logs-collector metric = container_memory_working_set_bytes 
```

## Level 2 - otelcol stateful set metrics (otel pods that enrich with metadata and post to sumologic)
```
statefulset = *sumologic-otelcol-logs* metric = container_cpu_cfs_throttled_seconds_total 
statefulset = *sumologic-otelcol-logs* metric = container_cpu_usage_seconds_total 
statefulset = *sumologic-otelcol-logs* metric = container_memory_working_set_bytes 
statefulset = *sumologic-otelcol-logs* metric = kube_statefulset_status_replicas 
statefulset = *sumologic-otelcol-logs* metric = otelcol_exporter_queue_size 
statefulset = *sumologic-otelcol-metrics* metric = container_cpu_cfs_throttled_seconds_total 
statefulset = *sumologic-otelcol-metrics* metric = container_cpu_usage_seconds_total 
statefulset = *sumologic-otelcol-metrics* metric = container_memory_working_set_bytes 
statefulset = *sumologic-otelcol-metrics* metric = kube_statefulset_status_replicas 
statefulset = *sumologic-otelcol-metrics* metric = otelcol_exporter_queue_size 
```

## metrics from otel about itself
```
metric = otelcol_exporter_queue_size 
metric = otelcol_otelsvc_k8s_pod_added 
metric = otelcol_otelsvc_k8s_pod_deleted 
metric = otelcol_process_memory_rss 
metric = otelcol_process_memory_rss 
metric = otelcol_process_cpu_seconds 
```

## prometheus related metrics for prometheus pods (operator etc)
```
metric = prometheus_remote_storage_failed_samples_total 
metric = prometheus_remote_storage_pending_samples 
metric = prometheus_remote_storage_succeeded_samples_total 
metric = prometheus_remote_storage_succeeded_samples_total 
```

## up metrics for related pods
```
metric = up job = *prom*
metric = up job = *dns* 
metric = up job = apiserver 
metric = up job = kube-state-metrics 
metric = up job = kubelet 
metric = up job = node-exporter 
```

