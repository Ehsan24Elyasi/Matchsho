import test from "node:test";
import assert from "node:assert/strict";
import { safeHref } from "../js/ui.js";
import { parseRoute } from "../js/router.js";
import { parseCSV } from "../js/features/admin.js";
test("unsafe user-provided link destinations never become executable URLs", () => {
  for (const value of [
    "javascript:alert(1)",
    "//evil.example",
    "/\\evil.example",
    "data:text/html,a",
    "https://evil.example",
    "\n/evil",
  ])
    assert.equal(safeHref(value), "#");
  assert.equal(safeHref("#profile/42"), "#profile/42");
  assert.equal(safeHref("/privacy.html"), "/privacy.html");
});
test("profile identity and list filters survive direct route reconstruction", () => {
  const route = parseRoute("#profile/42?from=matches&page=2");
  assert.deepEqual(route.parts, ["profile", "42"]);
  assert.equal(route.params.get("page"), "2");
  assert.equal(parseRoute("#").path, "home");
});
test("CSV roster preserves quotes, commas and newlines without spreadsheet evaluation", () => {
  const result = parseCSV(
    'student_id,email,name,class_name,gender,pool,cycle\r\n42,a@example.test,"علی، \"\"الف\"\"",CS,male,male,1405',
  );
  assert.equal(result[0].name, 'علی، "الف"');
  assert.equal(result[0].student_id, "42");
  assert.throws(() => parseCSV("name,email\nx,y"), /ستون/);
  assert.throws(
    () => parseCSV('student_id,email,name,class_name,gender,pool,cycle\n"bad'),
    /نقل/,
  );
});
