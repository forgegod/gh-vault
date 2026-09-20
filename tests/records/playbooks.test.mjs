import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = fileURLToPath(new URL('../../', import.meta.url));
const read = (relative) => readFileSync(path.join(root, relative), 'utf8');
const family = [
  'application-records',
  'capability-wireframes',
  'phased-plan-design',
  'phased-plan-execution',
  'phased-plan-overview',
  'phased-plan-refactoring',
];

test('repository packages the indexed product-record playbook family', () => {
  const index = read('skills/software-development/AGENTS.md');
  for (const name of family) {
    const relative = `skills/software-development/${name}/SKILL.md`;
    const content = read(relative);
    assert.match(content, new RegExp(`^---\\nname: ${name}\\n`));
    assert.match(content, /\nversion: \S+/);
    assert.match(content, /docs\/changes/);
    assert.ok(index.includes(`${name}/SKILL.md`), `${name} is indexed`);
    assert.doesNotMatch(content, /pnpm (?:test|records:check)/);
  }
});

test('repository maintenance gate stays separate from the Python runtime', () => {
  const makefile = read('Makefile');
  const ci = read('.github/workflows/ci.yml');
  assert.match(makefile, /verify: records-check test/);
  assert.match(makefile, /run --no-project --with pytest python -m pytest/);
  assert.match(makefile, /--test "tests\/records\/\*\.test\.mjs"/);
  assert.match(ci, /run: make verify/);
  assert.match(ci, /contents: read/);
  assert.match(ci, /persist-credentials: false/);
  assert.doesNotMatch(ci, /secrets\.|id-token: write/);
  assert.doesNotMatch(read('pyproject.toml'), /^dependencies\s*=/m);
});

test('CAP pytest assertion names resolve in their referenced test files', () => {
  const directory = 'docs/product/capabilities';
  let references = 0;
  for (const file of readdirSync(path.join(root, directory)).filter((name) => /^CAP-.*\.md$/.test(name))) {
    const content = read(`${directory}/${file}`);
    const verification = content.split('## Verification')[1]?.split('\n## ')[0] ?? '';
    const testPaths = [...verification.matchAll(/`(tests\/[^`]+\.py)`/g)].map((match) => match[1]);
    const names = new Set(testPaths.flatMap((relative) =>
      [...read(relative).matchAll(/^def (test_\w+)\(/gm)].map((match) => match[1])));
    for (const match of verification.matchAll(/`(test_\w+)`/g)) {
      assert.ok(names.has(match[1]), `${file} names an absent pytest assertion: ${match[1]}`);
      references += 1;
    }
  }
  assert.ok(references > 0, 'the suite must inspect actual CAP pytest citations');
});
