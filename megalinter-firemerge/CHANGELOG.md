# Changelog

## [2.0.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-firemerge-1.0.21...megalinter-firemerge-2.0.0) (2026-09-19)


### ⚠ BREAKING CHANGES

* **megalinter:** MegaLinter v10 removes REPOSITORY_GITLEAKS. Replace it with REPOSITORY_BETTERLEAKS in ENABLE_LINTERS before bumping this image pin, or secret scanning stops without failing.

### Features

* **megalinter:** mark the v10 gitleaks removal as breaking on the four remaining flavors ([#1821](https://github.com/anthony-spruyt/container-images/issues/1821)) ([bc1fa86](https://github.com/anthony-spruyt/container-images/commit/bc1fa860e03b47d184e6a7ebe07896904207812b))

## [1.0.21](https://github.com/anthony-spruyt/container-images/compare/megalinter-firemerge-1.0.20...megalinter-firemerge-1.0.21) (2026-09-19)


### Dependencies

* **megalinter-firemerge:** rebase onto MegaLinter v10.1.0 ([#1792](https://github.com/anthony-spruyt/container-images/issues/1792)) ([567180a](https://github.com/anthony-spruyt/container-images/commit/567180a0023b43337a8cd4cf358b613b544f4f63))

## [1.0.20](https://github.com/anthony-spruyt/container-images/compare/megalinter-firemerge-1.0.19...megalinter-firemerge-1.0.20) (2026-09-07)


### Continuous Integration

* **release:** migrate remaining images and retire the old pipeline ([#1460](https://github.com/anthony-spruyt/container-images/issues/1460)) ([7ac4a52](https://github.com/anthony-spruyt/container-images/commit/7ac4a52d2bcb9955fec7073b5e7281f68ba2d28e))
