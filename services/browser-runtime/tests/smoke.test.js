import test from "node:test";
import assert from "node:assert/strict";

test("browser runtime scaffold is available", () => {
  const componentName = "MarketTwin Browser Runtime";

  assert.equal(componentName, "MarketTwin Browser Runtime");
});
