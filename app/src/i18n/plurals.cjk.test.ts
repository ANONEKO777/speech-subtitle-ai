import { describe, expect, it } from "vitest";
import { type PluralBase, plural } from ".";
import { CATALOGS } from "./catalog";

type Locale = "zh-CN" | "ja";
type Pin = Readonly<Record<Locale, string>>;

const ARGS = { size: "1 GB", notInstalled: "X", percent: 50, filesDone: 0, done: "1 MB", total: "2 MB", target: "F:/x", parts: "X" };

/** Every plural at a count of 1, read by a person. The Record type makes tsc fail when a plural key has no pin. */
const AT_ONE: Record<PluralBase, Pin> = {
  "hw.missingTitle": { "zh-CN": "还缺 1 项，共 1 GB：", ja: "あと 1 件が不足しています（合計 1 GB）：" },
  "hw.optionMissing": { "zh-CN": "缺少 1 项，要下载 1 GB", ja: "1 件が不足、1 GB のダウンロードが必要です" },
  "download.retries": { "zh-CN": "重试 1 次", ja: "1 回再試行" },
  "models.summary": {
    "zh-CN": "已安装 1 项，共 1 GB。模型和可执行文件需另外下载，可以在这里删除、校验、修复或重新下载。",
    ja: "1 件をインストール済み、合計 1 GB。モデルと実行ファイルはアプリとは別にダウンロードされます。ここで削除、検証、修復、再ダウンロードができます。",
  },
  "storage.confirm.body": {
    "zh-CN": "原文件夹中目前有 1 个已安装的模型（1 GB）。如果只更改文件夹，模型会留在原处，本软件在新文件夹中会显示为“X”。",
    ja: "元のフォルダーにインストール済みのモデルが 1 件（1 GB）あります。フォルダーだけを変更すると、モデルは元の場所に残り、新しいフォルダーではアプリに「X」と表示されます。",
  },
  "storage.moving": { "zh-CN": "移动中 50%：0 / 1 个文件，1 MB / 2 MB", ja: "移動中 50%：0 / 1 ファイル、1 MB / 2 MB" },
  "storage.moved": { "zh-CN": "移动完成：1 个文件（1 GB）已移到 F:/x", ja: "移動が完了しました：1 ファイル（1 GB）を F:/x に移動しました" },
  "edits.kept": { "zh-CN": "重新翻译后已保留 1 条手动修改", ja: "再翻訳後も手動の修正を 1 件保持しました" },
  "edits.unmatched": {
    "zh-CN": "1 条修改因原文已变而没有应用，仍保存在项目文件夹的 edits 文件中",
    ja: "原文が変わったため、修正 1 件は適用されませんでした。プロジェクトフォルダーの edits ファイルには残っています",
  },
  "queue.added": { "zh-CN": "已将 1 项加入队列", ja: "1 件をバッチに追加しました" },
  "batch.countdown.sleepAfter": { "zh-CN": "秒后进入睡眠。", ja: "秒後にスリープします。" },
  "batch.countdown.shutdownAfter": { "zh-CN": "秒后关机。", ja: "秒後にシャットダウンします。" },
  "player.foot.edited": { "zh-CN": "已修改 1 条，重新翻译时会保留", ja: "1 件を編集済み。再翻訳しても保持されます" },
  "player.failedNote": {
    "zh-CN": "1 条字幕翻译失败：X。原因是模型多次的回答都没有通过检查，例如夹杂日文、字数不合。",
    ja: "1 件の字幕の翻訳に失敗しました：X。モデルの回答が何度もチェックに通らなかったためです（例：日本語が混ざる、文字数が合わない）。",
  },
};

const say = plural as (locale: Locale, base: PluralBase, n: number, args: typeof ARGS) => string;
const LOCALES: readonly Locale[] = ["zh-CN", "ja"];

describe.each(LOCALES)("%s plurals", (locale) => {
  it("has no plural forms, so the .other text is what a count of 1 shows", () => {
    const rules = new Intl.PluralRules(locale);
    expect([0, 1, 2, 21].map((n) => rules.select(n))).toEqual(["other", "other", "other", "other"]);
  });

  for (const [base, pin] of Object.entries(AT_ONE) as [PluralBase, Pin][]) {
    it(`${base} reads right for one`, () => {
      expect(say(locale, base, 1, ARGS)).toBe(pin[locale]);
    });

    it(`${base}.one says the same as .other, since .one is never shown`, () => {
      const catalog = CATALOGS[locale] as Readonly<Record<string, string>>;
      expect(catalog[`${base}.one`]).toBe(catalog[`${base}.other`]);
    });
  }
});
