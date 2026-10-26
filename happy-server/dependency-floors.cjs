"use strict";
// Usage: node dependency-floors.cjs apply|check <package dir> <name>=<floor>...
const fs = require("node:fs");
const path = require("node:path");

const [mode, root, ...specs] = process.argv.slice(2);
const floors = new Map(
  specs.map((spec) => [spec.slice(0, spec.lastIndexOf("=")), spec.slice(spec.lastIndexOf("=") + 1)])
);
const semverPaths = [root, "/usr/local/lib/node_modules/npm/node_modules", process.cwd()].filter(Boolean);
const semver = require(require.resolve("semver", { paths: semverPaths }));

const DEP_KINDS = ["dependencies", "optionalDependencies"];

function readManifest(dir) {
  const file = path.join(dir, "package.json");
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : null;
}

// lookup lists the node_modules directories a package resolves from, nearest first.
function* installed(dir, lookup) {
  const modules = path.join(dir, "node_modules");
  if (!fs.existsSync(modules)) return;
  for (const entry of fs.readdirSync(modules)) {
    if (entry.startsWith(".")) continue;
    const names = entry.startsWith("@")
      ? fs.readdirSync(path.join(modules, entry)).map((name) => `${entry}/${name}`)
      : [entry];
    for (const name of names) {
      const pkgDir = path.join(modules, name);
      const manifest = readManifest(pkgDir);
      if (!manifest) continue;
      const own = [path.join(pkgDir, "node_modules"), ...lookup];
      yield { name, dir: pkgDir, manifest, lookup: own };
      yield* installed(pkgDir, own);
    }
  }
}

function* packages() {
  const lookup = [path.join(root, "node_modules")];
  yield { name: readManifest(root).name, dir: root, manifest: readManifest(root), lookup };
  yield* installed(root, lookup);
}

function copyOf(pkg, dep) {
  for (const modules of pkg.lookup) {
    const manifest = readManifest(path.join(modules, dep));
    if (manifest) return manifest;
  }
  return null;
}

function edges(pkg) {
  return DEP_KINDS.flatMap((kind) => Object.entries(pkg.manifest[kind] ?? {})).filter(([dep]) => floors.has(dep));
}

const allowsBelow = (range, floor) => semver.validRange(range) !== null && !semver.subset(range, `>=${floor}`);

function raiseDirectRanges(manifest) {
  const changes = [];
  for (const [dep, floor] of floors) {
    const range = manifest.dependencies?.[dep];
    if (range !== undefined && allowsBelow(range, floor)) {
      manifest.dependencies[dep] = `^${floor}`;
      changes.push(`${dep}: dependency range ${range} -> ^${floor}`);
    }
  }
  return changes;
}

function upstreamHoldsFloor(upstream, dep, floor) {
  if (upstream === undefined) return false;
  if (typeof upstream === "string" && semver.validRange(upstream) && !allowsBelow(upstream, floor)) return true;
  throw new Error(
    `the ${dep} floor ${floor} conflicts with the upstream override ${JSON.stringify(upstream)}; drop the floor or reconcile the override`
  );
}

function nestOverride(overrides, pkg, dep, floor) {
  const copy = copyOf(pkg, dep);
  if (!copy || semver.gte(copy.version, floor)) return null;
  if (upstreamHoldsFloor(overrides[dep] ?? overrides[pkg.name]?.[dep], dep, floor)) return null;
  if (typeof overrides[pkg.name] === "string") {
    throw new TypeError(`upstream overrides ${pkg.name} itself, so the ${dep} floor cannot be nested under it`);
  }
  overrides[pkg.name] = { ...overrides[pkg.name], [dep]: `^${floor}` };
  return `${pkg.name} > ${dep}: override ^${floor} (was ${copy.version})`;
}

function nestOverrides(overrides) {
  const changes = [];
  for (const pkg of packages()) {
    if (pkg.dir === root) continue;
    for (const [dep] of edges(pkg)) {
      const change = nestOverride(overrides, pkg, dep, floors.get(dep));
      if (change) changes.push(change);
    }
  }
  return changes;
}

function apply() {
  const manifest = readManifest(root);
  const overrides = manifest.overrides ?? {};
  const changes = [...raiseDirectRanges(manifest), ...nestOverrides(overrides)];

  if (Object.keys(overrides).length > 0) manifest.overrides = overrides;
  if (changes.length > 0) {
    fs.writeFileSync(path.join(root, "package.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  }
  console.log(changes.length > 0 ? changes.join("\n") : "upstream already meets every floor");
}

function check() {
  const problems = [];
  for (const pkg of packages()) {
    const floor = floors.get(pkg.name);
    if (floor && pkg.dir !== root && semver.lt(pkg.manifest.version, floor)) {
      problems.push(`${pkg.name}@${pkg.manifest.version} in ${path.relative(root, pkg.dir)} is below its floor ${floor}`);
    }
    for (const [dep, range] of edges(pkg)) {
      const copy = copyOf(pkg, dep);
      if (copy && semver.validRange(range) && semver.lt(copy.version, semver.minVersion(range))) {
        problems.push(`${pkg.name} asks for ${dep}@${range} but ${copy.version} is installed`);
      }
    }
  }
  if (problems.length > 0) throw new Error(problems.join("\n"));
  console.log("ok");
}

try {
  if (!["apply", "check"].includes(mode) || !root || floors.size === 0) {
    throw new Error("usage: dependency-floors.cjs apply|check <package dir> <name>=<floor>...");
  }
  for (const [dep, floor] of floors) {
    if (!semver.valid(floor)) throw new Error(`${dep} floor ${JSON.stringify(floor)} is not a version`);
  }
  (mode === "apply" ? apply : check)();
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
