"""Lightweight compatibility shim implementing a tiny subset of Pydantic."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar, Union, get_args, get_origin, get_type_hints


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, errors: List[Dict[str, Any]]):
        super().__init__("Validation error")
        self._errors = errors

    def errors(self) -> List[Dict[str, Any]]:  # pragma: no cover - simple proxy
        return self._errors


@dataclass
class FieldInfo:
    default: Any = ...
    alias: Optional[str] = None


def Field(default: Any = ..., *, alias: Optional[str] = None) -> Any:
    return FieldInfo(default=default, alias=alias)


T = TypeVar("T", bound="BaseModel")


class BaseModelMeta(type):
    def __new__(mcls, name: str, bases: Tuple[type, ...], namespace: Dict[str, Any]):
        annotations = namespace.get("__annotations__", {})
        field_defaults: Dict[str, Any] = {}
        field_aliases: Dict[str, str] = {}
        for field_name in list(annotations.keys()):
            value = namespace.get(field_name, ...)
            if isinstance(value, FieldInfo):
                namespace.pop(field_name)
                if value.alias:
                    field_aliases[field_name] = value.alias
                if value.default is not ...:
                    field_defaults[field_name] = value.default
            elif value is not ...:
                field_defaults[field_name] = value
        cls = super().__new__(mcls, name, bases, namespace)
        cls.__field_defaults__ = field_defaults
        cls.__field_aliases__ = field_aliases
        return cls


class BaseModel(metaclass=BaseModelMeta):
    """Very small subset of the pydantic BaseModel API."""

    __field_defaults__: Dict[str, Any]
    __field_aliases__: Dict[str, str]

    def __init__(self, **data: Any) -> None:
        annotations = get_type_hints(self.__class__)
        base_fields = {"__field_defaults__", "__field_aliases__"}
        values: Dict[str, Any] = {}
        errors: List[Dict[str, Any]] = []
        for field, annotation in annotations.items():
            if field in base_fields:
                continue
            alias = self.__field_aliases__.get(field)
            if alias and alias in data:
                raw_value = data.pop(alias)
            elif field in data:
                raw_value = data.pop(field)
            elif field in self.__field_defaults__:
                default_value = self.__field_defaults__[field]
                if isinstance(default_value, list):
                    raw_value = list(default_value)
                elif isinstance(default_value, dict):
                    raw_value = dict(default_value)
                else:
                    raw_value = default_value
            else:
                errors.append({"loc": field, "msg": "field required"})
                continue
            try:
                value = self._convert(annotation, raw_value)
            except ValidationError as exc:  # pragma: no cover - unlikely nested error
                errors.extend(exc.errors())
                continue
            except Exception as exc:  # pragma: no cover - defensive
                errors.append({"loc": field, "msg": str(exc)})
                continue
            values[field] = value
        if errors:
            raise ValidationError(errors)
        for key, value in values.items():
            setattr(self, key, value)
        # accept extra keys without error

    @classmethod
    def parse_obj(cls: Type[T], obj: Any) -> T:
        if isinstance(obj, cls):
            return obj
        if not isinstance(obj, dict):
            raise ValidationError([{"loc": cls.__name__, "msg": "Input should be a dict"}])
        return cls(**obj)

    def dict(self, *, by_alias: bool = False) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for field in self.__annotations__:
            value = getattr(self, field)
            key = self.__field_aliases__.get(field, field) if by_alias else field
            if isinstance(value, BaseModel):
                result[key] = value.dict(by_alias=by_alias)
            elif isinstance(value, list):
                result[key] = [self._serialize(item, by_alias) for item in value]
            else:
                result[key] = value
        return result

    @staticmethod
    def _serialize(value: Any, by_alias: bool) -> Any:
        if isinstance(value, BaseModel):
            return value.dict(by_alias=by_alias)
        return value

    @classmethod
    def _convert(cls, annotation: Any, value: Any) -> Any:
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin in (list, List):
            inner = args[0] if args else Any
            return [cls._convert(inner, item) for item in value or []]
        if origin in (dict, Dict):
            return dict(value)
        if origin is Union:
            for inner in args:
                if inner is type(None) and value is None:
                    return None
                try:
                    return cls._convert(inner, value)
                except Exception:
                    continue
            return value
        if origin is tuple:
            return tuple(value)
        if origin is None and str(annotation).startswith('typing.Literal'):
            return value
        if origin is type(None):  # pragma: no cover - guard
            return None
        if hasattr(annotation, "parse_obj") and isinstance(value, dict):
            return annotation.parse_obj(value)
        if origin is None and isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation.parse_obj(value)
        if origin is None and annotation in (int, float, str, bool):
            return annotation(value)
        return value


__all__ = ["BaseModel", "Field", "ValidationError"]
