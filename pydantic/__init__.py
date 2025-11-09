"""A very small subset of Pydantic used for tests in this project."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Sequence, Tuple, Type, TypeVar


class ValidationError(ValueError):
    """Raised when validation fails."""


T = TypeVar("T", bound="BaseModel")


class FieldInfo:
    def __init__(self, default: Any = None, default_factory=None, **_: Any) -> None:
        self.default = default
        self.default_factory = default_factory


def Field(default: Any = None, *, default_factory=None, **kwargs: Any) -> FieldInfo:  # noqa: D401
    return FieldInfo(default=default, default_factory=default_factory, **kwargs)


class BaseModel:
    model_config: Dict[str, Any] = {}

    def __init__(self, **data: Any) -> None:
        for name, value in data.items():
            setattr(self, name, value)

    @classmethod
    def _default_for_field(cls, name: str) -> Any:
        default = getattr(cls, name, None)
        if isinstance(default, FieldInfo):
            if default.default_factory is not None:
                return default.default_factory()
            return deepcopy(default.default)
        return deepcopy(default)

    @classmethod
    def _coerce_field(cls, typ: Any, value: Any) -> Any:
        if value is None:
            return None
        origin = getattr(typ, "__origin__", None)
        args = getattr(typ, "__args__", ())
        if origin in (list, List):
            item_type = args[0] if args else Any
            result = []
            for item in value:
                if isinstance(item_type, type) and issubclass(item_type, BaseModel):
                    result.append(item_type.model_validate(item))
                else:
                    result.append(item)
            return result
        if origin in (dict, Dict):
            return dict(value)
        if origin in (tuple, Tuple) and args:
            return tuple(value)
        if origin is not None and getattr(origin, "__module__", "") == "typing" and args:
            # Handle Optional[...] and similar unions by taking the first non-None type.
            non_none = [arg for arg in args if arg is not type(None)]
            if non_none:
                return cls._coerce_field(non_none[0], value)
        if isinstance(typ, type) and issubclass(typ, BaseModel):
            return typ.model_validate(value)
        return value

    @classmethod
    def model_validate(cls: Type[T], data: Dict[str, Any]) -> T:
        if not isinstance(data, dict):
            raise ValidationError(f"Expected dict for {cls.__name__}")
        values: Dict[str, Any] = {}
        annotations = getattr(cls, "__annotations__", {})
        for name, typ in annotations.items():
            if name in data:
                raw = data[name]
            else:
                raw = cls._default_for_field(name)
            values[name] = cls._coerce_field(typ, raw)
        return cls(**values)

    def model_dump(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        annotations = getattr(self.__class__, "__annotations__", {})
        for name in annotations:
            value = getattr(self, name, None)
            if isinstance(value, BaseModel):
                result[name] = value.model_dump()
            elif isinstance(value, list):
                result[name] = [item.model_dump() if isinstance(item, BaseModel) else item for item in value]
            else:
                result[name] = value
        return result


__all__ = ["BaseModel", "Field", "ValidationError"]
