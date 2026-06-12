"""Storage API that module authors use to persist configuration.

A module never touches the database directly. It calls get_module_config /
save_module_config with its own id and gets back / stores a plain dict. The
core serialises it as JSON in the ModuleConfig table. This is the only contract
a module needs for persistence, which keeps modules portable.
"""
import json

from .models import ModuleConfig, db


def get_module_config(module_id: str, default: dict | None = None) -> dict:
    row = db.session.get(ModuleConfig, module_id)
    if row is None:
        return dict(default) if default else {}
    try:
        return json.loads(row.data)
    except (ValueError, TypeError):
        return dict(default) if default else {}


def save_module_config(module_id: str, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    row = db.session.get(ModuleConfig, module_id)
    if row is None:
        row = ModuleConfig(module_id=module_id, data=payload)
        db.session.add(row)
    else:
        row.data = payload
    db.session.commit()


def delete_module_config(module_id: str) -> None:
    row = db.session.get(ModuleConfig, module_id)
    if row is not None:
        db.session.delete(row)
        db.session.commit()
