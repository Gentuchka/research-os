"""JSON Schema validation at API boundaries."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from research_os.config import SCHEMAS_DIR
from research_os.kernel.types import InvariantCode, KernelError


@lru_cache(maxsize=32)
def _load_schema(name: str) -> dict[str, Any]:
    path = SCHEMAS_DIR / name
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_instance(schema_name: str, instance: dict[str, Any]) -> None:
    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    if errors:
        messages = "; ".join(e.message for e in errors[:5])
        raise KernelError(
            InvariantCode.INVALID_OPERATION,
            f"Schema validation failed for {schema_name}: {messages}",
        )
