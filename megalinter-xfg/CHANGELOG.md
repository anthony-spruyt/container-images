# Changelog

## [2.0.1](https://github.com/anthony-spruyt/container-images/compare/megalinter-xfg-v2.0.0...megalinter-xfg-v2.0.1) (2026-09-19)


### Bug Fixes

* **megalinter-xfg:** install globals for eslint flat config ([#1861](https://github.com/anthony-spruyt/container-images/issues/1861)) ([ba43dc9](https://github.com/anthony-spruyt/container-images/commit/ba43dc9a40c60b4da58afef3d7b6083496701973))

## [2.0.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-xfg-v1.0.47...megalinter-xfg-v2.0.0) (2026-09-19)


### ⚠ BREAKING CHANGES

* **megalinter:** MegaLinter v10 removes REPOSITORY_GITLEAKS. Replace it with REPOSITORY_BETTERLEAKS in ENABLE_LINTERS before bumping this image pin, or secret scanning stops without failing.

### Features

* **megalinter:** mark the v10 gitleaks removal as breaking on the four remaining flavors ([#1821](https://github.com/anthony-spruyt/container-images/issues/1821)) ([bc1fa86](https://github.com/anthony-spruyt/container-images/commit/bc1fa860e03b47d184e6a7ebe07896904207812b))

## [1.0.47](https://github.com/anthony-spruyt/container-images/compare/megalinter-xfg-v1.0.46...megalinter-xfg-v1.0.47) (2026-09-19)


### Dependencies

* **megalinter-xfg:** rebase onto MegaLinter v10.1.0 ([#1790](https://github.com/anthony-spruyt/container-images/issues/1790)) ([ea23db3](https://github.com/anthony-spruyt/container-images/commit/ea23db3442ed8b4a0a797bb4beadd60e5f1e7947))

## [1.0.46](https://github.com/anthony-spruyt/container-images/compare/megalinter-xfg-v1.0.45...megalinter-xfg-v1.0.46) (2026-09-07)


### Continuous Integration

* **release:** migrate remaining images and retire the old pipeline ([#1460](https://github.com/anthony-spruyt/container-images/issues/1460)) ([7ac4a52](https://github.com/anthony-spruyt/container-images/commit/7ac4a52d2bcb9955fec7073b5e7281f68ba2d28e))
