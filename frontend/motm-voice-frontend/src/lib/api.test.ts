import { describe, expect, it } from "vitest";
import { apiErrorMessage } from "./api";

// Minimal fake satisfying axios.isAxiosError()'s own check
// (error.isAxiosError === true) without needing a real network round trip.
function fakeAxiosError(status: number, data?: unknown) {
  return {
    isAxiosError: true,
    response: { status, data },
  };
}

describe("apiErrorMessage", () => {
  it("surfaces the backend's detail string when present", () => {
    const err = fakeAxiosError(429, {
      detail: "Test call limit reached: 3 per hour. Try again in 42 minute(s).",
      code: "RATE_LIMITED",
      retry_after_seconds: 2520,
    });
    expect(apiErrorMessage(err)).toBe(
      "Test call limit reached: 3 per hour. Try again in 42 minute(s)."
    );
  });

  it("falls back to a friendly message for 401", () => {
    const err = fakeAxiosError(401, {});
    expect(apiErrorMessage(err)).toBe("Your session has expired. Please log in again.");
  });

  it("falls back to a friendly message for 403", () => {
    const err = fakeAxiosError(403, {});
    expect(apiErrorMessage(err)).toBe("You don't have permission to do that.");
  });

  it("falls back to a friendly message for 404", () => {
    const err = fakeAxiosError(404, {});
    expect(apiErrorMessage(err)).toBe("Not found.");
  });

  it("uses the caller-supplied fallback when there is no detail and no matched status", () => {
    const err = fakeAxiosError(500, {});
    expect(apiErrorMessage(err, "Couldn't start test call")).toBe("Couldn't start test call");
  });

  it("uses the generic default fallback when none is supplied", () => {
    const err = fakeAxiosError(500, {});
    expect(apiErrorMessage(err)).toBe("Something went wrong.");
  });

  it("reports a network-down message when there is no response at all", () => {
    const err = { isAxiosError: true, response: undefined };
    expect(apiErrorMessage(err)).toBe("Can't reach the QuickHowl server. Is the backend running?");
  });

  it("falls back for a non-axios error", () => {
    expect(apiErrorMessage(new Error("boom"), "fallback text")).toBe("fallback text");
  });

  it("ignores a non-string detail field", () => {
    const err = fakeAxiosError(422, { detail: { field: "phone_number" } });
    expect(apiErrorMessage(err, "fallback text")).toBe("fallback text");
  });
});
