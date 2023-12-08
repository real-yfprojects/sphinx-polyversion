"""Test encoding and deconding of python types and objects to  the json format."""

from datetime import datetime

from sphinx_polyversion.git import GitRef, GitRefType
from sphinx_polyversion.json import Decoder, Encoder, std_hook


class TestEncoder:
    """Unittests for the `Encoder` class."""

    def test_register_hook(self):
        """Test that register() adds a hook to the encoder's hooks dictionary."""
        encoder = Encoder()

        assert encoder.hooks == set()

        result = encoder.register(std_hook)

        assert result == std_hook
        assert encoder.hooks == {std_hook}

        encoder.register(std_hook, std_hook())

        assert len(encoder.hooks) == 2

    def test_register_type(self):
        """Test that register() adds a type to the encoder's hooks dictionary."""
        encoder = Encoder()

        assert encoder.hooks == set()

        result = encoder.register(GitRefType)

        assert result == GitRefType
        assert encoder.hooks == {GitRefType}

        encoder.register(GitRef, GitRefType)

        assert len(encoder.hooks) == 2

    def test_determine_classname(self):
        """Test that determine_classname() returns the expected class name for a given object."""
        encoder = Encoder()

        assert (
            encoder.determine_classname(GitRef, instance=False)
            == "sphinx_polyversion.git.GitRef"
        )
        assert encoder.determine_classname(3) == ".int"

        from pathlib import Path

        assert encoder.determine_classname(Path, instance=False) == "pathlib.Path"

        assert (
            encoder.determine_classname(datetime, instance=False) == "datetime.datetime"
        )
        assert encoder.determine_classname(datetime(2023, 1, 1)) == ".datetime"

    def test_transform_hook(self):
        """Test transforming hook."""
        encoder = Encoder()
        encoder.register(std_hook)

        assert encoder.transform(datetime(2023, 12, 2)) == {
            "__jsonhook__": (
                "sphinx_polyversion.json.std_hook",
                ".datetime",
                "2023-12-02T00:00:00",
            )
        }

    def test_transform_class(self) -> None:
        """Test transforming the `Transformable` class.."""
        encoder = Encoder()
        assert encoder.transform(GitRef("master", "3434", "", None, None)) == {
            "__jsonclass__": (
                "sphinx_polyversion.git.GitRef",
                ["master", "3434", "", None, None, None],
            )
        }

    def test_transform_dict(self):
        """Test that transform() returns the expected dictionary for a given dictionary with nested objects."""
        encoder = Encoder()
        assert encoder.transform({"ref": GitRef("master", "3434", "", None, None)}) == {
            "ref": {
                "__jsonclass__": (
                    "sphinx_polyversion.git.GitRef",
                    ["master", "3434", "", None, None, None],
                )
            }
        }

    def test_transform_list(self):
        """Test that transform() returns the expected list for a given list with nested objects."""
        encoder = Encoder()
        assert encoder.transform([GitRef("master", "3434", "", None, None)]) == [
            {
                "__jsonclass__": (
                    "sphinx_polyversion.git.GitRef",
                    ["master", "3434", "", None, None, None],
                )
            }
        ]

    def test_transform_any(self):
        """Test that transform() returns the input object for an unknown object."""
        encoder = Encoder()
        o = object()
        assert encoder.transform(o) == o

    def test_encode(self):
        """
        Test that encode() returns the expected JSON string for a given object.

        This uses dict, list, transformable, hook and some standard datatypes
        """
        encoder = Encoder()
        encoder.register(std_hook)
        obj = {
            "ref": GitRef(
                "master",
                "3434",
                "refs/tags/v1.0.0",
                GitRefType.TAG,
                datetime(200, 2, 6, 6, 3, 6),
            ),
            "date": datetime(2023, 12, 2),
            "list": [1, 2, 3],
            "dict": {"a": 1, "b": 2},
        }
        assert (
            encoder.encode(obj)
            == '{"ref": {"__jsonclass__": ["sphinx_polyversion.git.GitRef", ["master", "3434", "refs/tags/v1.0.0", {"__jsonclass__": ["sphinx_polyversion.git.GitRefType", "TAG"]}, {"__jsonhook__": ["sphinx_polyversion.json.std_hook", ".datetime", "0200-02-06T06:03:06"]}, null]]}, "date": {"__jsonhook__": ["sphinx_polyversion.json.std_hook", ".datetime", "2023-12-02T00:00:00"]}, "list": [1, 2, 3], "dict": {"a": 1, "b": 2}}'
        )


class TestDecoder:
    """Unittests for the `Decoder` class."""

    def test_register_hook(self):
        """Test that register() adds a hook to the decoder's hooks dictionary."""
        decoder = Decoder()
        decoder.register(std_hook)
        assert std_hook in decoder.hooks

    def test_register_type(self):
        """Test that register() adds a type to the decoder's registered_types dictionary."""
        decoder = Decoder()
        decoder.register(GitRefType)
        assert GitRefType in decoder.registered_types

    def test_register_from(self):
        """Test that register_from() adds the same hooks and types to both the encoder and decoder."""
        decoder_1 = Decoder()
        decoder_1.register(GitRef, GitRefType)
        assert decoder_1.registered_types == [GitRef, GitRefType]

        decoder_2 = Decoder()
        decoder_2.register_from(decoder_1)
        assert GitRef in decoder_2.registered_types
        assert GitRefType in decoder_2.registered_types

    def test_determine_classname(self):
        """Test that determine_classname() returns the expected class name for a given object."""
        decoder = Decoder()

        assert decoder.determine_classname(GitRef) == "sphinx_polyversion.git.GitRef"

        from pathlib import Path

        assert decoder.determine_classname(Path) == "pathlib.Path"

    def test_decode(self):
        """Test that decode() returns the expected object for a given JSON string."""
        obj = {
            "ref": GitRef(
                "master",
                "3434",
                "refs/tags/v1.0.0",
                GitRefType.TAG,
                datetime(200, 2, 6, 6, 3, 6),
            ),
            "date": datetime(2023, 12, 2),
            "list": [1, 2, 3],
            "dict": {"a": 1, "b": 2},
        }
        encoded = '{"ref": {"__jsonclass__": ["sphinx_polyversion.git.GitRef", ["master", "3434", "refs/tags/v1.0.0", {"__jsonclass__": ["sphinx_polyversion.git.GitRefType", "TAG"]}, {"__jsonhook__": ["sphinx_polyversion.json.std_hook", ".datetime", "0200-02-06T06:03:06"]}, null]]}, "date": {"__jsonhook__": ["sphinx_polyversion.json.std_hook", ".datetime", "2023-12-02T00:00:00"]}, "list": [1, 2, 3], "dict": {"a": 1, "b": 2}}'

        decoder = Decoder()
        decoder.register(std_hook)
        decoder.register(GitRef, GitRefType)
        assert decoder.decode(encoded) == obj


class TestStd_Hook:
    """Ensure the hooks provided by this module work."""

    def test_encode_datetime(self):
        """Test the returned fields for `datetime`."""
        dt = datetime(2023, 8, 6, 6, 3, 6)
        assert std_hook.fields(dt) == "2023-08-06T06:03:06"

    def test_decode_datetime(self):
        """Test calling `from_json` for a `datetime`."""
        dt = std_hook.from_json("datetime.datetime", "2023-08-06T06:03:06")
        assert dt == datetime(2023, 8, 6, 6, 3, 6)
