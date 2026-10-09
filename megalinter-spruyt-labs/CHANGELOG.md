# Changelog

## [3.1.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v3.0.0...megalinter-spruyt-labs-v3.1.0) (2026-10-09)


### Features

* **megalinter:** add a docker language and compose it into image-building flavors ([#2177](https://github.com/anthony-spruyt/container-images/issues/2177)) ([bafaf0f](https://github.com/anthony-spruyt/container-images/commit/bafaf0f9bf4958725ef01179c45af58154a7ea96))


### Dependencies

* **deps:** update dependency @biomejs/biome to v2.5.15 ([#2190](https://github.com/anthony-spruyt/container-images/issues/2190)) ([0c3e6da](https://github.com/anthony-spruyt/container-images/commit/0c3e6dab855f0b8343efb3fddb2268868c135444))

## [3.0.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v2.0.4...megalinter-spruyt-labs-v3.0.0) (2026-10-06)


### ⚠ BREAKING CHANGES

* **megalinter:** PYTHON_PYLINT is removed from megalinter-container-images, megalinter-sungather, megalinter-go and megalinter-spruyt-labs. Before bumping the pin, replace PYTHON_PYLINT in ENABLE_LINTERS with PYTHON_RUFF and PYTHON_RUFF_FORMAT (container-images, sungather) or remove it (go, spruyt-labs), or MegaLinter fails with "Fatal error while calling pylint".

### Features

* **megalinter:** drop pylint from four flavors; enable PYTHON_RUFF instead of PYTHON_PYLINT ([#2093](https://github.com/anthony-spruyt/container-images/issues/2093)) ([f288272](https://github.com/anthony-spruyt/container-images/commit/f2882726ec5adb75c7b0981d3d3fca126c8a0777))

## [2.0.4](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v2.0.3...megalinter-spruyt-labs-v2.0.4) (2026-10-04)


### Dependencies

* **megalinter:** weekly linter version refresh ([#2053](https://github.com/anthony-spruyt/container-images/issues/2053)) ([6738ed7](https://github.com/anthony-spruyt/container-images/commit/6738ed797d34076c76350386abfe2eb70c7edb12))

## [2.0.3](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v2.0.2...megalinter-spruyt-labs-v2.0.3) (2026-09-27)


### Dependencies

* **megalinter:** weekly linter version refresh ([#1934](https://github.com/anthony-spruyt/container-images/issues/1934)) ([89cb6c2](https://github.com/anthony-spruyt/container-images/commit/89cb6c2158d4770bd7d84d977450a5297ea60e89))

## [2.0.2](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v2.0.1...megalinter-spruyt-labs-v2.0.2) (2026-09-26)


### Dependencies

* **deps:** update dependency @biomejs/biome to v2.5.14 ([#1913](https://github.com/anthony-spruyt/container-images/issues/1913)) ([d7fe4a9](https://github.com/anthony-spruyt/container-images/commit/d7fe4a9505a131912dfd2d51d2fcb9c6f4c7a798))

## [2.0.1](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v2.0.0...megalinter-spruyt-labs-v2.0.1) (2026-09-20)


### Dependencies

* **megalinter:** weekly linter version refresh ([#1871](https://github.com/anthony-spruyt/container-images/issues/1871)) ([1c8d4f7](https://github.com/anthony-spruyt/container-images/commit/1c8d4f7fa3a2a21d4a67dd836874f4db27f7da47))

## [2.0.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v1.0.40...megalinter-spruyt-labs-v2.0.0) (2026-09-19)


### ⚠ BREAKING CHANGES

* **megalinter:** MegaLinter v10 removes REPOSITORY_GITLEAKS. Replace it with REPOSITORY_BETTERLEAKS in ENABLE_LINTERS before bumping this image pin, or secret scanning stops without failing.

### Features

* **megalinter:** mark the v10 gitleaks removal as breaking on the four remaining flavors ([#1821](https://github.com/anthony-spruyt/container-images/issues/1821)) ([bc1fa86](https://github.com/anthony-spruyt/container-images/commit/bc1fa860e03b47d184e6a7ebe07896904207812b))

## [1.0.40](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v1.0.39...megalinter-spruyt-labs-v1.0.40) (2026-09-19)


### Dependencies

* **megalinter-spruyt-labs:** rebase onto MegaLinter v10.1.0 ([#1789](https://github.com/anthony-spruyt/container-images/issues/1789)) ([38acb56](https://github.com/anthony-spruyt/container-images/commit/38acb565ff31f0c34f004f2eb88dd5da28058602))

## [1.0.39](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v1.0.38...megalinter-spruyt-labs-v1.0.39) (2026-09-18)


### Dependencies

* **deps:** update dependency @biomejs/biome to v2.5.13 ([#1740](https://github.com/anthony-spruyt/container-images/issues/1740)) ([044ee69](https://github.com/anthony-spruyt/container-images/commit/044ee69c55776dceccdefd09d1c33c4e8f5bf066))

## [1.0.38](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v1.0.37...megalinter-spruyt-labs-v1.0.38) (2026-09-07)


### Dependencies

* **deps:** update dependency @biomejs/biome to v2.5.12 ([#1564](https://github.com/anthony-spruyt/container-images/issues/1564)) ([a6ac8bb](https://github.com/anthony-spruyt/container-images/commit/a6ac8bb8114343fb791bb7121dcb44525242a4ad))

## [1.0.37](https://github.com/anthony-spruyt/container-images/compare/megalinter-spruyt-labs-v1.0.36...megalinter-spruyt-labs-v1.0.37) (2026-09-07)


### Continuous Integration

* **release:** migrate remaining images and retire the old pipeline ([#1460](https://github.com/anthony-spruyt/container-images/issues/1460)) ([7ac4a52](https://github.com/anthony-spruyt/container-images/commit/7ac4a52d2bcb9955fec7073b5e7281f68ba2d28e))
