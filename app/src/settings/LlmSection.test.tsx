// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import type { Locale } from "../i18n/locale";
import { LlmSection } from "./LlmSection";

const KEY = "sk-INVENTED inner-space";
const UNSENDABLE = "the API key holds a space, a line break or another character that cannot be sent; enter the key again";
/** What `PUT /api/settings` and `POST /api/llm/test` answer for a key no header can carry. */
const REFUSAL = { detail: UNSENDABLE, notices: [{ code: "llm.keyUnsendable", params: {}, message: UNSENDABLE }] };
const SETTINGS = {
  llm: { source: "builtin", ollama_url: "http://127.0.0.1:11434", ollama_model: "", cloud_url: "", cloud_model: "", cloud_consent: false, api_key_set: false },
  registry_url: null,
  ui_language: "zh-TW",
  cloud_consent_text: "",
  problem: null,
  storage: { user_data: "C:/u", models_dir: "C:/m", custom_models_dir: null },
};

function answer(_url: string, init?: RequestInit): Promise<Response> {
  const refused = init?.method === "PUT" || init?.method === "POST";
  return Promise.resolve(new Response(JSON.stringify(refused ? REFUSAL : SETTINGS), { status: refused ? 422 : 200 }));
}

async function fillCloud(locale: Locale) {
  vi.stubGlobal("fetch", vi.fn(answer));
  render(
    <I18nProvider initial={locale}>
      <LlmSection backend={{ port: 1, token: "t" }} />
    </I18nProvider>,
  );
  fireEvent.click(await screen.findByTestId("llm-source-cloud"));
  fireEvent.change(screen.getByTestId("cloud-url"), { target: { value: "https://api.example.test/v1" } });
  fireEvent.change(screen.getByTestId("cloud-model"), { target: { value: "m" } });
  fireEvent.change(screen.getByTestId("cloud-key"), { target: { value: KEY } });
  fireEvent.click(screen.getByTestId("cloud-consent"));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a key no header can carry", () => {
  it.each([
    ["zh-TW", "API 金鑰"],
    ["en", "the API key holds a space"],
  ] as const)("is refused on the LLM page when it is saved (%s)", async (locale, start) => {
    await fillCloud(locale);
    fireEvent.click(screen.getByTestId("llm-save"));

    const shown = (await screen.findByTestId("llm-save-error")).textContent ?? "";
    expect(shown.startsWith(start)).toBe(true);
    expect(shown).not.toContain("INVENTED");
  });

  it("is refused in Traditional Chinese when it is tested", async () => {
    await fillCloud("zh-TW");
    fireEvent.click(screen.getByTestId("llm-test"));

    expect((await screen.findByTestId("llm-test-detail")).textContent).toMatch(/^API 金鑰.*請重新輸入金鑰$/);
  });
});
