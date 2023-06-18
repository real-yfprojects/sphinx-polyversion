from __future__ import annotations

import json
import warnings
from datetime import datetime
from inspect import getmodule
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Protocol,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
    runtime_checkable,
)

__all__ = ["Transformable", "Encoder", "Decoder"]


#: Python types representing a JSON object
JSON_TYPE_KEY = Union[None, bool, int, float, str]
JSON_TYPE = Union[
    JSON_TYPE_KEY,
    List["JSON_TYPE"],
    Tuple["JSON_TYPE", ...],
    Dict[str, "JSON_TYPE"],
]

JSON_TYPE_DUMP = Union[
    JSON_TYPE_KEY,
    List["JSON_TYPE_DUMP"],
    Tuple["JSON_TYPE_DUMP", ...],
    Dict[JSON_TYPE_KEY, "JSON_TYPE_DUMP"],
]


class RecursionWarning(UserWarning):
    pass


class Transformable(Protocol):
    def _json_fields(self) -> JSONable:
        ...

    @classmethod
    def _from_json_fields(cls: Type[T], o: JSON_TYPE) -> T:
        pass


#: Python types that this module can encode
JSONable = Union[
    JSON_TYPE_KEY,
    List["JSONable"],
    Tuple["JSONable", ...],
    Dict[JSON_TYPE_KEY, "JSONable"],
    Transformable,
]


class Encoder(json.JSONEncoder):
    @overload
    def __init__(self, hook: JSONHook, /, **kwargs: Any) -> None:
        ...

    @overload
    def __init__(self, hooks: Iterable[JSONHook] = [], /, **kwargs: Any) -> None:
        ...

    def __init__(
        self, hooks: Iterable[JSONHook] | JSONHook = [], /, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.hooks = [hooks] if isinstance(hooks, JSONHook) else hooks

    @staticmethod
    def determine_classname(o: object | type, instance: bool = True) -> str:
        module = getmodule(o)
        mod_name = module.__name__ if module else ""
        c = type(o) if instance else cast(type, o)
        cls_name = c.__qualname__
        return f"{mod_name}.{cls_name}"

    def transform(self, o: JSONable) -> JSON_TYPE_DUMP:
        for hook in self.hooks:
            if (fields := hook.fields(o)) is not None:
                return {
                    "__jsonhook__": (
                        self.determine_classname(hook, instance=False),
                        self.determine_classname(o),
                        self.transform(fields),
                    )
                }

        if hasattr(o, "_json_fields"):
            # type JSONable
            fields = o._json_fields()  # type: ignore
            if t := type(o) == type(fields):
                warnings.warn(
                    f"Class {t} returns itself as json field container",
                    RecursionWarning,
                )
            return {
                "__jsonclass__": (
                    self.determine_classname(o),
                    self.transform(fields),
                )
            }

        if isinstance(o, dict):
            return {k: self.transform(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [self.transform(v) for v in o]

        # do not use cast for performance reasons
        return o

    def __call__(self, o: JSONable) -> JSON_TYPE_DUMP:
        return self.transform(o)

    def iterencode(self, o: JSONable, _one_shot: bool = False) -> Iterator[str]:
        """Encode an object."""
        # called for every top level object to encode
        return super().iterencode(self.transform(o), _one_shot)


T = TypeVar("T", bound=Transformable)


class Decoder(json.JSONDecoder):
    def __init__(
        self,
        decoder: Decoder | None = None,
        *,
        parse_float: Callable[[str], Any] | None = None,
        parse_int: Callable[[str], Any] | None = None,
        parse_constant: Callable[[str], Any] | None = None,
        strict: bool = True,
    ) -> None:
        if decoder:
            parse_float = parse_float or decoder.parse_float
            parse_int = parse_int or decoder.parse_int
            parse_constant = parse_constant or decoder.parse_constant
            strict = strict or decoder.strict
        super().__init__(
            parse_float=parse_float,
            parse_int=parse_int,
            parse_constant=parse_constant,
            strict=strict,
            object_hook=self.object_hook,
        )
        self.type_dict: Dict[str, Type[Transformable]] = {}
        self.type_hooks: Dict[str, Type[JSONHook]] = {}
        if decoder:
            self.register_from(decoder)

    @property
    def registered_types(self) -> List[type]:
        return list(self.type_dict.values())

    @property
    def hooks(self) -> List[JSONHook]:
        return list(self.type_hooks.values())

    @staticmethod
    def determine_classname(t: type) -> str:
        mod_name = getmodule(t).__name__  # type: ignore
        cls_name = t.__qualname__
        return f"{mod_name}.{cls_name}"

    def register_from(self, decoder: Decoder) -> None:
        self.register(*self.registered_types)

    @overload
    def register(self, t: Type[T], /) -> Type[T]:
        ...

    @overload
    def register(self, t1: Type[T], t2: Type[T], /, *types: Type[T]) -> None:
        ...

    @overload
    def register(self, hook: Type[JSONHook], /) -> Type[JSONHook]:
        ...

    def register(
        self, *ts: Type[JSONHook] | Type[T]
    ) -> Type[T] | Type[JSONHook] | None:
        for t in ts:
            key = self.determine_classname(t)
            if isinstance(t, JSONHook):
                # register hook
                if key in self.type_hooks:
                    raise ValueError(f"Hook {key} already registered")
                self.type_hooks[key] = t
            else:
                # register Transformable class
                if not hasattr(t, "_from_json_fields"):
                    raise TypeError(
                        "Registered Type must implement `_from_json_fields`"
                    )
                if key in self.type_dict:
                    raise ValueError(f"Class {key} already registered")
                self.type_dict[key] = t

        return ts[0] if len(ts) == 1 else None

    def object_hook(self, o: Dict[str, JSON_TYPE]) -> Any:
        """Alter objects after deserialization."""
        classname: str
        fields: JSON_TYPE
        if "__jsonclass__" in o:
            # deserializable object
            classname, fields = o["__jsonclass__"]  # type: ignore

            if classname in self.type_dict:
                return self.type_dict[classname]._from_json_fields(fields)
        elif "__jsonhook__" in o:
            # object that can be deserialized through a hook
            hookname: str
            hookname, classname, fields = o["__jsonhook__"]  # type: ignore
            if hookname in self.type_hooks:
                return self.type_hooks[hookname].from_json(classname, fields)
        return o


GLOBAL_DECODER = Decoder()


@runtime_checkable
class JSONHook(Protocol):
    @staticmethod
    def fields(o: Any) -> None | Any:
        ...

    @staticmethod
    def from_json(cls: str, o: JSON_TYPE) -> Any:
        ...


@GLOBAL_DECODER.register
class std_hook(JSONHook):
    @staticmethod
    def fields(o: Any) -> str | None:
        if isinstance(o, datetime):
            return o.isoformat()
        return None

    @staticmethod
    def from_json(cls: str, o: JSON_TYPE) -> Any:
        o = cast(str, o)
        return datetime.fromisoformat(o)
