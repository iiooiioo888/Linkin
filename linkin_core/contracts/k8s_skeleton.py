"""內網 K8s 骨架。映像是佔位，階段 0 不發布。"""

from __future__ import annotations

import json
from typing import Any

from linkin_core.contracts.topology import (
    ALLOW,
    DEFAULT_SERVICES,
    DNS_PORTS,
    FRONTEND_SERVICE,
    OTLP_PORT,
)

NAMESPACE = "linkin"
HTTP_PORT = 8080
APPS = (*DEFAULT_SERVICES, FRONTEND_SERVICE)
DATA_STORES = ("postgres", "redis", "chroma", "nats")
IMAGE = "linkin/scaffold/{name}:0.0.0"


def _quote(value: str) -> str:
    special = set(":#{}[],&*!|>%@`'\n\t")
    if (
        value == ""
        or value.lower() in {"true", "false", "null", "yes", "no"}
        or value[0] in "-?&*!|>%@`'\"0123456789"
        or any(ch in special for ch in value)
        or value != value.strip()
    ):
        return json.dumps(value, ensure_ascii=False)
    return value


def _dump(obj: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, str):
        return _quote(obj)
    if isinstance(obj, list):
        if not obj:
            return "[]"
        lines = []
        for item in obj:
            rendered = _dump(item, indent + 1)
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}- {rendered.lstrip()}")
            else:
                lines.append(f"{pad}- {rendered}")
        return "\n".join(lines)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        lines = []
        for key, value in obj.items():
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{pad}{key}:")
                lines.append(_dump(value, indent + 1))
            else:
                lines.append(f"{pad}{key}: {_dump(value, indent + 1)}")
        return "\n".join(lines)
    raise TypeError(type(obj))


def dump_docs(docs: list[dict[str, Any]]) -> str:
    chunks = [f"---\n{_dump(doc)}" for doc in docs]
    return "\n".join(chunks).rstrip() + "\n"


def _labels(name: str) -> dict[str, str]:
    return {
        "app.kubernetes.io/name": name,
        "app.kubernetes.io/part-of": "linkin",
    }


def _meta(name: str) -> dict[str, Any]:
    return {"name": name, "namespace": NAMESPACE, "labels": _labels(name)}


def _http_probe(path: str) -> dict[str, Any]:
    return {"httpGet": {"path": path, "port": "http"}, "initialDelaySeconds": 5}


def _container(name: str, ports: list[dict[str, Any]]) -> dict[str, Any]:
    container: dict[str, Any] = {
        "name": name,
        "image": IMAGE.format(name=name),
        "imagePullPolicy": "IfNotPresent",
        "ports": ports,
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
        },
    }
    if any(item["name"] == "http" for item in ports):
        container["livenessProbe"] = _http_probe("/healthz")
        container["readinessProbe"] = _http_probe("/readyz")
    else:
        container["livenessProbe"] = {"tcpSocket": {"port": ports[0]["name"]}}
        container["readinessProbe"] = {"tcpSocket": {"port": ports[0]["name"]}}
    return container


def _pod(name: str, ports: list[dict[str, Any]], signal: str) -> dict[str, Any]:
    return {
        "metadata": {
            "labels": {
                **_labels(name),
                "linkin.io/mtls": "required",
                "linkin.io/scale-signal": signal,
            }
        },
        "spec": {
            "automountServiceAccountToken": False,
            "securityContext": {"runAsNonRoot": True, "runAsUser": 65532},
            "containers": [_container(name, ports)],
        },
    }


def _deploy(name: str, ports: list[dict[str, Any]], signal: str) -> dict[str, Any]:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": _meta(name),
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": _labels(name)},
            "template": _pod(name, ports, signal),
        },
    }


def _service(name: str, ports: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": _meta(name),
        "spec": {
            "selector": _labels(name),
            "ports": [
                {"name": item["name"], "port": item["containerPort"], "targetPort": item["name"]}
                for item in ports
            ],
        },
    }


def _http_ports() -> list[dict[str, Any]]:
    return [{"name": "http", "containerPort": HTTP_PORT}]


def _opc_ports() -> list[dict[str, Any]]:
    return [
        {"name": "http", "containerPort": HTTP_PORT},
        {"name": "write", "containerPort": 8081},
    ]


def _otel_ports() -> list[dict[str, Any]]:
    return [
        {"name": "http", "containerPort": HTTP_PORT},
        {"name": "otlp", "containerPort": OTLP_PORT},
    ]


def app_workloads() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    signals = {
        "api-gateway": "qps",
        "route-service": "qps",
        "context-service": "latency",
        "reflection-service": "cpu",
        "company-orchestrator": "tasks",
        "seat-executor": "queue",
        "tool-gateway": "qps",
        "guardrail-service": "qps",
    }
    for name in APPS:
        if name == "opc-service":
            ports = _opc_ports()
        elif name == "observability-collector":
            ports = _otel_ports()
        else:
            ports = _http_ports()
        docs.append(_deploy(name, ports, signals.get(name, "qps")))
        docs.append(_service(name, ports))
    return docs


def data_stores() -> list[dict[str, Any]]:
    specs = {
        "postgres": [{"name": "db", "containerPort": 5432}],
        "redis": [{"name": "cache", "containerPort": 6379}],
        "chroma": [{"name": "http", "containerPort": 8000}],
        "nats": [
            {"name": "client", "containerPort": 4222},
            {"name": "monitor", "containerPort": 8222},
        ],
    }
    docs: list[dict[str, Any]] = []
    for name, ports in specs.items():
        if name == "chroma":
            docs.append(
                {
                    "apiVersion": "apps/v1",
                    "kind": "StatefulSet",
                    "metadata": _meta(name),
                    "spec": {
                        "serviceName": name,
                        "replicas": 1,
                        "selector": {"matchLabels": _labels(name)},
                        "template": _pod(name, ports, "disk"),
                        "volumeClaimTemplates": [
                            {
                                "metadata": {"name": "data"},
                                "spec": {
                                    "accessModes": ["ReadWriteOnce"],
                                    "resources": {"requests": {"storage": "10Gi"}},
                                },
                            }
                        ],
                    },
                }
            )
        else:
            docs.append(_deploy(name, ports, "disk"))
        docs.append(_service(name, ports))
    return docs


def namespace_doc() -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": NAMESPACE,
            "labels": {
                "app.kubernetes.io/part-of": "linkin",
                "linkin.io/exposure": "intranet",
            },
        },
    }


def configmap_doc() -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": _meta("linkin-contract"),
        "data": {
            "LINKIN_EXPOSURE": "intranet",
            "LINKIN_SCHEMA_VERSION": "1.0.0",
            "LINKIN_MAX_SYNC_HOPS": "3",
            "ROUTE_PREVIEW_P95_MS": "300",
        },
    }


def ingress_doc() -> dict[str, Any]:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            **_meta("linkin-internal"),
            "annotations": {"linkin.io/exposure": "intranet"},
        },
        "spec": {
            "ingressClassName": "nginx-internal",
            "rules": [
                {
                    "host": "linkin.internal",
                    "http": {
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": "api-gateway",
                                        "port": {"number": HTTP_PORT},
                                    }
                                },
                            }
                        ]
                    },
                }
            ],
        },
    }


def _peer(name: str) -> dict[str, Any]:
    if name == "ingress-nginx":
        return {
            "namespaceSelector": {
                "matchLabels": {"kubernetes.io/metadata.name": "ingress-nginx"}
            }
        }
    return {"podSelector": {"matchLabels": _labels(name)}}


def network_policies() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = [
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": _meta("default-deny"),
            "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]},
        }
    ]
    ingress_by_dst: dict[str, list[tuple[str, int]]] = {}
    egress_by_src: dict[str, list[tuple[str, int]]] = {}
    for src, dst, port in ALLOW:
        ingress_by_dst.setdefault(dst, []).append((src, port))
        if src != "ingress-nginx":
            egress_by_src.setdefault(src, []).append((dst, port))
    for name in (*APPS, *DATA_STORES):
        egress_by_src.setdefault(name, []).append(("observability-collector", OTLP_PORT))
        ingress_by_dst.setdefault("observability-collector", []).append((name, OTLP_PORT))
    for dst, peers in sorted(ingress_by_dst.items()):
        docs.append(
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": _meta(f"allow-in-{dst}"),
                "spec": {
                    "podSelector": {"matchLabels": _labels(dst)},
                    "policyTypes": ["Ingress"],
                    "ingress": [
                        {"from": [_peer(src)], "ports": [{"protocol": "TCP", "port": port}]}
                        for src, port in peers
                    ],
                },
            }
        )
    dns = [
        {"protocol": "UDP", "port": DNS_PORTS[0]},
        {"protocol": "TCP", "port": DNS_PORTS[0]},
    ]
    for src, peers in sorted(egress_by_src.items()):
        rules = [
            {
                "to": [
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                        }
                    }
                ],
                "ports": dns,
            }
        ]
        rules.extend(
            {"to": [_peer(dst)], "ports": [{"protocol": "TCP", "port": port}]}
            for dst, port in peers
        )
        docs.append(
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": _meta(f"allow-out-{src}"),
                "spec": {
                    "podSelector": {"matchLabels": _labels(src)},
                    "policyTypes": ["Egress"],
                    "egress": rules,
                },
            }
        )
    return docs


def hpa_docs() -> list[dict[str, Any]]:
    hpa_targets = (
        "api-gateway",
        "route-service",
        "context-service",
        "reflection-service",
        "company-orchestrator",
        "tool-gateway",
        "guardrail-service",
    )
    docs: list[dict[str, Any]] = []
    for name in hpa_targets:
        docs.append(
            {
                "apiVersion": "autoscaling/v2",
                "kind": "HorizontalPodAutoscaler",
                "metadata": _meta(name),
                "spec": {
                    "scaleTargetRef": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "name": name,
                    },
                    "minReplicas": 1,
                    "maxReplicas": 4,
                    "metrics": [
                        {
                            "type": "Resource",
                            "resource": {
                                "name": "cpu",
                                "target": {"type": "Utilization", "averageUtilization": 70},
                            },
                        }
                    ],
                },
            }
        )
    return docs


def keda_docs() -> list[dict[str, Any]]:
    return [
        {
            "apiVersion": "keda.sh/v1alpha1",
            "kind": "ScaledObject",
            "metadata": _meta("seat-executor"),
            "spec": {
                "scaleTargetRef": {"name": "seat-executor"},
                "minReplicaCount": 1,
                "maxReplicaCount": 8,
                "triggers": [
                    {
                        "type": "nats-jetstream",
                        "metadata": {
                            "natsServerMonitoringEndpoint": "nats.linkin.svc.cluster.local:8222",
                            "account": "$G",
                            "stream": "linkin",
                            "consumer": "seat-executor",
                            "lagThreshold": "10",
                        },
                    }
                ],
            },
        }
    ]


def istio_mtls() -> list[dict[str, Any]]:
    return [
        {
            "apiVersion": "security.istio.io/v1",
            "kind": "PeerAuthentication",
            "metadata": _meta("linkin-strict"),
            "spec": {"mtls": {"mode": "STRICT"}},
        },
        {
            "apiVersion": "networking.istio.io/v1",
            "kind": "DestinationRule",
            "metadata": _meta("linkin-mtls"),
            "spec": {
                "host": "*.linkin.svc.cluster.local",
                "trafficPolicy": {"tls": {"mode": "ISTIO_MUTUAL"}},
            },
        },
    ]


def render_files() -> dict[str, str]:
    return {
        "namespace.yaml": dump_docs([namespace_doc()]),
        "configmap.yaml": dump_docs([configmap_doc()]),
        "workloads.yaml": dump_docs(app_workloads()),
        "data-stores.yaml": dump_docs(data_stores()),
        "ingress.yaml": dump_docs([ingress_doc()]),
        "networkpolicies.yaml": dump_docs(network_policies()),
        "hpa.yaml": dump_docs(hpa_docs()),
        "keda-seat-executor.yaml": dump_docs(keda_docs()),
        "istio-mtls.yaml": dump_docs(istio_mtls()),
    }
