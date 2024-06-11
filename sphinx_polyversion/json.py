"""(De-)Serialize python objects to/from json."""

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

__all__ = ["Encoder", "Decoder", "RecursionWarning", "std_hook"]


#: Python types representing a key in JSON mapping
JSON_TYPE_KEY = Union[None, bool, int, float, str]

#: Python types representing a JSON object (as returned by json.load)
JSON_TYPE = Union[
    JSON_TYPE_KEY,
    List["JSON_TYPE"],
    Tuple["JSON_TYPE", ...],
    Dict[str, "JSON_TYPE"],
]

#: Python types supported by the build-in json module (json.dump)
JSON_TYPE_DUMP = Union[
    JSON_TYPE_KEY,
    List["JSON_TYPE_DUMP"],
    Tuple["JSON_TYPE_DUMP", ...],
    Dict[JSON_TYPE_KEY, "JSON_TYPE_DUMP"],
]


class RecursionWarning(UserWarning):
    """
    A transformable object returns its own type.

    This usually results in an infinite recursion since
    `_json_fields` is called over and over.
    """


class Transformable(Protocol):
    """Protocol for classes whose instances can be converted from and to json."""

    def _json_fields(self) -> JSONable:
        """
        Return a representation of the objects fields.

        This representation should in turn be serializable by this module.
        """

    @classmethod
    def _from_json_fields(cls: Type[T], o: Any) -> T:
        """
        Instantiate this class from the deserialized json.

        Parameters
        ----------
        o : Any
            The deserialized fields as they were returned
            by :method:`_json_fields` earlier.

        Returns
        -------
        An instance of this class.

        """


#: Python types that this module can encode (without using hooks)
JSONable = Union[
    JSON_TYPE_KEY,
    List["JSONable"],
    Tuple["JSONable", ...],
    Dict[JSON_TYPE_KEY, "JSONable"],
    Transformable,
]


class Encoder(json.JSONEncoder):
    """
    JSON Encoder supporting all kinds of python objects.

    This Encoder supports types/instances implementing the `Transformable`
    protocol. You can also pass hooks to the Encoder for supporting types
    not implementing set protocol.

    Parameters
    ----------
    hooks : Iterable[JSONHook] | JSONHook, optional
        The object hooks to use, by default []
    **kwargs
        Keyword arguments passed to :class:`json.JSONEncoder`

    """

    @overload
    def __init__(self, hook: JSONHook, /, **kwargs: Any) -> None:
        ...

    @overload
    def __init__(self, hooks: Iterable[JSONHook] = [], /, **kwargs: Any) -> None:
        ...

    def __init__(
        self, hooks: Iterable[JSONHook] | JSONHook = [], /, **kwargs: Any
    ) -> None:
        """
        Init the JSON Encoder.

        Parameters
        ----------
        hooks : Iterable[JSONHook] | JSONHook, optional
            The object hooks to use, by default []
        **kwargs
            Keyword arguments passed to :class:`json.JSONEncoder`

        """
        super().__init__(**kwargs)
        self.hooks = {hooks} if isinstance(hooks, JSONHook) else set(hooks)

    @overload
    def register(
        self,
        t1: Type[JSONHook],
        t2: Type[JSONHook],
        /,
        *types: Type[JSONHook],
    ) -> None:
        ...

    @overload
    def register(self, hook: Type[JSONHook], /) -> Type[JSONHook]:
        ...

    def register(self, *ts: Type[JSONHook]) -> Type[JSONHook] | None:
        """
        Register a hook or a transformable type.

        A decoder can only decode serialized objects if their type or a
        corresponding hook was registered with the decoder.

        This method can be used as decorator for :class:`Tranformable` classes
        or hook classes.

        Raises
        ------
        ValueError
            Hook or class already registered
        TypeError
            Invalid type that doesn't implement :class:`JSONHook` or :class:`Transformable`.

        """
        for t in ts:
            self.hooks.add(t)
        return ts[0] if len(ts) == 1 else None

    @staticmethod
    def determine_classname(o: object | type, instance: bool = True) -> str:
        """
        Determine a unique identifier for a python class or instance.

        This method is put in the produced json to encode classes that aren't
        natively supported by JSON.

        Parameters
        ----------
        o : object | type
            The object to identify
        instance : bool, optional
            Whether the object is a class/type or an instance, by default True

        Returns
        -------
        str
            The identifier

        """
        module = getmodule(o)
        mod_name = module.__name__ if module else ""
        c = type(o) if instance else cast(type, o)
        cls_name = c.__qualname__
        return f"{mod_name}.{cls_name}"

    def transform(self, o: JSONable) -> JSON_TYPE_DUMP:
        """
        Replace custom types by an encodable dictionary.

        Parameters
        ----------
        o : JSONable
            The json object to iterate over.

        Returns
        -------
        JSON_TYPE_DUMP
            The resulting json object.

        """
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
        """
        Replace custom types by an encodable dictionary.

        Parameters
        ----------
        o : JSONable
            The json object to iterate over.

        Returns
        -------
        JSON_TYPE_DUMP
            The resulting json object.

        Notes
        -----
        Calls :method:`transform` internally.

        """
        return self.transform(o)

    def iterencode(self, o: JSONable, _one_shot: bool = False) -> Iterator[str]:
        """Encode an object."""
        # called for every top level object to encode
        return super().iterencode(self.transform(o), _one_shot)


T = TypeVar("T", bound=Transformable)


class Decoder(json.JSONDecoder):
    """
    A json decoder supporting all kinds of python objects.

    To decode such an object, three requirements have to be fullfilled:
    1. The object has to implement the :class:`Tranformable`
    protocol or a :class:`JSONHook` has to be implemented for the type.
    2. The object has to be encoded in the correct format as done by :class:`Encoder`.
    3. THe hook or class has to be registered with this decoder. You can use
    :method:`register` for that. This method can also be used as a class decorator.

    Parameters
    ----------
    decoder : Decoder | None, optional
        A decoder to inherit properties from, by default None
    parse_float : Callable[[str], Any] | None, optional
        Float parser, by default None
    parse_int : Callable[[str], Any] | None, optional
        Int parser, by default None
    parse_constant : Callable[[str], Any] | None, optional
        Constant parser, by default None
    strict : bool, optional
        Whether to disallow control characters, by default True

    Attributes
    ----------
    registered_types : List[type]
        The transformable types registered for decoding.
    hooks : List[Type[JSONHook]]
        hooks registered for decoding.

    Methods
    -------
    register(*t)
        Register a hook or a tranformable type.
    register_from(decoder)
        Register all types registered by another decoder.

    """

    def __init__(
        self,
        decoder: Decoder | None = None,
        *,
        parse_float: Callable[[str], Any] | None = None,
        parse_int: Callable[[str], Any] | None = None,
        parse_constant: Callable[[str], Any] | None = None,
        strict: bool = True,
    ) -> None:
        """
        Init the json decoder.

        Parameters
        ----------
        decoder : Decoder | None, optional
            A decoder to inherit properties from, by default None
        parse_float : Callable[[str], Any] | None, optional
            Float parser, by default None
        parse_int : Callable[[str], Any] | None, optional
            Int parser, by default None
        parse_constant : Callable[[str], Any] | None, optional
            Constant parser, by default None
        strict : bool, optional
            Whether to disallow control characters, by default True

        """
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
        """List of transformable types registered for decoding."""
        return list(self.type_dict.values())

    @property
    def hooks(self) -> List[Type[JSONHook]]:
        """List of hooks registered for decoding."""
        return list(self.type_hooks.values())

    @staticmethod
    def determine_classname(t: type) -> str:
        """
        Determine a unique identifier for a class/type.

        This identifier is used to store hooks and types but also
        to select the correct one when its identifier is found in the
        json to decode.

        Parameters
        ----------
        t : type
            The class/type to identify.

        Returns
        -------
        str
            The identifier.

        """
        mod_name = getmodule(t).__name__  # type: ignore
        cls_name = t.__qualname__
        return f"{mod_name}.{cls_name}"

    def register_from(self, decoder: Decoder) -> None:
        """Register all types registered by another decoder."""
        self.register(*decoder.registered_types)
        self.register(*decoder.hooks)

    @overload
    def register(self, t: Type[T], /) -> Type[T]:
        ...

    @overload
    def register(
        self,
        t1: Type[JSONHook] | Type[T],
        t2: Type[JSONHook] | Type[T],
        /,
        *types: Type[JSONHook] | Type[T],
    ) -> None:
        ...

    @overload
    def register(self, hook: Type[JSONHook], /) -> Type[JSONHook]:
        ...

    def register(
        self, *ts: Type[JSONHook] | Type[T]
    ) -> Type[T] | Type[JSONHook] | None:
        """
        Register a hook or a transformable type.

        A decoder can only decode serialized objects if their type or a
        corresponding hook was registered with the decoder.

        This method can be used as decorator for :class:`Tranformable` classes
        or hook classes.

        Raises
        ------
        ValueError
            Hook or class already registered
        TypeError
            Invalid type that doesn't implement :class:`JSONHook` or :class:`Transformable`.

        """
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


@runtime_checkable
class JSONHook(Protocol):
    """Base for hooks for arbitrary python objects."""

    @staticmethod
    def fields(o: Any) -> None | JSONable:
        """
        Return serializable representation of an instances state.

        If an instance isn't support this method should return None.
        Otherwise it should return a representation of the instances
        fields.

        Parameters
        ----------
        o : Any
            Any object that should be encoded.

        Returns
        -------
        None | JSONable
            The fields of the objects if it is supported else None

        """

    @staticmethod
    def from_json(cls: str, o: JSON_TYPE) -> Any:
        """
        Instanciate an object from its fields.

        This method is only called with supported instances that were
        encoded with the help of :method:`fields`.

        Parameters
        ----------
        cls : str
            The identifier of the class to create an instance of.
        o : JSON_TYPE
            The decoded fields.

        Returns
        -------
        Any
            The deserialized object.

        """


#: Constant and global convenience decoder instance
#: that has all types and hooks in this package registered
#: (if the corresponding types were loaded through an import of the containing module)
GLOBAL_DECODER = Decoder()

#: Constant and global convenience encoder instance
#: that has all hooks in this package registered
#: (if they were loaded through an import of the containing module)
GLOBAL_ENCODER = Encoder()


@GLOBAL_ENCODER.register
@GLOBAL_DECODER.register
class std_hook(JSONHook):
    """
    A set of standard hooks implemented by this module.

    This currently on supports the `datetime` class.
    """

    @staticmethod
    def fields(o: Any) -> str | None:
        """Make an object encodable."""
        if isinstance(o, datetime):
            return o.isoformat()
        return None

    @staticmethod
    def from_json(cls: str, o: JSON_TYPE) -> Any:
        """Decode an object."""
        o = cast(str, o)
        return datetime.fromisoformat(o)
