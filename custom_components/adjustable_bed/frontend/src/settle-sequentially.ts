/** Run every asynchronous operation in order and report whether any failed. */
export async function settleSequentially(
  operations: readonly (() => Promise<unknown>)[],
): Promise<boolean> {
  let failed = false;
  for (const operation of operations) {
    try {
      await operation();
    } catch {
      failed = true;
    }
  }
  return failed;
}
