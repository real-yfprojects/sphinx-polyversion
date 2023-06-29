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

# 1.0.0-alpha1

- [ ] High Test coverage
  - [ ] Unittests
  - [ ] Integration tests
- [ ] Enhance README

# 1.0.0

- [ ] Contributing Standards
- [ ] Extensive Documentation
  - [ ] User guide
  - [ ] Subclassing guide
  - [ ] Reference
  - [ ] Contributing
  - [ ] Workflows, Policies
  - [ ] Maintaining
- [ ] CI
- [ ] Docs on Github Pages

- [ ] PyPi package

# 1.1.0

- [ ] Only rebuild changed versions
- [ ] Easy integration with ci
- [ ] Github Action
- [ ] Read conf file location from pyproject.toml?

# Wishlist

- Limit number of subprocesses to CPU count to optimize speed
- typed overrides
