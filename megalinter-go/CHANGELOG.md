# Changelog

## [2.0.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-go-1.0.0...megalinter-go-2.0.0) (2026-10-06)


### ⚠ BREAKING CHANGES

* **megalinter:** PYTHON_PYLINT is removed from megalinter-container-images, megalinter-sungather, megalinter-go and megalinter-spruyt-labs. Before bumping the pin, replace PYTHON_PYLINT in ENABLE_LINTERS with PYTHON_RUFF and PYTHON_RUFF_FORMAT (container-images, sungather) or remove it (go, spruyt-labs), or MegaLinter fails with "Fatal error while calling pylint".

### Features

* **megalinter:** drop pylint from four flavors; enable PYTHON_RUFF instead of PYTHON_PYLINT ([#2093](https://github.com/anthony-spruyt/container-images/issues/2093)) ([f288272](https://github.com/anthony-spruyt/container-images/commit/f2882726ec5adb75c7b0981d3d3fca126c8a0777))

## 1.0.0 (2026-10-06)


### Features

* **megalinter:** add megalinter-go and megalinter-python flavors ([#2083](https://github.com/anthony-spruyt/container-images/issues/2083)) ([20a3fa0](https://github.com/anthony-spruyt/container-images/commit/20a3fa0e68c86b53c4ad5eba2b95be27a3d3a454))
