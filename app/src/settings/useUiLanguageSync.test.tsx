// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import { I18nProvider, useT } from "../i18n/I18nProvider";
import * as api from "../manage/api";
import { useUiLanguageSync } from "./useUiLanguageSync";

vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchSettings: vi.fn(),
}));

const backend = { port: 1, token: "t" } as Backend;

function Probe({ ready }: { ready: boolean }) {
  useUiLanguageSync(ready ? backend : null);
  return <p data-testid="locale">{useT().locale}</p>;
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.clearAllMocks();
});

describe("useUiLanguageSync", () => {
  it("replaces the mirror with the language the backend saved", async () => {
    vi.mocked(api.fetchSettings).mockResolvedValue({ uiLanguage: "en" } as Awaited<ReturnType<typeof api.fetchSettings>>);
    render(
      <I18nProvider initial="zh-TW">
        <Probe ready />
      </I18nProvider>,
    );
    expect(screen.getByTestId("locale").textContent).toBe("zh-TW");
    await waitFor(() => expect(screen.getByTestId("locale").textContent).toBe("en"));
  });

  it("asks nothing before the backend is ready, and keeps the mirror when it cannot answer", async () => {
    vi.mocked(api.fetchSettings).mockRejectedValue(new Error("down"));
    const { rerender } = render(
      <I18nProvider initial="en">
        <Probe ready={false} />
      </I18nProvider>,
    );
    expect(api.fetchSettings).not.toHaveBeenCalled();
    rerender(
      <I18nProvider initial="en">
        <Probe ready />
      </I18nProvider>,
    );
    await waitFor(() => expect(api.fetchSettings).toHaveBeenCalledOnce());
    expect(screen.getByTestId("locale").textContent).toBe("en");
  });

  it("does nothing outside a provider, so the existing screens stay as they are", () => {
    render(<Probe ready />);
    expect(api.fetchSettings).not.toHaveBeenCalled();
    expect(screen.getByTestId("locale").textContent).toBe("zh-TW");
  });
});
