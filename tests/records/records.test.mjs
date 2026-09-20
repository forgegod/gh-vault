import { test } from "node:test";
import assert from "node:assert/strict";
import { validateRecords } from "../../scripts/check-product-records.mjs";
import {
  addFixtureFile,
  createFixtureTree,
  patchFixture,
} from "./fixtures.mjs";

function errorsFor(root) {
  return validateRecords(root).then((result) => result.errors);
}

test("a valid fixture tree passes without errors", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    const result = await validateRecords(root);
    assert.deepEqual(result.errors, []);
    assert.equal(result.capabilities, 1);
    assert.equal(result.changes, 0);
    assert.equal(result.manifest, false);
  } finally {
    cleanup();
  }
});

test("a CAP missing the Behaviour section fails", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    patchFixture(
      root,
      "docs/product/capabilities/CAP-001-fixture-capability.md",
      "",
      "## Behaviour\n\n- The fixture engine runs.\n\n",
    );
    const errors = await errorsFor(root);
    assert.ok(
      errors.some((error) =>
        error.includes("must include a Behaviour section"),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});

test("an invalid capability status fails", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    patchFixture(
      root,
      "docs/product/capabilities/CAP-001-fixture-capability.md",
      "**Status:** shipped",
      "**Status:** implemented",
    );
    const errors = await errorsFor(root);
    assert.ok(
      errors.some((error) =>
        error.includes("has invalid capability status"),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});

test("a missing implementation file fails", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    patchFixture(
      root,
      "docs/product/capabilities/CAP-001-fixture-capability.md",
      "`src/other.mjs`",
      "`src/engine.mjs`",
    );
    const errors = await errorsFor(root);
    assert.ok(
      errors.some((error) =>
        error.includes("references missing implementation file: src/other.mjs"),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});

test("a CAP without a behaviour-test reference fails", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    patchFixture(
      root,
      "docs/product/capabilities/CAP-001-fixture-capability.md",
      "",
      "- `src/engine.test.mjs` — proves the fixture engine runs.\n\n",
    );
    const errors = await errorsFor(root);
    assert.ok(
      errors.some((error) =>
        error.includes("must reference at least one executable behaviour test"),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});

test("a missing behaviour-test file fails", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    patchFixture(
      root,
      "docs/product/capabilities/CAP-001-fixture-capability.md",
      "`src/missing.test.mjs`",
      "`src/engine.test.mjs`",
    );
    const errors = await errorsFor(root);
    assert.ok(
      errors.some((error) =>
        error.includes("references missing behaviour test: src/missing.test.mjs"),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});

test("a CAP duplicated by a second file with the same ID fails", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    addFixtureFile(
      root,
      "docs/product/capabilities/CAP-001-second-slug.md",
      `# CAP-001 — Duplicate capability\n\n**Status:** implemented\n\n## Behaviour\n\n- Nothing.\n\n## Implementation\n\n- \`src/engine.mjs\` — fixture engine.\n\n## Verification\n\n- \`src/engine.test.mjs\` — proves the fixture engine runs.\n`,
    );
    const errors = await errorsFor(root);
    assert.ok(
      errors.some((error) =>
        error.includes("duplicates capability ID CAP-001"),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});

test("a CAP not linked from docs/product/index.md fails", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    patchFixture(
      root,
      "docs/product/index.md",
      "# Capability index\n",
      "# Capability index\n\n- [CAP-001 — Fixture capability](capabilities/CAP-001-fixture-capability.md)\n",
    );
    const errors = await errorsFor(root);
    assert.ok(
      errors.some((error) =>
        error.includes("docs/product/index.md must link CAP-001"),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});

test("a broken local Markdown link inside a CAP fails", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    patchFixture(
      root,
      "docs/product/capabilities/CAP-001-fixture-capability.md",
      "[Architecture](../../missing.md)",
      "[Architecture](../../architecture.md)",
    );
    const errors = await errorsFor(root);
    assert.ok(
      errors.some((error) =>
        error.includes("has broken local link: ../../missing.md"),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});
