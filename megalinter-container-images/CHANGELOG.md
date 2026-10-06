# Changelog

## [12.0.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-container-images-v11.0.3...megalinter-container-images-v12.0.0) (2026-10-06)


### ⚠ BREAKING CHANGES

* **megalinter:** PYTHON_PYLINT is removed from megalinter-container-images, megalinter-sungather, megalinter-go and megalinter-spruyt-labs. Before bumping the pin, replace PYTHON_PYLINT in ENABLE_LINTERS with PYTHON_RUFF and PYTHON_RUFF_FORMAT (container-images, sungather) or remove it (go, spruyt-labs), or MegaLinter fails with "Fatal error while calling pylint".

### Features

* **megalinter:** drop pylint from four flavors; enable PYTHON_RUFF instead of PYTHON_PYLINT ([#2093](https://github.com/anthony-spruyt/container-images/issues/2093)) ([f288272](https://github.com/anthony-spruyt/container-images/commit/f2882726ec5adb75c7b0981d3d3fca126c8a0777))

## [11.0.3](https://github.com/anthony-spruyt/container-images/compare/megalinter-container-images-v11.0.2...megalinter-container-images-v11.0.3) (2026-10-04)


### Dependencies

* **megalinter:** weekly linter version refresh ([#2053](https://github.com/anthony-spruyt/container-images/issues/2053)) ([6738ed7](https://github.com/anthony-spruyt/container-images/commit/6738ed797d34076c76350386abfe2eb70c7edb12))

## [11.0.2](https://github.com/anthony-spruyt/container-images/compare/megalinter-container-images-v11.0.1...megalinter-container-images-v11.0.2) (2026-09-27)


### Dependencies

* **megalinter:** weekly linter version refresh ([#1934](https://github.com/anthony-spruyt/container-images/issues/1934)) ([89cb6c2](https://github.com/anthony-spruyt/container-images/commit/89cb6c2158d4770bd7d84d977450a5297ea60e89))

## [11.0.1](https://github.com/anthony-spruyt/container-images/compare/megalinter-container-images-v11.0.0...megalinter-container-images-v11.0.1) (2026-09-20)


### Continuous Integration

* **megalinter:** stamp every flavor, including new ones ([#1872](https://github.com/anthony-spruyt/container-images/issues/1872)) ([da38b7d](https://github.com/anthony-spruyt/container-images/commit/da38b7d6ac85169e7e9b2b1adf64c56c934ff379))

## [11.0.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-container-images-v10.0.53...megalinter-container-images-v11.0.0) (2026-09-19)


### ⚠ BREAKING CHANGES

* **megalinter-container-images:** MegaLinter v10 removes REPOSITORY_GITLEAKS. Consumers must migrate to REPOSITORY_BETTERLEAKS before bumping this image pin.

### Dependencies

* **megalinter-container-images:** rebase onto MegaLinter v10.1.0 ([#1783](https://github.com/anthony-spruyt/container-images/issues/1783)) ([c900ebc](https://github.com/anthony-spruyt/container-images/commit/c900ebc14886e4acfa7e6679a010e64284e4ae22))

## [10.0.53](https://github.com/anthony-spruyt/container-images/compare/megalinter-container-images-v10.0.52...megalinter-container-images-v10.0.53) (2026-09-07)


### Continuous Integration

* **release:** migrate remaining images and retire the old pipeline ([#1460](https://github.com/anthony-spruyt/container-images/issues/1460)) ([7ac4a52](https://github.com/anthony-spruyt/container-images/commit/7ac4a52d2bcb9955fec7073b5e7281f68ba2d28e))
