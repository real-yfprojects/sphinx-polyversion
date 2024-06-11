# sphinx-polyversion

[![Static Badge](https://img.shields.io/badge/docs-latest-blue?logo=github&color=5cabff)](https://real-yfprojects.github.io/sphinx-polyversion/)
[![pypi](https://img.shields.io/pypi/v/sphinx-polyversion.svg?logo=pypi&logoColor=white&color=0073b7)](https://pypi.org/project/sphinx-polyversion/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/sphinx-polyversion?color=ffd43b)](https://pypi.org/project/sphinx-polyversion/)
[![Github License](https://img.shields.io/github/license/real-yfprojects/sphinx-polyversion)](https://github.com/real-yfprojects/sphinx-polyversion/blob/main/LICENSE)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/sphinx-polyversion)](https://pypi.org/project/sphinx-polyversion/)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v0.json)](https://github.com/charliermarsh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://pre-commit.com)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

<!-- description -->

Build multiple versions of your sphinx docs and merge them into one website.

- Isolated builds using venv, virtualenv or poetry
- git support
- Build with `sphinx-build` or custom commands
- Access and modify all versioning data inside `conf.py`
- Concurrent builds
- Override build configuration from commandline easily
- Render templates to the root directory containing the docs for each version
- Build from local working tree easily while mocking version data
- Not a sphinx extension -> standalone tool
- Configuration in a python script
- Highly customizable and scriptable through OOP
- Implement subclasses in your configuration script to add support for other VCS, Project/dependency management tools, build tools and whatever you require
- IDE integration and autocompletion

<!-- end description -->

Have a look at the [roadmap](./ROADMAP.md) to find out about upcoming features.

## Installation

```
pip install sphinx-polyversion
```

```
poetry add --group docs sphinx-polyversion
```

## Usage

### Example

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

#: Mock data used for building local version
MOCK_DATA = {
    "revisions": [
        GitRef("v1.8.0", "", "", GitRefType.TAG, datetime.fromtimestamp(0)),
        GitRef("v1.9.3", "", "", GitRefType.TAG, datetime.fromtimestamp(1)),
        GitRef("v1.10.5", "", "", GitRefType.TAG, datetime.fromtimestamp(2)),
        GitRef("master", "", "", GitRefType.BRANCH, datetime.fromtimestamp(3)),
        GitRef("dev", "", "", GitRefType.BRANCH, datetime.fromtimestamp(4)),
        GitRef("some-feature", "", "", GitRefType.BRANCH, datetime.fromtimestamp(5)),
    ],
    "current": GitRef("local", "", "", GitRefType.BRANCH, datetime.fromtimestamp(6)),
}
MOCK = False

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
    mock=MOCK_DATA,
).run(MOCK)
```

Build your docs by running

```console
$ sphinx-polyversion docs/poly.py
```

### Commandline Options

```
usage: sphinx-polyversion [-h] [-o [OVERRIDE [OVERRIDE ...]]] [-v] [-l] conf [out]

Build multiple versions of your sphinx docs and merge them into one site.

positional arguments:
  conf                  Polyversion config file to load. This must be a python file that can be evaluated.
  out                   Output directory to build the merged docs to.

optional arguments:
  -h, --help            show this help message and exit
  -o [OVERRIDE [OVERRIDE ...]], --override [OVERRIDE [OVERRIDE ...]]
                        Override config options. Pass them as `key=value` pairs.
  -v, --verbosity       Increase output verbosity (decreases minimum log level). The default log level is ERROR.
  -l, --local, --mock   Build the local version of your docs.
```

### How To Build Versions Differently

```py
#: Mapping of revisions to changes in build parameters
BUILDER = {
    None: SphinxBuilder(Path("docs")),  # default
    "v1.5.7": SphinxBuilder(Path("docs/source")),
    "v2.0.0": CommandBuilder(
        Path("docs/source"),
        ["sphinx-autodoc", Placeholder.SOURCE_DIR, Placeholder.OUTPUT_DIR],
    ),
    "v2.4.0": CommandBuilder(
        Path("docs/source/sphinx"),
        ["sphinx-autodoc", Placeholder.SOURCE_DIR, Placeholder.OUTPUT_DIR],
    ),
}

#: Mapping of revisions to changes in environment parameters
ENVIRONMENT = {
    None: Poetry.factory(args="--sync".split()),  # first version
    "v1.5.7": Poetry.factory(args="--only sphinx --sync".split()),
    "v1.8.2": Poetry.factory(args="--only dev --sync".split()),
    "v3.0.0": Pip.factory(venv=Path(".venv"), args="-e . -r requirements.txt".split()),
}

# ...

DefaultDriver(
    # ...
    builder=BUILDER,
    env=ENVIRONMENT,
    selector=partial(closest_tag, root),
    # ...
).run()
```

### Data Passed to Sphinx

```py
{"revisions": [GitRef(...), GitRef(...)], "current": GitRef(...)}
```

You can change the format by passing your own factory.

```py
def data(driver: DefaultDriver, rev: GitRef, env: Environment):
    return {
      "tags": list(filter(lambda r: r.type_ == GitRefType.TAG, driver.targets)),
      "branches": list(filter(lambda r: r.type_ == GitRefType.BRANCH, driver.targets)),
      "current": rev,
    }

# ...

DefaultDriver(
    # ...
    data_factory=data,
    # ...
).run()
```

## Contributing

Contributions of all kinds are welcome. That explicitely includes suggestions for enhancing the API, the architecture or the documentation of the project.
PRs are greatly appreciated as well. But please make sure that your change is wanted by opening an issue about it first before you waste your time with a PR
that isn't merged in the end.

## License

MIT License <br>
See the [LICENSE](./LICENSE) file which should be located in this directory.
