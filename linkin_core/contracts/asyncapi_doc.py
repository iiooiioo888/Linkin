"""AsyncAPI 2.6 草案。事件帶 schema_version、trace_id、tenant_id。"""

from __future__ import annotations

from typing import Any

from linkin_core.contracts.events import EVENT_MODELS, EventName
from linkin_core.contracts.version import CONTRACT_VERSION


def _schemas() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for model in EVENT_MODELS.values():
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        defs = schema.pop("$defs", {})
        out[model.__name__] = schema
        out.update(defs)
    return out


def build_asyncapi() -> dict[str, Any]:
    channels: dict[str, Any] = {}
    for name, model in EVENT_MODELS.items():
        channels[name.value] = {
            "subscribe": {
                "operationId": name.name,
                "message": {
                    "name": model.__name__,
                    "payload": {"$ref": f"#/components/schemas/{model.__name__}"},
                },
            }
        }
    task_stream = "tasks/{task_id}/stream"
    channels[task_stream] = {
        "parameters": {"task_id": {"schema": {"type": "string"}}},
        "subscribe": {
            "operationId": "watchTask",
            "message": {
                "name": "TaskStream",
                "payload": {
                    "type": "object",
                    "required": ["schema_version", "trace_id", "tenant_id", "event"],
                    "properties": {
                        "schema_version": {"type": "string"},
                        "trace_id": {"type": "string"},
                        "tenant_id": {"type": "string"},
                        "event": {"type": "string"},
                    },
                },
            },
        },
    }
    return {
        "asyncapi": "2.6.0",
        "info": {
            "title": "Linkin 事件契約",
            "version": CONTRACT_VERSION,
            "description": "NATS JetStream。頻道名即事件名。",
        },
        "defaultContentType": "application/json",
        "servers": {
            "nats": {
                "url": "nats.linkin.svc.cluster.local:4222",
                "protocol": "nats",
            }
        },
        "channels": channels,
        "components": {"schemas": _schemas()},
    }


def event_names() -> list[str]:
    return [item.value for item in EventName]
