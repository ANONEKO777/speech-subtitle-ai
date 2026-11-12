// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Cue } from "../player/cues";
import { CueEditor } from "./CueEditor";
import { type Loaded, useCueEditing } from "./useCueEditing";

const cues: readonly Cue[] = [
  { id: 1, startMs: 1000, endMs: 2000, src: "こんにちは。", lang: "ja", zh: "你好。" },
  { id: 2, startMs: 3000, endMs: 4000, src: "二つ目。", lang: "ja", zh: "第二。" },
];
const loaded: Loaded = { cues, editedIds: [] };
const backend = { port: 1, token: "t" };

function Harness() {
  const editing = useCueEditing(backend, "p", "zh-TW", loaded);
  const cue = editing.state.cues[0]!;
  if (editing.editingId !== cue.id) return <button onClick={() => editing.begin(cue.id)}>edit</button>;
  return (
    <CueEditor
      cue={cue}
      marks={false}
      hooks={{
        validate: (d) => editing.validate(cue.id, d),
        refusal: editing.refusal,
        onCommit: (d) => editing.commit(cue.id, d),
        onCancel: editing.cancel,
      }}
    />
  );
}

const reply = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, statusText: "x" }));

async function typeAndSave(fetchImpl: () => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(fetchImpl));
  render(<Harness />);
  fireEvent.click(screen.getByText("edit"));
  const text = await screen.findByTestId("edit-text");
  fireEvent.change(text, { target: { value: "你好嗎？" } });
  fireEvent.keyDown(text, { key: "Enter" });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a failed save shows its reason on the cue after the person has typed", () => {
  it("422 english_changed", async () => {
    await typeAndSave(() =>
      reply(422, { detail: { message: "bad", problems: [{ id: 1, code: "english_changed", message: "m" }] } }),
    );
    expect((await screen.findByTestId("edit-error")).textContent).toBe("原文不能修改，只能改譯文和時間");
    expect(screen.getByTestId("cue-editor")).toBeTruthy();
  });

  it("409 job busy", async () => {
    await typeAndSave(() => reply(409, { detail: "job j1 is using this project" }));
    expect((await screen.findByTestId("edit-error")).textContent).toContain("job j1 is using this project");
  });

  it("network failure", async () => {
    await typeAndSave(() => Promise.reject(new TypeError("Failed to fetch")));
    expect((await screen.findByTestId("edit-error")).textContent).toContain("Failed to fetch");
  });

  it("clears the reason when the next attempt starts", async () => {
    let calls = 0;
    await typeAndSave(() => (calls++ === 0 ? reply(409, { detail: "busy" }) : new Promise<Response>(() => {})));
    await screen.findByTestId("edit-error");
    fireEvent.keyDown(screen.getByTestId("edit-text"), { key: "Enter" });
    await waitFor(() => expect(screen.queryByTestId("edit-error")).toBeNull());
  });

  it("typing on the source line says the source cannot be changed, and the draft is not sent", async () => {
    const fetchImpl = vi.fn(() => reply(200, {}));
    vi.stubGlobal("fetch", fetchImpl);
    render(<Harness />);
    fireEvent.click(screen.getByText("edit"));
    const source = await screen.findByTestId("edit-source");
    expect(source.textContent).toBe("こんにちは。");
    expect(source.getAttribute("lang")).toBe("ja");
    const reachedPlayer = vi.fn();
    window.addEventListener("keydown", reachedPlayer);
    fireEvent.keyDown(source, { key: "x" });
    window.removeEventListener("keydown", reachedPlayer);
    expect((await screen.findByTestId("edit-error")).textContent).toBe("原文不能修改，只能改譯文和時間");
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(reachedPlayer).not.toHaveBeenCalled();
  });
});
