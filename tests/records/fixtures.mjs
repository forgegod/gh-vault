/**
 * Fixture-tree builders for the record-validator behaviour tests.
 *
 * Each builder writes a minimal record tree under a fresh `node:os` tmpdir and
 * returns `{ root, cleanup }`. The default tree is valid; the mutation helpers
 * make one targeted break so a test can assert the matching error.
 *
 * The default fixture tree satisfies the blueprint's record contract:
 * one CAP with a valid Implementation reference (`src/engine.mjs`) and a valid
 * Verification reference (`src/engine.test.mjs`). The Python-evidence
 * fixtures layer additional CAPs that point at `test_*.py` / `*_test.py`
 * files instead, so the suite proves the wider evidence recognition without
 * weakening the lifecycle, review, or wireframe gates.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/** A minimal valid record tree plus the files a CAP references. */
export function buildValidTree(root) {
  fs.mkdirSync(path.join(root, "src"), { recursive: true });
  fs.writeFileSync(
    path.join(root, "src", "engine.mjs"),
    "export const engine = 'fixture';\n",
  );
  fs.writeFileSync(
    path.join(root, "src", "engine.test.mjs"),
    "export const test = true;\n",
  );

  const product = path.join(root, "docs", "product");
  const changes = path.join(root, "docs", "changes");
  fs.mkdirSync(path.join(product, "capabilities"), { recursive: true });
  fs.mkdirSync(path.join(path.join(changes, "active")), { recursive: true });
  fs.mkdirSync(path.join(path.join(changes, "archive")), { recursive: true });

  write(
    root,
    "docs/product/README.md",
    `# Product capability records\n\n## CAP shape\n\nSee the template.\n`,
  );
  write(
    root,
    "docs/product/index.md",
    `# Capability index\n\n- [CAP-001 — Fixture capability](capabilities/CAP-001-fixture-capability.md)\n`,
  );
  write(
    root,
    "docs/product/capabilities/CAP-001-fixture-capability.md",
    `# CAP-001 — Fixture capability\n\n**Status:** implemented\n**Primary surface:** none\n\n## Behaviour\n\n- The fixture engine runs.\n\n## Implementation\n\n- \`src/engine.mjs\` — fixture engine.\n\n## Verification\n\n- \`src/engine.test.mjs\` — proves the fixture engine runs.\n\n## Related contracts\n\n- [Architecture](../../architecture.md)\n`,
  );
  write(
    root,
    "docs/changes/README.md",
    `# Change records\n\nLifecycle rules live in this file.\n`,
  );
  write(
    root,
    "docs/architecture.md",
    `# Architecture\n\nFixture tree contract.\n`,
  );

  return { root };
}

/** @param {string} root @param {string} relative @param {string} content */
function write(root, relative, content) {
  const target = path.join(root, relative);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, content);
}

/**
 * Create a tmpdir with a valid tree and return it plus cleanup.
 *
 * @returns {{root: string, cleanup: () => void}}
 */
export function createFixtureTree() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "gh-vault-records-"));
  buildValidTree(root);
  return {
    root,
    cleanup: () => fs.rmSync(root, { recursive: true, force: true }),
  };
}

/**
 * Mutate a fixture file.
 *
 * @param {string} root
 * @param {string} relative
 * @param {string} replacement
 * @param {string} [match] when given, replaces the first occurrence of `match`
 */
export function patchFixture(root, relative, replacement, match) {
  const target = path.join(root, relative);
  const source = fs.readFileSync(target, "utf8");
  if (match === undefined) {
    fs.writeFileSync(target, replacement);
    return;
  }
  fs.writeFileSync(target, source.replace(match, replacement));
}

/** @param {string} root @param {string} relative @param {string} content */
export function addFixtureFile(root, relative, content) {
  write(root, relative, content);
}

/**
 * Add a second CAP whose Verification references a Python pytest test file.
 *
 * The CAP keeps the same lifecycle, surface, and review discipline as the
 * default fixture; only the Verification evidence path changes. This keeps
 * the Python-evidence regression tests focused on the recognition rule.
 *
 * @param {string} root
 * @param {{relative: string, testPath: string}} options
 */
export function addPythonCapability(root, { relative, testPath }) {
  fs.mkdirSync(path.dirname(path.join(root, relative)), { recursive: true });
  fs.writeFileSync(
    path.join(root, relative),
    [
      `# CAP-002 — Python evidence capability`,
      ``,
      `**Status:** implemented`,
      `**Primary surface:** none`,
      ``,
      `## Behaviour`,
      ``,
      `- The fixture Python module runs.`,
      ``,
      `## Implementation`,
      ``,
      `- \`src/fixture_target.py\` — Python implementation under test.`,
      ``,
      `## Verification`,
      ``,
      `- \`${testPath}\` — proves the fixture Python module runs.`,
      ``,
      `## Related contracts`,
      ``,
      `- [Architecture](../../architecture.md)`,
      ``,
    ].join("\n"),
  );
  addFixtureFile(root, testPath, "# placeholder; never executed\n");
  addFixtureFile(
    root,
    "docs/product/index.md",
    `# Capability index\n\n- [CAP-001 — Fixture capability](capabilities/CAP-001-fixture-capability.md)\n- [CAP-002 — Python evidence capability](capabilities/CAP-002-python-evidence-capability.md)\n`,
  );
  fs.mkdirSync(path.dirname(path.join(root, "src", "fixture_target.py")), {
    recursive: true,
  });
  fs.writeFileSync(
    path.join(root, "src", "fixture_target.py"),
    "# placeholder; never executed\n",
  );
}
