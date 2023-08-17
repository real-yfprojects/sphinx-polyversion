---------------
Getting Started
---------------

This guide will show you how to create a minimal setup for your project.
At the same time it will link resources where you can find more information
for specific customizations and use cases.
This guide assumes that you installed `sphinx-polyversion` into the development
environment of your project and have written some documentation that builds
with `sphinx-build`.

.. TODO: link sphinx docs / sphinx build

Configuring `sphinx-polyversion`
--------------------------------

With `sphinx-polyversion` everything revolves around its configuration file
which is a python script conventionally named `poly.py`.
This configuration file will be executed when calling `sphinx-polyversion`.
This tool is designed in such a way that `poly.py` does all the heavy lifting.
In fact there is no need to run :code:`sphinx-polyversion` from the commandline.
Instead you can execute `poly.py` directly to build your documentation.
However the `sphinx_polyversion`
python package provides the underlying logic as well as helpful utilities.
This design makes sphinx-polyversion highly customizable and extendable allowing
it to be used in all kinds of applications - even those that the developers
of `sphinx-polyversion` didn't even think about.

By convention the `poly.py` file follows a specific structure that provides
some benefits in combination with this tool. This section will walk you through
this structure.

Start off with defining the config options to be used for building
your versioned documentation. This is done by initializing variables
in the global scope. You can find a reasonable example below.
Since `poly.py` is a self contained python script you decide every detail
of the build process including all configuration options. There are
no specifications you have to conform to when deciding on the config options
you define and how you name them.

.. warning::

    There are to naming specifications for config variables:
    The output directory must always be called :code:`OUTPUT_DIR`.
    And you have to pass :code:`MOCK` to :code:`DefaultDriver.run`.

.. TODO link reference

.. note::

    Config options will be passed to the build logic later.
    This requires types like :code:`tuple` or :code:`Path` and fortunally
    any type can be used for config options.
    However it makes sense to stick to :code:`string` where possible
    since the overrides will always be a string entered from the commandline.
    Currently there is no system to convert these string to other python
    types. If you have an idea how to design a system
    that follows the philosophy of this project please open a discussion on github.

.. TODO: link override section
.. TODO link philosophy and discussions

Defining the options as variables at the beginning not only makes
the configuration file easier to understand but also allows those variables to
be overridden from the commandline before being used to build the documentation.
This is a major feature of `sphinx-polyversion` which will be explained
further down this guide.

.. TODO: link overrides section

.. code-block:: py
    :caption: `docs/poly.py` - imports and config variables
    :linenos:

    from pathlib import Path
    from datetime import datetime
    from sphinx_polyversion import *
    from sphinx_polyversion.git import *
    from sphinx_polyversion.pyvenv import Poetry
    from sphinx_polyversion.sphinx import SphinxBuilder

    #: Regex matching the branches to build docs for
    BRANCH_REGEX = r".*"

    #: Regex matching the tags to build docs for
    TAG_REGEX = r".*"

    #: Output dir relative to project root
    #: !!! This name has to be choosen !!!
    OUTPUT_DIR = "docs/build"

    #: Source directory
    SOURCE_DIR = "docs/"

    #: Arguments to pass to `poetry install`
    POETRY_ARGS = "--only docs --sync"

    #: Arguments to pass to `sphinx-build`
    SPHINX_ARGS = "-a -v"

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


Next you add the code handling the overrides read from the commandline.
This is straightforward since `sphinx-polyversion` provides the function :code:`apply_overrides` that
takes care of that. It parses the commandline arguments and overrides
the config variables with the given values. For that you need to pass
the :code:`globals()` dictionary to the function.

.. TODO link function


.. code-block:: py
    :caption: `docs/poly.py` - overrides
    :linenos:
    :lineno-start: 38

    # Load overrides read from commandline to global scope
    apply_overrides(globals())

The `poly.py` file is finished with adding the code that actually builds
the different versions of the documentation.

First you determine the root folder of the repository.
It makes sense to use the method provided since
you might call the script from arbitrary locations. The root will be used
for determining the locations of the template, source and static directories.

After that you initialize the :code:`DefaultDriver` class using the config options
you defined earlier. The driver uses the passed :code:`vcs` object to determine which
versions to build. It will proceed with running the :code:`builder` object
in the :code:`env` environment. In this case :code:`sphinx-build` is run in a python
virtual environment created with *poetry* for each version. This means that each
version is build in an isolated environment with the dependencies defined
in its revision.

.. TODO link reference
.. TODO link poetry

.. code-block:: py
    :caption: `docs/poly.py` - building the docs
    :linenos:
    :lineno-start: 41

    # Determine repository root directory
    root = Git.root(Path(__file__).parent)

    # Setup driver and run it
    src = Path(SOURCE_DIR)  # convert from string
    DefaultDriver(
        root,
        OUTPUT_DIR,
        vcs=Git(
            branch_regex=BRANCH_REGEX,
            tag_regex=TAG_REGEX,
            buffer_size=1 * 10**9,  # 1 GB
            predicate=file_predicate([src]),  # exclude refs without source dir
        ),
        builder=SphinxBuilder(src / "sphinx", args=SPHINX_ARGS.split()),
        env=Poetry.factory(args=POETRY_ARGS.split()),
        template_dir=root / src / "templates",
        static_dir=root / src / "static",
        mock=MOCK_DATA,
    ).run(MOCK)

Using versioning data in :code:`conf.py`
----------------------------------------

When using sphinx the versioning data (current revision, list of all revisions,
...)
can be accessed inside the `conf.py` file and inside the jinja templates used
to render the docs. For that the version data is serialized to json and
exposed through an environment variable to sphinx. The data can the be
read in `conf.py` and written to `html_context`. This sphinx configuration
variable holds a dictionary with fields available in jinja templates.

Luckily you don't have to worry about that, the :code:`load` function takes
care of everything for you. After calling this function the following data
is merged into `html_context`. You can customize what data is passed to sphinx
though.

.. TODO: link docs for data format

.. code-block:: py
    :caption: default data exposed to sphinx docs

    {
        # All revisions to be build
        "revisions": Tuple[GitRef, ...],
        # The revision sphinx is currently building
        "current": GitRef,
    }

.. code-block:: py
    :caption: `docs/conf.py` - loading versioning data
    :linenos:
    :lineno-start: 6

    # -- Load versioning data ----------------------------------------------------

    from sphinx_polyversion import load
    from sphinx_polyversion.git import GitRef

    data = load(globals())  # adds variables `current` and `revisions`
    current: GitRef = data['current']

Populating the root of the merged docs
--------------------------------------

The docs for each revision will be build into a subfolder of the `docs/build`:

.. code-block::

    docs/build
    ├───dev
    ├───master
    ├───v2.3
    ├───v2.4
    └───v3.7

You can add global pages to the root of the documentation. That is `docs/build/`.
Those can either be static files that are copied or templates that are rendered
using `jinja2`. In this example static files will be located in `docs/static`
and templates in `docs/templates`. This results in the following layout:

.. TODO link jinja2

.. code-block::

    docs
    ├───build
    ├───sphinx
    │   ├───_static
    │   ├───_templates
    │   └───conf.py
    ├───static
    ├───templates
    │   └───index.html
    └───poly.py

The :code:`index.html` file is optional but makes sense since it will be the page
shown when entering the url to your documentation. In most cases you will want
the it to redirect to the latest revision of the sphinx docs. The following jinja
template generates the corresponding html.

.. code-block:: html+jinja
    :linenos:
    :caption: `docs/templates/index.html`

    <!doctype html>

    <html>
        <head>
            <title>Redirecting to master branch</title>
            <meta charset="utf-8" />
            <meta
                http-equiv="refresh"
                content="0; url=./{{ latest.name }}/index.html"
            />
            <link rel="canonical" href="./{{ latest.name }}/index.html" />
        </head>
    </html>

You will have to add some lines to `poly.py` since the template requires
a `latest` field that isn't provided by default since `sphinx-polyversion` can't
know which tag represents the latest revision. First you have to implement
:code:`root_data` (see below) and then pass :code:`root_data_factory=root_data`
to :code:`DefaultDriver`.

.. TODO link reference

.. code-block:: py
    :caption: `docs/poly.py` - calculate and expose latest revision
    :linenos:
    :lineno-start: 40

    from sphinx_polyversion.git import refs_by_type

    def root_data(driver: DefaultDriver):
        revisions = driver.builds
        tags, branches  = refs_by_type(revisions)
        latest = max(tags or branches)
        return {"revisions": revisions, "latest": latest}



Building with `sphinx-polyversion`
----------------------------------

Now that everything is setup you can actually run `sphinx-polyversion` and
build your versioned documentation. All versions configured in `poly.py` will
be build. However if you want to test local changes you can use the :code:`-l`
flag to build a documentation from the files in the local filesystem. When passing
this flag all other versions are not build.

.. argparse::
    :ref: sphinx_polyversion.main.get_parser
    :prog: sphinx_polyversion
    :nodescription:


Overriding config options
-------------------------

You can override the defaults set in `poly.py` by specifying values on the
commandline. Specifying an output location will override :code:`OUTPUT_DIR` while
specifying :code:`--local` will set :code:`MOCK` to :code:`True`.
All other variables can be overidden through the :code:`-o` flag. You can
override the arguments passed to `sphinx-build` by entering the following:

.. code-block:: bash

    sphinx-polyversion docs/poly.py -o SPHINX_BUILD='-T -v'


Adding a version picker to the docs
-----------------------------------

There are plenty of ways how to add a widget to your rendered documentation that allows
the user to select the version to view. Some themes might come with a version picker build-in
while for the others you have to add one yourself. Usually you can leverage sphinx template
system for that. For a reference you can have a look how this documentation implemented
the version picker.

.. TODO link relevant code
