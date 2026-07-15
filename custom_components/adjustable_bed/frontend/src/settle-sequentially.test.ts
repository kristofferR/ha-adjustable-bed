import { expect, test } from "bun:test";
import { settleSequentially } from "./settle-sequentially";

test("runs operations sequentially and continues after a failure", async () => {
  const order: string[] = [];

  const failed = await settleSequentially([
    async () => {
      order.push("first:start");
      await Promise.resolve();
      order.push("first:end");
    },
    async () => {
      order.push("second");
      throw new Error("failed");
    },
    async () => {
      order.push("third");
    },
  ]);

  expect(order).toEqual(["first:start", "first:end", "second", "third"]);
  expect(failed).toBe(true);
});

test("reports success when every operation succeeds", async () => {
  expect(
    await settleSequentially([async () => undefined, async () => undefined]),
  ).toBe(false);
});
