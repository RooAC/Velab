import { apiError, backendUnreachable } from "@/lib/apiError";
import { describe, expect, it } from "vitest";

describe("apiError", () => {
  it("returns the shared structured error shape", async () => {
    const response = apiError("INVALID_INPUT", "invalid input", 400, { field: "name" });

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({
      error: {
        code: "INVALID_INPUT",
        message: "invalid input",
        details: { field: "name" },
      },
    });
  });

  it("provides a common backend unreachable response", async () => {
    const response = backendUnreachable();

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({
      error: {
        code: "BACKEND_UNREACHABLE",
        message: "backend service is unreachable",
      },
    });
  });
});
