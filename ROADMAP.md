# 0.1.0

- [x] Abstract Architecture
- [x] Default Driver
- [x] Command Builder
- [x] Sphinx Builder
- [x] NoneEnvironment (doesn't do anything)
- [x] PIP Environment
- [x] POETRY Environment
- [x] GIT Provider
- [x] Implement API for conf.py
  - [x] Provide data class for use in conf.py
  - [x] Load values

# 0.2.0

- [x] Docstrings
- [x] Venv support
- [x] Virtualenv support
- [x] Implement root render
- [x] Implement API for polyconf.py
  - [x] Override conf values
  - [x] Basic configuration
- [x] Entry point to run from terminal

# 0.3.0

- [x] Fix async file_predicate
- [x] Fix Poetry env location
- [x] Register hooks with Encoder

# 0.4.0

- [x] Helpers for dynamic build paths and etc.
- [x] Sort tags
  - [x] by date
  - [x] by name
- [x] Allow str in addition to Path in commonly used API
- [x] Extend API for conf.py with quality of life improvements
- [x] Make VCS provide a namer
- [x] README

# 0.5.0

- [x] Custom data format - depending on version
- [x] Verbosity flag
- [x] Pre and post build commands
- [x] Easily build local version and mocking
- [x] PyPi package

# 1.0.0

- [x] 70% Test coverage
  - [x] Unittests
  - [x] Integration tests
- [ ] Enhance README
  - [ ] Comparison to alternatives
- [ ] CI
  - [ ] Coverage badge
  - [ ] Test badge
  - [ ] publish to pypi on release
  - [x] Tests
  - [x] Doc preview
  - [x] Linting
- [x] Docs on Github Pages

# 1.0.1

- [ ] Extensive Documentation
  - [ ] User guide
    - [ ] Use different setups depending on the version
  - [ ] Subclassing guide
  - [ ] Reference
    - [ ] Command line syntax
    - [ ] API
    - [ ] Abstract classes
    - [ ] Implementations
- [ ] Contributing Standards
  - [ ] Contributing
  - [ ] Workflows, Policies
  - [ ] Maintaining
- [ ] CI
  - [ ] Change in coverage
  - [ ] Highlight linting problems in PR
  - [ ] Higlight uncovered code in PR

# 1.1.0

- [ ] Caching (e.g. of poetry envs)
- [ ] Only rebuild changed versions
- [ ] Easy integration with ci
- [ ] Github Action
- [ ] Read conf file location from pyproject.toml?

# Wishlist

- typed overrides
