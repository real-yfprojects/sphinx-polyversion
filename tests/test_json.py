from datetime import datetime

from sphinx_polyversion.git import GitRef, GitRefType
from sphinx_polyversion.json import Decoder, Encoder, std_hook


class TestEncoder:
    def test_register_hook(self):
        encoder = Encoder()

        assert encoder.hooks == set()

        result = encoder.register(std_hook)

        assert result == std_hook
        assert encoder.hooks == {std_hook}

        encoder.register(std_hook, std_hook())

        assert len(encoder.hooks) == 2

    def test_register_type(self):
        encoder = Encoder()

        assert encoder.hooks == set()

        result = encoder.register(GitRefType)

        assert result == GitRefType
        assert encoder.hooks == {GitRefType}

        encoder.register(GitRef, GitRefType)

        assert len(encoder.hooks) == 2

    def test_determine_classname(self):
        encoder = Encoder()

        assert (
            encoder.determine_classname(GitRef, instance=False)
            == "sphinx_polyversion.git.GitRef"
        )
        assert encoder.determine_classname(3) == ".int"

        from pathlib import Path

        assert encoder.determine_classname(Path, instance=False) == "pathlib.Path"

    def test_transform_hook(self):
        # test transforming json hook
        pass

    def test_transform_class(self):
        # test transforming transformable (results in json class)
        pass

    def test_transform_dict(self):
        # test recursive calls in case of dict
        pass

    def test_transform_list(self):
        # test recursive calls in case of list
        pass

    def test_transform_any(self):
        # test it passes unknown objects through
        pass

    def test_encode(self):
        # test encoding one big object containing
        # dict, list, transformable, hook and some standard datatypes
        pass


class TestDecoder:
    def test_register_hook(self):
        # register and check whether hook is in hooks property
        pass

    def test_register_type(self):
        # register and check whether type is in `registered_types` property
        pass

    def test_register_from(self):
        # test that both decoders know the same hooks and types
        pass

    def test_determine_classname(self):
        decoder = Decoder()

        assert decoder.determine_classname(GitRef) == "sphinx_polyversion.git.GitRef"

        from pathlib import Path

        assert decoder.determine_classname(Path) == "pathlib.Path"


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
