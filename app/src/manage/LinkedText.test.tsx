// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { LinkedText } from "./LinkedText";

vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  openUrl: vi.fn(() => Promise.resolve()),
}));

afterEach(cleanup);

const MESSAGE =
  "處理失敗：這台電腦缺少 Microsoft Visual C++ 可轉散發套件（x64）。請到 https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist 下載並安裝，裝好後再試一次。";

describe("LinkedText", () => {
  it("keeps the text and makes the address a link that goes through open_url", () => {
    const { container } = render(<LinkedText text={MESSAGE} />);
    expect(container.textContent).toBe(MESSAGE);
    const link = screen.getByRole("link");
    expect(link.textContent).toBe("https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist");
    fireEvent.click(link);
    expect(api.openUrl).toHaveBeenCalledWith("https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist");
  });

  it("leaves text without an address as plain text and stops an address before a full stop or CJK text", () => {
    const plain = render(<LinkedText text="沒有網址的訊息。" />);
    expect(plain.container.querySelector("a")).toBeNull();
    cleanup();
    render(<LinkedText text="see https://github.com/a/b. then https://spdx.org/licenses/MIT.html，完" />);
    expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual([
      "https://github.com/a/b",
      "https://spdx.org/licenses/MIT.html",
    ]);
  });
});
