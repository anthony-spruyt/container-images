# Changelog

## [1.2.2](https://github.com/anthony-spruyt/container-images/compare/llm-tool-guard-1.2.1...llm-tool-guard-1.2.2) (2026-10-15)


### Bug Fixes

* **deps:** update dependency fastapi to v0.142.3 ([#2354](https://github.com/anthony-spruyt/container-images/issues/2354)) ([555c23b](https://github.com/anthony-spruyt/container-images/commit/555c23b9b7ce9bf3dfa69085d2f06964a0080635))
* **deps:** update dependency fastapi to v0.142.4 ([#2357](https://github.com/anthony-spruyt/container-images/issues/2357)) ([d116bef](https://github.com/anthony-spruyt/container-images/commit/d116bef5469e0b411385cd4b87f2ccf408debbaa))
* **test:** read docker logs before grep -q under pipefail ([#2362](https://github.com/anthony-spruyt/container-images/issues/2362)) ([9b0ec83](https://github.com/anthony-spruyt/container-images/commit/9b0ec8376da28bcfa8d5f9805ac4606596e46581))


### Continuous Integration

* **image:** block image job egress to an allowlist ([#2359](https://github.com/anthony-spruyt/container-images/issues/2359)) ([35c8d90](https://github.com/anthony-spruyt/container-images/commit/35c8d9064338427de7bff0f779748cbebfbcd115))

## [1.2.1](https://github.com/anthony-spruyt/container-images/compare/llm-tool-guard-1.2.0...llm-tool-guard-1.2.1) (2026-10-14)


### Bug Fixes

* install the guard images from uv lock files ([#2331](https://github.com/anthony-spruyt/container-images/issues/2331)) ([288db27](https://github.com/anthony-spruyt/container-images/commit/288db27601b69de63709c965508f6814a7d7ac26))

## [1.2.0](https://github.com/anthony-spruyt/container-images/compare/llm-tool-guard-1.1.1...llm-tool-guard-1.2.0) (2026-10-14)


### Features

* **llm-tool-guard-model:** ship the scanner model as its own weights image ([19739df](https://github.com/anthony-spruyt/container-images/commit/19739dfc09ff29f7c7c0445c937b0a68f4e27d9e))

## [1.1.1](https://github.com/anthony-spruyt/container-images/compare/llm-tool-guard-1.1.0...llm-tool-guard-1.1.1) (2026-10-12)


### Dependencies

* **deps:** update dependency pydantic to v2.14.1 ([#2288](https://github.com/anthony-spruyt/container-images/issues/2288)) ([70d09fb](https://github.com/anthony-spruyt/container-images/commit/70d09fb1a7b2763d6991f1a3f6460f02f246adc8))
* **deps:** update dependency transformers to v5.19.0 ([#2289](https://github.com/anthony-spruyt/container-images/issues/2289)) ([cb2e99f](https://github.com/anthony-spruyt/container-images/commit/cb2e99f2e69d996f8862544102bcd1f75e49e659))
* **deps:** update torch (cpu + cuda) ([#2291](https://github.com/anthony-spruyt/container-images/issues/2291)) ([810c332](https://github.com/anthony-spruyt/container-images/commit/810c3320a7265f17b2a2ca4e6eb22f8f4188c8bf))

## [1.1.0](https://github.com/anthony-spruyt/container-images/compare/llm-tool-guard-1.0.0...llm-tool-guard-1.1.0) (2026-10-10)


### Features

* **llm-tool-guard:** version-scoped cache keys, request cap, scan time budget, drain on shutdown ([#2270](https://github.com/anthony-spruyt/container-images/issues/2270)) ([bd484c0](https://github.com/anthony-spruyt/container-images/commit/bd484c0f6da1ef2e4c1d34e9d20151051ee80085))

## 1.0.0 (2026-10-10)


### Features

* **llm-tool-guard:** add tool-result prompt-injection scanner ([93d83dc](https://github.com/anthony-spruyt/container-images/commit/93d83dcceec75913dfb61bd43a071423771d5e2f))
