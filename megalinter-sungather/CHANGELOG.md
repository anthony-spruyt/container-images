# Changelog

## [3.0.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-sungather-2.0.3...megalinter-sungather-3.0.0) (2026-10-06)


### ⚠ BREAKING CHANGES

* **megalinter:** PYTHON_PYLINT is removed from megalinter-container-images, megalinter-sungather, megalinter-go and megalinter-spruyt-labs. Before bumping the pin, replace PYTHON_PYLINT in ENABLE_LINTERS with PYTHON_RUFF and PYTHON_RUFF_FORMAT (container-images, sungather) or remove it (go, spruyt-labs), or MegaLinter fails with "Fatal error while calling pylint".

### Features

* **megalinter:** drop pylint from four flavors; enable PYTHON_RUFF instead of PYTHON_PYLINT ([#2093](https://github.com/anthony-spruyt/container-images/issues/2093)) ([f288272](https://github.com/anthony-spruyt/container-images/commit/f2882726ec5adb75c7b0981d3d3fca126c8a0777))

## [2.0.3](https://github.com/anthony-spruyt/container-images/compare/megalinter-sungather-2.0.2...megalinter-sungather-2.0.3) (2026-10-04)


### Dependencies

* **megalinter:** weekly linter version refresh ([#2053](https://github.com/anthony-spruyt/container-images/issues/2053)) ([6738ed7](https://github.com/anthony-spruyt/container-images/commit/6738ed797d34076c76350386abfe2eb70c7edb12))

## [2.0.2](https://github.com/anthony-spruyt/container-images/compare/megalinter-sungather-2.0.1...megalinter-sungather-2.0.2) (2026-09-27)


### Dependencies

* **megalinter:** weekly linter version refresh ([#1934](https://github.com/anthony-spruyt/container-images/issues/1934)) ([89cb6c2](https://github.com/anthony-spruyt/container-images/commit/89cb6c2158d4770bd7d84d977450a5297ea60e89))

## [2.0.1](https://github.com/anthony-spruyt/container-images/compare/megalinter-sungather-2.0.0...megalinter-sungather-2.0.1) (2026-09-20)


### Dependencies

* **megalinter:** weekly linter version refresh ([#1871](https://github.com/anthony-spruyt/container-images/issues/1871)) ([1c8d4f7](https://github.com/anthony-spruyt/container-images/commit/1c8d4f7fa3a2a21d4a67dd836874f4db27f7da47))

## [2.0.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-sungather-1.0.21...megalinter-sungather-2.0.0) (2026-09-19)


### ⚠ BREAKING CHANGES

* **megalinter:** MegaLinter v10 removes REPOSITORY_GITLEAKS. Replace it with REPOSITORY_BETTERLEAKS in ENABLE_LINTERS before bumping this image pin, or secret scanning stops without failing.

### Features

* **megalinter:** mark the v10 gitleaks removal as breaking on the four remaining flavors ([#1821](https://github.com/anthony-spruyt/container-images/issues/1821)) ([bc1fa86](https://github.com/anthony-spruyt/container-images/commit/bc1fa860e03b47d184e6a7ebe07896904207812b))

## [1.0.21](https://github.com/anthony-spruyt/container-images/compare/megalinter-sungather-1.0.20...megalinter-sungather-1.0.21) (2026-09-19)


### Dependencies

* **megalinter-sungather:** rebase onto MegaLinter v10.1.0 ([#1793](https://github.com/anthony-spruyt/container-images/issues/1793)) ([dc8056d](https://github.com/anthony-spruyt/container-images/commit/dc8056dc170a823ea3ae81624673d9dbdbb7b1a7))

## [1.0.20](https://github.com/anthony-spruyt/container-images/compare/megalinter-sungather-1.0.19...megalinter-sungather-1.0.20) (2026-09-07)


### Continuous Integration

* **release:** migrate remaining images and retire the old pipeline ([#1460](https://github.com/anthony-spruyt/container-images/issues/1460)) ([7ac4a52](https://github.com/anthony-spruyt/container-images/commit/7ac4a52d2bcb9955fec7073b5e7281f68ba2d28e))
