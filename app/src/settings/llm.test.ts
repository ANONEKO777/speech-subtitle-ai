import { describe, expect, it } from "vitest";
import type { LlmSaved } from "../manage/types";
import { draftFrom, toBody, validateLlm } from "./llm";

const saved = (over: Partial<LlmSaved> = {}): LlmSaved => ({
  source: "builtin",
  ollamaUrl: "http://127.0.0.1:11434",
  ollamaModel: "",
  cloudUrl: "",
  cloudModel: "",
  cloudConsent: false,
  apiKeySet: false,
  ...over,
});
const cloud = (over = {}) => ({
  ...draftFrom(saved()),
  source: "cloud" as const,
  cloudUrl: "https://api.example.com/v1",
  cloudModel: "m",
  apiKey: "sk-1",
  consent: true,
  ...over,
});
const savedCloud = saved({ source: "cloud", cloudUrl: "https://a.example.com/v1", cloudModel: "m", cloudConsent: true, apiKeySet: true });

describe("LLM source validation", () => {
  it("accepts the built-in source with nothing to fill", () => {
    expect(validateLlm(draftFrom(saved()), saved()).canSave).toBe(true);
  });

  it("needs an Ollama address and model", () => {
    const d = { ...draftFrom(saved()), source: "ollama" as const, ollamaUrl: "not a url" };
    const check = validateLlm(d, saved());
    expect(check.errors.ollamaUrl).toBeDefined();
    expect(check.errors.ollamaModel).toBeDefined();
    expect(check.canTest).toBe(false);
    expect(validateLlm({ ...d, ollamaUrl: "http://127.0.0.1:9", ollamaModel: "qwen3:8b" }, saved()).canSave).toBe(true);
  });

  it("refuses to save a cloud source until the person consents", () => {
    const check = validateLlm(cloud({ consent: false }), saved());
    expect(check.errors.consent).toBeDefined();
    expect(check.canSave).toBe(false);
    expect(check.canTest).toBe(true);
    expect(validateLlm(cloud(), saved()).canSave).toBe(true);
  });

  it("wants https for a cloud address unless it is this machine", () => {
    expect(validateLlm(cloud({ cloudUrl: "http://api.example.com/v1" }), saved()).errors.cloudUrl).toBeDefined();
    expect(validateLlm(cloud({ cloudUrl: "http://127.0.0.1:8080/v1" }), saved()).errors.cloudUrl).toBeUndefined();
  });

  it("makes the person type the key again when the address changed", () => {
    const same = { ...draftFrom(savedCloud), apiKey: "" };
    expect(validateLlm(same, savedCloud).canSave).toBe(true);
    const moved = { ...same, cloudUrl: "https://b.example.com/v1" };
    const check = validateLlm(moved, savedCloud);
    expect(check.errors.apiKey).toContain("網址已變更");
    expect(check.canSave).toBe(false);
    expect(validateLlm({ ...moved, apiKey: "sk-2" }, savedCloud).canSave).toBe(true);
  });

  it("treats a trailing slash as the same address", () => {
    const d = { ...draftFrom(savedCloud), cloudUrl: "https://a.example.com/v1/" };
    expect(validateLlm(d, savedCloud).errors.apiKey).toBeUndefined();
  });
});

describe("LLM request body", () => {
  it("sends the key only when one was typed, and consent only for cloud", () => {
    expect(toBody(cloud()).api_key).toBe("sk-1");
    expect(toBody(cloud({ apiKey: "" }))).not.toHaveProperty("api_key");
    expect(toBody({ ...cloud(), source: "ollama" }).cloud_consent).toBe(false);
  });

  it("starts from the saved consent only for a saved cloud source, and never from a saved key", () => {
    expect(draftFrom(saved({ source: "cloud", cloudConsent: true })).consent).toBe(true);
    expect(draftFrom(saved({ cloudConsent: true })).consent).toBe(false);
    expect(draftFrom(saved({ apiKeySet: true })).apiKey).toBe("");
  });
});
