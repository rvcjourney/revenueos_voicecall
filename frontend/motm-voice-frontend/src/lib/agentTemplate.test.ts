import { describe, expect, it } from "vitest";
import { DEFAULT_GREETING, DEFAULT_INSTRUCTIONS, findVariables } from "./agentTemplate";

describe("findVariables", () => {
  it("lists each placeholder once, in order of appearance", () => {
    expect(findVariables("Hi {userName} from {partnerName}", "Bye {userName}, {current_date}")).toEqual([
      "userName",
      "partnerName",
      "current_date",
    ]);
  });

  it("ignores braces that aren't placeholders", () => {
    expect(findVariables('{"json": 1} { spaced } {9bad}')).toEqual([]);
  });

  it("finds every placeholder in the default template", () => {
    const vars = findVariables(DEFAULT_GREETING, DEFAULT_INSTRUCTIONS);
    expect(vars.slice(0, 2)).toEqual(["partnerName", "userName"]);
    expect(vars).toContain("current_date");
    expect(vars).toHaveLength(18);
  });
});
