from __future__ import annotations

from backend.manager.download import Item, Plan, part_of, replacing_of
from backend.manager.registry import Model, Registry
from backend.manager.storage import Storage


def model_bundle(model_id: str, registry: Registry) -> tuple[Model, ...]:
    model = registry.models[model_id]
    return (*(registry.models[need] for need in model.needs), model)


def model_plan(model_id: str, registry: Registry, storage: Storage) -> Plan:
    items = tuple(
        Item(m.url, storage.model_file(m), m.sha256, m.size_bytes)
        for m in model_bundle(model_id, registry)
    )
    return Plan(model_id, items, shared=items[:-1])


def delete_model(model_id: str, registry: Registry, storage: Storage) -> None:
    path = storage.model_file(registry.models[model_id])
    path.unlink(missing_ok=True)
    part_of(path).unlink(missing_ok=True)
    replacing_of(path).unlink(missing_ok=True)
    part_of(replacing_of(path)).unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass
