# Changelog

## [2.1.6](https://github.com/anthony-spruyt/container-images/compare/megalinter-go-2.1.5...megalinter-go-2.1.6) (2026-10-28)


### Dependencies

* **megalinter:** rebuild flavors for updated language definitions ([#2617](https://github.com/anthony-spruyt/container-images/issues/2617)) ([93c4dad](https://github.com/anthony-spruyt/container-images/commit/93c4dadc250ed40e3bbb74a6c6c874bd9d2de544))

## [2.1.5](https://github.com/anthony-spruyt/container-images/compare/megalinter-go-2.1.4...megalinter-go-2.1.5) (2026-10-25)


### Dependencies

* **megalinter:** rebuild flavors for updated language definitions ([#2483](https://github.com/anthony-spruyt/container-images/issues/2483)) ([468feab](https://github.com/anthony-spruyt/container-images/commit/468feab2a47d08c41026e26183c6b9bb98f98b6a))
* **megalinter:** weekly linter version refresh ([#2489](https://github.com/anthony-spruyt/container-images/issues/2489)) ([ad6e86f](https://github.com/anthony-spruyt/container-images/commit/ad6e86f7dc50ff682fc111a4f3fb32f356b65d07))

## [2.1.4](https://github.com/anthony-spruyt/container-images/compare/megalinter-go-2.1.3...megalinter-go-2.1.4) (2026-10-20)


### Dependencies

* **megalinter:** weekly linter version refresh ([#2387](https://github.com/anthony-spruyt/container-images/issues/2387)) ([3ead206](https://github.com/anthony-spruyt/container-images/commit/3ead2066143c1eec4bb6ad05ab464d51ed6cde32))

## [2.1.3](https://github.com/anthony-spruyt/container-images/compare/megalinter-go-2.1.2...megalinter-go-2.1.3) (2026-10-15)


### Dependencies

* **megalinter:** weekly linter version refresh ([#2364](https://github.com/anthony-spruyt/container-images/issues/2364)) ([8be0113](https://github.com/anthony-spruyt/container-images/commit/8be0113ee6b5a43d0469df8cff64477dec88c138))


### Continuous Integration

* **image:** block image job egress to an allowlist ([#2359](https://github.com/anthony-spruyt/container-images/issues/2359)) ([35c8d90](https://github.com/anthony-spruyt/container-images/commit/35c8d9064338427de7bff0f779748cbebfbcd115))

## [2.1.2](https://github.com/anthony-spruyt/container-images/compare/megalinter-go-2.1.1...megalinter-go-2.1.2) (2026-10-14)


### Dependencies

* **megalinter:** weekly linter version refresh ([#2339](https://github.com/anthony-spruyt/container-images/issues/2339)) ([c61b202](https://github.com/anthony-spruyt/container-images/commit/c61b2025a1371018fef988b2345576107d7f4ed6))

## [2.1.1](https://github.com/anthony-spruyt/container-images/compare/megalinter-go-2.1.0...megalinter-go-2.1.1) (2026-10-12)


### Dependencies

* **megalinter:** weekly linter version refresh ([#2249](https://github.com/anthony-spruyt/container-images/issues/2249)) ([29061c3](https://github.com/anthony-spruyt/container-images/commit/29061c3b95c872dc3c552ca6c19ad9864cc17d1d))
* **megalinter:** weekly linter version refresh ([#2281](https://github.com/anthony-spruyt/container-images/issues/2281)) ([bfc19fa](https://github.com/anthony-spruyt/container-images/commit/bfc19fa8b60df78d005aa89e9567382a96fb8b03))

## [2.1.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-go-2.0.0...megalinter-go-2.1.0) (2026-10-09)


### Features

* **megalinter:** add a docker language and compose it into image-building flavors ([#2177](https://github.com/anthony-spruyt/container-images/issues/2177)) ([bafaf0f](https://github.com/anthony-spruyt/container-images/commit/bafaf0f9bf4958725ef01179c45af58154a7ea96))

## [2.0.0](https://github.com/anthony-spruyt/container-images/compare/megalinter-go-1.0.0...megalinter-go-2.0.0) (2026-10-06)


### ⚠ BREAKING CHANGES

* **megalinter:** PYTHON_PYLINT is removed from megalinter-container-images, megalinter-sungather, megalinter-go and megalinter-spruyt-labs. Before bumping the pin, replace PYTHON_PYLINT in ENABLE_LINTERS with PYTHON_RUFF and PYTHON_RUFF_FORMAT (container-images, sungather) or remove it (go, spruyt-labs), or MegaLinter fails with "Fatal error while calling pylint".

### Features

* **megalinter:** drop pylint from four flavors; enable PYTHON_RUFF instead of PYTHON_PYLINT ([#2093](https://github.com/anthony-spruyt/container-images/issues/2093)) ([f288272](https://github.com/anthony-spruyt/container-images/commit/f2882726ec5adb75c7b0981d3d3fca126c8a0777))

## 1.0.0 (2026-10-06)


### Features

* **megalinter:** add megalinter-go and megalinter-python flavors ([#2083](https://github.com/anthony-spruyt/container-images/issues/2083)) ([20a3fa0](https://github.com/anthony-spruyt/container-images/commit/20a3fa0e68c86b53c4ad5eba2b95be27a3d3a454))
