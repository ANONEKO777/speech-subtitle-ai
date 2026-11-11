- Each entry has a "lang" field, "ja" for Japanese or "en" for English, and the text is in the "src" field. Translate every entry from its own language. Never treat an English entry as Japanese or a Japanese entry as English.
- Japanese is often spoken with the subject left out. Read the context to find who or what each sentence is about and write that subject when Chinese needs it. Never guess a subject the context does not give.
- Drop spoken Japanese politeness and filler (ですね, ええと, あのー, まあ, ということで, させていただきます) when Chinese does not need it, but keep a clearly respectful or humble tone natural. Do not translate お/ご honorific prefixes word for word.
- Write every Japanese kanji in its Traditional form as used in Taiwan (気 becomes 氣, 会 becomes 會, 点 becomes 點, 売 becomes 賣, 続 becomes 續). Never leave kana or Japanese-only kanji in the translation.
- A katakana word is usually a loanword or a product name. Translate it by meaning when Taiwan has a common Chinese word, and keep it in its original Latin spelling when it is a product, company or person name (パフォース or パーフォース means Perforce, 東陽テクニカ is Toyo Corporation).
- A Latin word the speaker says inside a Japanese sentence (Perforce, P4, MCP, AI, PR) stays in Latin letters.
- Keep one translation for each name and term across all entries, whichever language the entry is in.

## Not yet run: Taiwan wording and product names found by the independent read

The rules above are the ones the 60-sentence probe ran with. The rules below are not tested. P23 adds them to the prompt and to the `zh_tw` check, then reruns the same 60 sentences.

- Write Taiwan wording. Say 通關 for finishing a game (クリア後 is 通關後, never 清關, which means customs clearance).
- Say 儲存庫 or 存放庫 for a code repository (not 倉庫), 管線 for a build or data pipeline (not 流水線), 營運 (not 運營), 中繼資料 for metadata (not 元數據). Say 程式碼 (not 代碼) and 外掛 (not 插件).
- Do not use the Japanese-only word 整備. Say 整理 or 準備 as the sense needs.
- A product name the ASR wrote in katakana is the product, not a phrase to translate. ビジュアルスタジオコード is Visual Studio Code, written in Latin letters.

`backend/core/zh_tw.py` `_TERMS` already replaces 代碼 and 插件. It has no entry for 倉庫, 流水線, 運營 or 元數據, and its 數據 rule would turn 元數據 into 元資料, which is also wrong in Taiwan. Add entries for the four.

The 36 rows that a second independent reader read afterwards (rows 3 and 5 to 9, 12 to 14, 17 to 20, 22, 24 to 26, 28, 31 to 34, 37 to 41, 43, 44, 46 to 48, 53, 57, 58, 60) added these errors. Rows 52 and 55 are the only two that no second reader has seen. This is still one model's reading. No human read them.

- Say 原始碼 for source code, not 源碼. Both prompts wrote 源碼 in row 17, and the candidate wrote it in row 12. Add 源碼 to `_TERMS` beside the four entries above (it has 源代碼 only).
- 間口が広い means a low barrier to entry, not a wide area. Row 48 became 廣闊的主題公園模式 (current) and 廣闊主題公園模式 (candidate), which loses the meaning. Rows 56 and 57 (the same sentence sampled twice) turned いつでもイン into 隨時可以內建 (current, meaningless) and 在線上 (candidate, a guess).
- Keep a name the ASR garbled as the name the context gives, not as a literal copy. Row 11 current wrote "Power Hoast" for パワーホスト (the candidate wrote "PowerHost" in a garbled sentence). Row 22 current kept the ASR token アプロジ as "APPROJ". Both need the glossary.
