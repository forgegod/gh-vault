/**
 * Python pytest evidence-recognition regression suite.
 *
 * The validator's Verification test-evidence filter recognises:
 *   - `*.test.{c,m}{j,t}s?` and `*.spec.{c,m}{j,t}s?` (existing JS/TS forms),
 *   - `test_*.py` and `*_test.py` (added Python pytest forms).
 *
 * These tests pin that contract. Positive tests assert that each Python form
 * is accepted when the file exists; missing-evidence tests assert that a CAP
 * pointing at a real Python file but with no recognised shape still fails;
 * invalid-evidence tests assert that arbitrary `.py` paths are NOT treated as
 * executable behaviour evidence and that missing files still fail.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { rmSync } from "node:fs";
import path from "node:path";
import { validateRecords } from "../../scripts/check-product-records.mjs";
import {
  addPythonCapability,
  createFixtureTree,
  patchFixture,
} from "./fixtures.mjs";

const pythonCap =
  "docs/product/capabilities/CAP-002-python-evidence-capability.md";

function errorsFor(root) {
  return validateRecords(root).then((result) => result.errors);
}

test("accepts a CAP with a `test_*.py` evidence path", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    addPythonCapability(root, {
      relative: pythonCap,
      testPath: "tests/test_fixture.py",
    });
    const result = await validateRecords(root);
    assert.deepEqual(result.errors, []);
    assert.equal(result.capabilities, 2);
  } finally {
    cleanup();
  }
});

test("accepts a CAP with a `*_test.py` evidence path", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    addPythonCapability(root, {
      relative: pythonCap,
      testPath: "tests/fixture_test.py",
    });
    const result = await validateRecords(root);
    assert.deepEqual(result.errors, []);
    assert.equal(result.capabilities, 2);
  } finally {
    cleanup();
  }
});

test("accepts nested `tests/test_*.py` and `tests/*_test.py` paths", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    addPythonCapability(root, {
      relative: pythonCap,
      testPath: "tests/records/test_validator.py",
    });
    const result = await validateRecords(root);
    assert.deepEqual(result.errors, []);
  } finally {
    cleanup();
  }
});

test("rejects a Python evidence file that does not exist", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    addPythonCapability(root, {
      relative: pythonCap,
      testPath: "tests/test_fixture.py",
    });
    rmSync(path.join(root, "tests", "test_fixture.py"));
    const errors = await errorsFor(root);
    assert.ok(
      errors.some((error) =>
        error.includes(
          "references missing behaviour test: tests/test_fixture.py",
        ),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});

test("rejects a CAP whose Verification references no executable evidence", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    addPythonCapability(root, {
      relative: pythonCap,
      testPath: "tests/test_fixture.py",
    });
    patchFixture(
      root,
      pythonCap,
      "",
      "- `tests/test_fixture.py` — proves the fixture Python module runs.\n\n",
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

test("does not accept an arbitrary `.py` path as behaviour evidence", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    addPythonCapability(root, {
      relative: pythonCap,
      testPath: "tests/test_fixture.py",
    });
    // Replace the recognised `test_*.py` reference with a plain module path
    // that is NOT in either pytest pattern. The file exists, so the failure
    // must come from the evidence-shape filter, not the missing-file check.
    patchFixture(
      root,
      pythonCap,
      "- `src/fixture_target.py` — replaces the test reference.",
      "- `tests/test_fixture.py` — proves the fixture Python module runs.",
    );
    const errors = await errorsFor(root);
    assert.ok(
      errors.some((error) =>
        error.includes("must reference at least one executable behaviour test"),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
    // Crucially, the non-pytest `.py` path must NOT have been promoted to
    // evidence; otherwise the suite would silently broaden what the validator
    // accepts.
    assert.ok(
      !errors.some((error) =>
        error.includes("references missing behaviour test: src/fixture_target.py"),
      ),
      `unexpected behaviour-test reference: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});

test("does not accept `.spec.py` or `.test.py` (the JS suffix patterns do not extend)", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    addPythonCapability(root, {
      relative: pythonCap,
      testPath: "tests/test_fixture.py",
    });
    patchFixture(
      root,
      pythonCap,
      [
        "- `tests/fixture.spec.py` — not a pytest convention.",
        "- `tests/fixture.test.py` — not a pytest convention.",
      ].join("\n"),
      "- `tests/test_fixture.py` — proves the fixture Python module runs.",
    );
    const errors = await errorsFor(root);
    // The two non-pytest paths must be rejected as evidence; only the missing
    // reference for the real pytest form should remain after the patch.
    assert.ok(
      errors.some((error) =>
        error.includes("must reference at least one executable behaviour test"),
      ),
      `errors were: ${errors.join(" | ")}`,
    );
    assert.ok(
      !errors.some((error) =>
        error.includes("references missing behaviour test: tests/fixture.spec.py"),
      ),
      `unexpected behaviour-test reference for spec.py: ${errors.join(" | ")}`,
    );
    assert.ok(
      !errors.some((error) =>
        error.includes("references missing behaviour test: tests/fixture.test.py"),
      ),
      `unexpected behaviour-test reference for test.py: ${errors.join(" | ")}`,
    );
  } finally {
    cleanup();
  }
});

test("lifecycle and surface gates still apply to a Python-evidence CAP", async () => {
  const { root, cleanup } = createFixtureTree();
  try {
    addPythonCapability(root, {
      relative: pythonCap,
      testPath: "tests/test_fixture.py",
    });
    // An invalid status must still fail, proving the lifecycle gate is not
    // weakened by the evidence-recognition widening.
    patchFixture(
      root,
      pythonCap,
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
