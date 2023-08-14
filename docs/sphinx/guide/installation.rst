------------
Installation
------------

This tool can be installed as a os-independent python package. You will therefore
need a Python installation and a python package manager like *pip*.
Sphinx-polyversion is available on pypi.org. But you can also install the package
directly from its git repository.

.. TODO: link pypi

Sphinx-polyversion provides integration with virtualenv and jinja. By specifying
the respective dependency groups you can install them alongside the tool.

.. TODO: link to pages explaining jinja and virtualenv integration
.. TODO: link article about dependency groups

.. tab-set::

    .. tab-item:: Pip
        :sync: pip

        .. code-block:: bash

            pip install sphinx-polyversion[jinja,virtualenv]

    .. tab-item:: Poetry
        :sync: poetry
        :selected:

        .. code-block:: bash

            poetry add --group docs sphinx-polyversion[jinja,virtualenv]

    .. tab-item:: Pipenv
        :sync: pipenv

        .. code-block:: bash

            pipenv install --dev sphinx-polyversion[jinja,virtualenv]

.. note:: The minimum supported Python version is **3.8**.

Installing from Source
----------------------

If you want to setup a development environment refer to this guide.

.. TODO: Link dev guide

.. tab-set::

    .. tab-item:: Pip
        :sync: pip

        .. code-block:: bash

            pip install git+https://github.com/real-yfprojects/sphinx-polyversion[jinja,virtualenv]

    .. tab-item:: Poetry
        :sync: poetry
        :selected:

        .. code-block:: bash

            poetry add --group docs git+https://github.com/real-yfprojects/sphinx-polyversion[jinja,virtualenv]

    .. tab-item:: Pipenv
        :sync: pipenv

        .. code-block:: bash

            pipenv install --dev git+https://github.com/real-yfprojects/sphinx-polyversion[jinja,virtualenv]
