"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const script = path.join(__dirname, "dependency-floors.cjs");
const floors = ["eff=2.0.0", "zod=4.6.6"];

function tree({ overrides, zod = "^4.0.0", asks = "1.0.0", eff = "1.0.0" } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "floors-"));
  const write = (dir, manifest) => {
    fs.mkdirSync(path.join(root, dir), { recursive: true });
    fs.writeFileSync(path.join(root, dir, "package.json"), JSON.stringify(manifest));
  };
  write("", { name: "fx", dependencies: { a: "^1.0.0", zod }, overrides });
  write("node_modules/a", { name: "a", version: "1.0.0", dependencies: { eff: asks } });
  write("node_modules/eff", { name: "eff", version: eff });
  write("node_modules/zod", { name: "zod", version: "4.6.7" });
  return root;
}

const run = (mode, root) => spawnSync(process.execPath, [script, mode, root, ...floors], { encoding: "utf8" });
const manifest = (root) => JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));

test("apply raises a direct range that allows below the floor and overrides a copy below it", () => {
  const root = tree({ overrides: { keep: "1.0.0" } });
  const result = run("apply", root);
  assert.equal(result.status, 0, result.stderr);
  const { dependencies, overrides } = manifest(root);
  assert.equal(dependencies.zod, "^4.6.6");
  assert.equal(dependencies.a, "^1.0.0");
  assert.deepEqual(overrides, { keep: "1.0.0", a: { eff: "^2.0.0" } });
});

test("apply leaves ranges and copies that already meet the floors", () => {
  const root = tree({ zod: "^4.6.6", asks: "^2.1.0", eff: "2.1.3" });
  const before = fs.readFileSync(path.join(root, "package.json"), "utf8");
  const result = run("apply", root);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.readFileSync(path.join(root, "package.json"), "utf8"), before);
});

test("apply keeps an upstream override that already meets the floor", () => {
  const root = tree({ overrides: { eff: "^2.5.0" } });
  const result = run("apply", root);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(manifest(root).overrides, { eff: "^2.5.0" });
});

for (const overrides of [{ eff: "^1.0.0" }, { a: { eff: "^1.0.0" } }, { eff: "$eff" }, { a: "1.0.0" }]) {
  test(`apply fails on a conflicting upstream override ${JSON.stringify(overrides)}`, () => {
    const root = tree({ overrides });
    const before = fs.readFileSync(path.join(root, "package.json"), "utf8");
    const result = run("apply", root);
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /eff/);
    assert.equal(fs.readFileSync(path.join(root, "package.json"), "utf8"), before);
  });
}

test("check passes when every copy meets its floor and its dependents' ranges", () => {
  const result = run("check", tree({ zod: "^4.6.6", asks: "^1.0.0", eff: "2.0.0" }));
  assert.equal(result.status, 0, result.stderr);
});

test("check fails on a copy below its floor", () => {
  const result = run("check", tree({ eff: "1.0.0" }));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /eff@1\.0\.0/);
});

test("check fails when a dependent asks for more than is installed", () => {
  const result = run("check", tree({ asks: "^3.0.0", eff: "2.0.0" }));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /a asks for eff@\^3\.0\.0 but 2\.0\.0 is installed/);
});
