import "@testing-library/jest-dom";
import { vi } from "vitest";

// Mock scrollIntoView for chat component tests
if (typeof window !== "undefined") {
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
}
