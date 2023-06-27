# sphinx-polyversion

Build multiple versions of your sphinx docs and merge them into one website.

- Isolated builds using venv, virtualenv or poetry
- git support
- Build with `sphinx-build` or custom commands
- Access and modify all versioning data inside `conf.py`
- Concurrent builds
- Override build configuration from commandline easily
- Render templates to the root directory containing the docs for each version
- Not a sphinx extension -> standalone tool
- Configuration in a python script
- Highly customizable and scriptable through OOP
- Implement subclasses in your configuration script to add support for other VCS, Project/dependency management tools, build tools and whatever you require
- IDE integration and autocompletion

Have a look at the [roadmap](./ROADMAP.md) to find out about upcoming features.

## Example

Setup your sphinx docs in `docs/source/sphinx`. Add a `conf.py` file
with the following to set directory:

```py
from sphinx_polyversion.api import load

load(globals())
# This adds the following to the global scope
# html_context = {
#     "revisions": [GitRef('main', ...), GitRef('v6.8.9', ...), ...],
#     "current": GitRef('v1.4.6', ...),
# }

# process the loaded version information as you wish
html_context["latest"] = max(html_context["revisions"]) # latest by date

# sphinx config
project = "foo"
# ...
```

Configure `sphinx-polyversion` in the file `docs/poly.py`.

```py
from pathlib import Path

from sphinx_polyversion.api import apply_overrides
from sphinx_polyversion.driver import DefaultDriver
from sphinx_polyversion.git import Git, file_predicate
from sphinx_polyversion.pyvenv import Poetry
from sphinx_polyversion.sphinx import SphinxBuilder

#: Regex matching the branches to build docs for
BRANCH_REGEX = r".*"

#: Regex matching the tags to build docs for
TAG_REGEX = r".*"

#: Output dir relative to project root
OUTPUT_DIR = "docs/build"

#: Source directory
SOURCE_DIR = "docs/source"

#: Arguments to pass to `poetry install`
POETRY_ARGS = "--only sphinx --sync".split()

#: Arguments to pass to `sphinx-build`
SPHINX_ARGS = "-a -v".split()

# Load overrides read from commandline to global scope
apply_overrides(globals())
# Determine repository root directory
root = Git.root(Path(__file__).parent)

# Setup driver and run it
src = Path(SOURCE_DIR)
DefaultDriver(
    root,
    OUTPUT_DIR,
    vcs=Git(
        branch_regex=BRANCH_REGEX,
        tag_regex=TAG_REGEX,
        buffer_size=1 * 10**9,  # 1 GB
        predicate=file_predicate([src]), # exclude refs without source dir
    ),
    builder=SphinxBuilder(src / "sphinx", args=SPHINX_ARGS),
    env=Poetry.factory(args=POETRY_ARGS),
    template_dir=root / src / "templates",
    static_dir=root / src / "static",
).run()
```

Build your docs by running

```console
$ sphinx-polyversion docs/poly.py
```

## Installation

This project is not yet released and therefore cannot be installed from pypi yet.

```
pip install git+https://github.com/real-yfprojects/sphinx-polyversion@main
```

```
poetry add --group docs git+https://github.com/real-yfprojects/sphinx-polyversion@main
```

## Contributing

Contributions of all kinds are welcome. That explicitely includes suggestions for enhancing the API, the architecture or the documentation of the project.
PRs are greatly appreciated as well. But please make sure that your change is wanted by opening an issue about it first before you waste your time with a PR
that isn't merged in the end.

## License

MIT License <br>
See the [LICENSE](./LICENSE) file which should be located in this directory.
