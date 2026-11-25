# ZH-ASR-DECISION: Chinese as a source, measured (Z0)

Written 2026-11-26. Z0 changes no product code (`backend/`, `app/`, `tests/` are untouched). Every
number is labelled **measured** (a run I did, scripts in `scripts/zh_z0_*`), **inferred** (my reasoning
from measured numbers) or **guess**. Raw outputs are under `.work/zh-z0/` and are not committed.

Goal (operator): the app takes Mandarin videos and translates them into English or Japanese for a
foreign audience. The Chinese line is Traditional by default, characters only, no wording change.

## 1. Data, licences, rights

- FLEURS test split (`google/fleurs` on Hugging Face; public, not gated; CC BY 4.0 from the dataset card's
  `license:` field and its closing paragraph): `cmn_hans_cn` 945 utterances 3.07 h (525,346,466 bytes),
  `ja_jp` 650 (448,762,391), `ko_kr` 382 (214,425,558), `en_us` 647 (289,851,356). The files are 32-bit
  float wav; they were converted to 16 kHz mono 16-bit with ffmpeg. The FLEURS sentences quoted below are
  quoted under CC BY 4.0 (Google, FLEURS). Common Voice was not downloaded: it needs an account and
  accepted terms, so the operator would have to do that by hand.
- Two videos from the operator, kept outside the repository; their rights belong to their authors and the
  operator. (a) The anime explainer "詳解【來自深淵】的全部七層！動漫界獨一份的超神設定": Traditional
  burned-in subtitles, fast speech, music, many names; a stress test. (b) The conference talk "[2025 TGDF]
  從概念設計到虛幻引擎，在前期階段探索遊戲視覺的可能性": 55 min, slides; the picture
  shows only the session title at the bottom, so it has no subtitles of the speech; it is the typical case.
  This document holds numbers and excerpts of at most 14 characters from them. No frames, no transcripts.
- A Taiwanese-voice proxy: 120 sentences of the repository's own zh-TW text read by the Windows voice
  `Microsoft Hanhan Desktop` (874 s). Clean synthetic speech: it shows which script an engine writes for a
  Taiwan voice, not how accurate it is on a real speaker.

## 2. E1 engines (full FLEURS Mandarin test, 945 utterances, the repository's own wrappers) (measured)

CER is script-free (hypothesis and reference both made Simplified with OpenCC `t2s`), punctuation and spaces
dropped, parenthesised Latin glosses of the reference removed. `plain` = references with no Latin letter or
digit (Arabic digits against Chinese numerals count as errors). RTF = wall time over audio time, model
loading included, one run per row, each utterance as a chunk.

| run | CER | plain | utt p50 / p90 | punct per 1000 Han | RTF | GPU peak over baseline |
|---|---|---|---|---|---|---|
| whisper turbo `-l zh` | 5.36% | 4.29% | 3.4% / 13.0% | 12 | 0.0202 | +2.3 GB |
| whisper `-l auto` | 5.36% (same text: language id names zh) | | | | 0.0223 | +2.4 GB |
| whisper `-l zh`, prompt "以下是繁體中文的句子。" | 5.50% | 4.65% | | 32 | 0.0195 | +2.5 GB |
| Qwen3-ASR `-l zh`, with aligner | 4.01% | 2.23% | 0.0% / 11.9% | 89 | 0.0311 | +7.2 GB |
| Qwen3-ASR `-l auto` | 4.01% (same text) | | | | 0.0462 | +7.5 GB |
| Qwen3-ASR `-l zh-Hant` | 4.17% (raw 28.5%) | 2.63% | | 90 | 0.0342 | +7.3 GB |
| Qwen3-ASR `-l zh`, no aligner | not scored | | | | 0.0264 | +4.6 GB |

- Paired bootstrap over utterances: whisper minus Qwen3 CER is +1.35 points (95% +0.98 to +1.74). measured.
- CrispASR v0.8.49 accepts `-l zh`. It accepts any string: `xx`, `en` and `Chinese` give the same text as
  `zh`, and `ja` only moves one punctuation mark. `-l auto` runs a Whisper tiny language-id model
  (`~/.cache/crispasr/ggml-tiny.bin`, 77 MB, fetched from Hugging Face when it is absent), about 48% slower.
  The forced aligner covers Chinese: all 945 outputs have word times. measured.
- Both engines write Simplified for mainland audio (943 of 945 utterances). Whisper writes almost no
  punctuation (12 marks per 1000 Han characters), Qwen3 89 (one per 11 characters). measured.
- Speed, 189 utterances (2167 s), 5 rounds alternating whisper, Qwen3, Qwen3 without aligner. Rounds 3 to 5
  ran with nothing else on the PC: whisper 0.0168, 0.0157, 0.0156; Qwen3 0.0281, 0.0290, 0.0293; Qwen3
  without aligner 0.0219, 0.0217, 0.0218 (spread under 6%). Rounds 1 and 2 ran while I was scoring and
  linting at the same time: whisper 0.0178 and 0.0211, Qwen3 0.0306 and 0.0497, without aligner 0.0246 and
  0.0487. The earlier 1.6x variance was most likely my own concurrent CPU load (inferred: the quiet rounds repeat; I
  did not profile it). An independent remeasure on a PC that was not quiet (22 to 38% CPU from other work,
  two rounds) got whisper 0.0260 then 0.0179 and Qwen3 0.0338 then 0.0311, and the same memory (+2.26 GB and
  +7.04 GB): the order and the memory are confirmed, the absolute RTF is not exact on a loaded machine, so
  read the speed figures as low to medium confidence. Quiet-round medians, measured: whisper 0.0157, Qwen3 0.029, Qwen3 without aligner 0.0218.
  The aligner costs +0.007 RTF (+33%) and +2.5 GB. All are far faster than real time (one hour of audio in
  1 to 2 minutes). Whisper's limiter is token decoding and sampling on the CPU: 78% of its time (sample 84 s
  plus batch decode 88 s of 221 s on the full run), encode 11%, model load 4%, GPU load mean 36%. Qwen3's GPU
  load mean is 42% and I did not find its limiter. The first whisper batch ran at Normal priority, not Idle
  (a bug in my priority call, fixed); later runs are Idle.

## 3. E2 script and conversion

Share of recognised text that is Traditional (utterances all Simplified / Traditional / mixed), measured:

| speech | whisper | whisper + Traditional prompt | Qwen3 `-l zh` | Qwen3 `-l zh-Hant` |
|---|---|---|---|---|
| mainland FLEURS, 945 utterances | 943 S, 2 mixed | 865 S, 49 T, 31 mixed | 943 S, 2 mixed | 124 S, 716 T, 105 mixed |
| Taiwanese voice proxy, 120 sentences | 120 S | 113 S, 5 T, 2 mixed | 118 S, 1 T, 1 mixed | 22 S, 84 T, 14 mixed |
| real Taiwanese talk (E6), Traditional share of the characters that mark a script | 8.5% | 32.9% | 0.0% | 27.4% |

No engine setting makes the output Traditional, and a prompt or `zh-Hant` mixes both scripts inside one
stretch. So the text must be converted after recognition whatever the engine writes (inferred).

Converters, tried in scratch environments (nothing added to the repository). Round trip on 34,089 Han
characters of the repository's own Traditional text (lines with kana or Simplified-only characters removed):
`t2s` of the package, then its `s2t`; differences from the original character counted. measured.

| converter (licence, install) | `s2t` | `s2tw` | `s2twp` | wording changed to Taiwan terms (of 38), `s2t` / `s2tw` / `s2twp` |
|---|---|---|---|---|
| `opencc` 1.4.2, native (Apache-2.0; wheels cp311 win_amd64 2.89 MB, macOS x86_64 2.15 MB, arm64 2.05 MB: no build step) | 0.99% | 0.28% | 1.13% | 0 / 0 / 28 |
| `opencc-purepy` 1.5.2, pure Python (code MIT; the bundled dictionaries in `opencc_purepy/dicts/` carry their own Apache-2.0 LICENSE; one wheel, 1.41 MB, no binary) | 0.25% | 0.26% | 1.07% | 0 / 0 / 26 |
| `opencc-python-reimplemented` 0.1.7, pure Python (Apache-2.0, 2023; same module name `opencc`) | 1.00% | 0.29% | 1.18% | 0 / 0 / 27 |
| `zhconv-rs` 0.4.2 (GPL-2.0-or-later; wheels 1.2 MB), `zh-hant` / `zh-tw` | 0.22% | 0.25% | | 0 / 10 (inferred: the 手机 control removed) |

- The earlier "1.00%" row was the reimplemented package, not the native one: the two have the same module
  name and my report merge let one overwrite the other. Rerun with separate names: native `s2t` 0.99%,
  `s2tw` 0.28%. Native `s2t` writes variant forms that Taiwan does not use (為 as 爲 x108, 裡 as 裏 x70, 啟 as
  啓, 才 as 纔); `s2tw` fixes them and changes characters only, not words. `s2twp` replaces vocabulary (26 to
  28 of 38 terms) and is not wanted. measured. Correction after independent verification: my script first
  printed 1 for `s2t` and `s2tw`; that was 手机 to 手機, a character conversion counted as wording, so plain
  `s2t` and `s2tw` change no wording (0 of 38), and the `s2twp` counts are the verifier's 28, 26 and 27. The column `zh_z0_convert.py report` prints still includes that control, so it reads 1 higher than these numbers.
- On 945 recognised utterances `s2tw` differs from `s2t` in 36.3% (variant characters: 爲 to 為 x230, 裏 to 裡
  x58, 羣 to 群 x57, 着 to 著 x45), and `s2twp` differs from `s2tw` in 15.4% (wording: 項目 to 專案, 博客 to 部落格,
  信息 to 資訊). measured. Where converters disagree (the one-to-many places): 著/着 x45, 佈/布 x24, 裡/里 x19,
  臺/台 x18, 週/周 x17, 佔/占 x14. `zhconv-rs` turns 裡 into 里 43 times in the round trip, a visible error.
  The hard subs of the anime video themselves mix 着 and 里 into Traditional text, so real Traditional is not
  uniform. Speed is not a limit: 400,000 characters per second or more for every converter. measured.
- 台灣 or 臺灣 (decision for the operator). The largest round-trip difference is 台 to 臺 (41 of purepy
  `s2t`'s 84; the same 41 for every OpenCC `s2t` and `s2tw` configuration, measured): all four OpenCC
  configurations (native and pure Python, `s2t` and `s2tw`) write 臺灣 for 台灣, while `zhconv-rs` `zh-hant`
  keeps 台. In Taiwan 台灣 is the usual written form and 臺灣 the formal one (inferred), so a viewer sees a
  visible difference. The default is the converter's output (臺灣); a one-line post-fix from 臺灣 to 台灣 is
  cheap, but its effect on real Taiwanese subtitles was not measured. `opencc-purepy` `s2t` and `s2tw` differ
  in only about 0.5% of the recognised outputs, because purepy's `s2t` already writes the Taiwan-standard
  forms; native `s2t` does not (爲, 裏, 啓).
- Recommendation (inferred; the verifier would also ship `s2tw`): convert with `opencc-purepy` `s2tw` (code
  MIT, dictionaries Apache-2.0, no native code in the installer, 0.26% round trip), or native `opencc`
  `s2tw` (Apache-2.0, 0.28%) if a native wheel is acceptable in the PyInstaller bundle; never `s2twp`, never
  `zhconv-rs` (GPL, 裡 to 里). `s2tw` writes the Taiwan-standard character forms and has no phrase table. A
  switch keeps the recognised text for people who want it. Licence check before shipping:
  `THIRD-PARTY-NOTICES.md` needs the MIT notice of the code and the Apache-2.0 notice of the bundled
  dictionaries for `opencc-purepy`; for native `opencc` it needs its Apache-2.0 LICENSE and AUTHORS and the
  same check of the dictionary data in the wheel (not checked beyond the package metadata).

## 4. E3 sizes and length

- Speech rate (measured). FLEURS read speech: 5.28 characters per speech second (p10 4.46, p50 5.23, p90
  6.12; speech seconds by the app's Silero VAD: 1.88 h of 3.07 h), 3.22 per audio second. Anime video, ASR
  text: 4.5 per VAD speech second; its hard subs show 5.0 characters per second a line is on screen (line p50 13
  characters, p90 19, max 20, always one line). Talk: Qwen3 4.60, whisper 4.12 Han characters per speech second.
- `CueRules` (measured on the app's cue builder over the anime video's Qwen3 words, 600 s, 130 cues): the
  Japanese values `max_line_chars=40` (20 full-width) and `max_cps=14.0` give cues of 21 characters p50 / 33 p90
  / 38 max, 3.8 s p50, half the cues on two lines. The informative figure is speed: p90 6.1 and
  max 7.4 characters per second against the limit 14.0, so the limit never binds (a limit of 10 gives 124 cues
  of the same shape). The checker's "0 violations" only tests the builder against its own rules and is not
  evidence. 14.0 is a Japanese carry-over that works because Mandarin speech is slower than the limit; it
  was not tuned for Chinese. Narrower lines (32, 28) give more two-line cues (98 and 109 of 133 and 146). Start with
  **40 / 14.0**; the hard subs of the video use one line of at most 20 characters. On the talk the builder
  gives 13.8 cues per minute, 24 characters p50 / 40 p90 / 66 max (measured).
- Summary sizing (the Japanese row has 1.2 and 2.0). `chars_per_token`: measured with the Qwen3-8B tokenizer
  (`/tokenize`): 1.27 to 1.30 characters per token on the three Chinese sets (1.16 to 1.25 Han per token), so
  **1.3**. `chars_per_word`: no word segmenter was installed, so it is a **guess**, 1.7 (Mandarin words are
  mostly two characters, many are one).
- Density, output characters per Chinese source character (source in Traditional, punctuation counted), from
  Qwen3-8B through the app's translate path with length limits off. `draft` is a Chinese source prompt I
  wrote for this probe (the shape of `ja_routes.HOME_RULES` without the kana, honorific and Taiwan lines).
  `standin` is the app's own prompts as the brief asks, with Chinese text where they expect the other
  language: the `en` route of the Japanese source for English, the English source with the `ja` target row for
  Japanese (there is no Japanese-to-Japanese route). measured.

| variant | set (cues) | target | p50 | p90 | p99 | failed cues | Japanese without kana |
|---|---|---|---|---|---|---|---|
| draft | FLEURS ASR (120) | English | 3.37 | 4.00 | 4.61 | 0 | |
| draft | anime ASR cues (130) | English | 3.50 | 4.18 | 5.80 | 1 | |
| draft | anime hard-sub lines (69) | English | 3.62 | 4.90 | 6.00 | 0 | |
| draft | FLEURS ASR | Japanese | 1.36 | 1.63 | 1.90 | 0 | 0 |
| draft | anime ASR cues | Japanese | 1.31 | 1.60 | 2.12 | 0 | 1 |
| draft | anime hard-sub lines | Japanese | 1.25 | 1.81 | 2.30 | 0 | 2 |
| standin | FLEURS ASR | English | 3.40 | 4.02 | 4.32 | 0 | |
| standin | anime ASR cues | English | 3.45 | 4.35 | 5.80 | 1 | |
| standin | anime hard-sub lines | English | 3.50 | 4.75 | 7.12 | 0 | |
| standin | FLEURS ASR | Japanese | 1.36 | 1.63 | 2.06 | 0 | 0 |
| standin | anime ASR cues | Japanese | 1.26 | 1.54 | 1.86 | 0 | 11 |
| standin | anime hard-sub lines | Japanese | 1.25 | 1.77 | 2.10 | 0 | 2 |

  The ratios divide by the source length including the line break of two-line cues, so they are up to about 5%
  low for those cues (anime ASR English p90 prints 4.18, 4.29 without the break; standin 4.35, 4.42); the
  `Density` limits below come from the hard-sub set, which has no line breaks, and are unaffected. Short lines
  (the hard subs, 13 characters) have the larger ratios. By the P25 rule (1.5 times the largest
  p90, slack 8): English `Density(7.4, 8, 0.3)`, Japanese `Density(2.7, 8, 0.4)` (inferred; the minimum
  ratios are a guess). A failed English cue is a name the model leaves in Chinese characters, which the
  app's English check rejects four times; the route's `LEAVE_EMPTY` handles it. No English reply held kana
  or Chinese characters after the checks. The English-source prompt (`standin`) returned Japanese without any
  kana for 11 of 130 anime cues against 1 with the draft prompt, so a `zh`-to-`ja` route needs its own
  prompt and a kana requirement (measured; the cause is not isolated).
- Twenty cues picked by position, not quality (every 8th FLEURS cue, every 20th anime cue; draft prompt;
  anime lines cut to 12 characters and about 12 words; "EN" and "JA" are characters per source character):

| set | source | English | Japanese | EN | JA |
|---|---|---|---|---|---|
| fleurs 0 | 特朗普與土耳其總統雷傑普·塔伊普·埃爾多安通話後，發表了聲明。 | After speaking with Turkish President Recep Tayyip Erdogan, Trump issued a statement. | トランプはトルコ大統領レジェップ・タイイプ・エルドアンと会談後、声明を発表しました。 | 2.74 | 1.35 |
| fleurs 8 | 然而事實並非如此。雖然這份文件的背面寫了一些東西，但並不是一份藏寶圖。 | However, the fact is not like that. Although some words were written on the back of this document, it is not a map to treasure. | しかし実際にはそうではありません。この文書の裏面には何か書かれていますが、それは宝図ではありません。 | 3.63 | 1.43 |
| fleurs 16 | 在二十世紀二十年代，大多市民的主流態度是和平主義的、分離主義的。 | In the 1920s, the mainstream attitude of most citizens was pacifist and separatist. | 二十世紀二十年代には、多くの市民が平和主義的で分離主義的な態度をもっていた。 | 2.59 | 1.19 |
| fleurs 32 | 對兒童來說，金字塔的聲光表演是該地區最有趣的活動之一。 | For children, the light and sound show of the pyramids is one of the most interesting activities in the area. | 子供にとって、ピラミッドの光と音のパフォーマンスは、この地域で最も面白い活動の一つです。 | 4.04 | 1.63 |
| fleurs 40 | 獅子是群居屬性最明顯的貓科動物，生活在稱為獅群的大型群體中。 | Lions are the most social of all the cat family members, living in large groups called prides. | ライオンは群れの属性が最も明確なネコ科の動物で、大きな群れで生活しています。 | 3.13 | 1.27 |
| fleurs 48 | 浪漫主義具有很強的文化決定論色彩，這源於歌德、費希特和施萊格爾等作家。 | Romanticism has a strong cultural determinism, which comes from writers such as Goethe, Fichte, and Schlegel. | ロマンティシズムは文化的決定論の強い傾向を持ち、これはゲーテ、フェッヒェ、シュレーゲルなどの作家に由来しています。 | 3.11 | 1.63 |
| fleurs 72 | 胡納已經辭職，他在內閣中的位置將由國會議員艾德代為接替。預計國會議員諾曼蘭姆將接替艾為空出的商務部長一職。 | Huna has resigned, and his position in the cabinet will be temporarily filled by Member of Parliament Aide. It is expected that Member of Parliament Norman Larm will take over the vacant position of Minister of Commerce. | フナは辞職し、内閣の席は議員エイドに代わって行きます。議員ノーマン・ランムはエイドの空いた商務大臣の席を務める予定です。 | 4.15 | 1.13 |
| fleurs 80 | 孫德爾本斯已經被聯合國教科文組織宣佈為世界遺產。印度境內的這部分森林被稱為孫德爾本斯國家公園。 | The Sunderbans have been declared a UNESCO World Heritage Site. The part of this forest within India is called the Sunderbans National Park. | スンデルバンズは国連教科文組織によって世界遺産に登録されました。インド国内のこの部分の森林はスンデルバンズ国立公園と呼ばれます。 | 2.98 | 1.36 |
| fleurs 88 | 二十世紀的研究表明，基因變異有有兩種庫：顯性和隱性。 | Research in the twentieth century showed that gene mutations have two types: dominant and recessive. | 20世紀の研究では、遺伝的変異には2つのタイプがあります。それは優性と劣性です。 | 3.85 | 1.54 |
| fleurs 96 | 這提供了一個可以看到北極光的絕佳機會，因為天空或多或少連續一整天都是暗的。 | This provides an excellent opportunity to see the Northern Lights, as the sky is mostly dark for most of the day. | これは、極光を見ることができる素晴らしい機会を提供する。空はほぼ一日中暗いので、それほど明るくない。 | 3.05 | 1.35 |
| anime 0 | 吞食遺物和礦石的習慣，肚… | The habit of consuming relics and minerals means their stomachs may contain … | 遺物や鉱石を食べる習慣があり… | 3.80 | 1.56 |
| anime 20 | 裡面記載了深界第七層無盡… | which describes the scenery of the endless spring in the seventh layer … | ここには深界第七層の無尽の泉… | 5.00 | 1.35 |
| anime 40 | 探窟家們利用他的軀幹建立… | Explorers used its body to establish a monitoring base, … | 探窟家たちはその躯幹を使って… | 2.75 | 1.15 |
| anime 60 | 驅形獸是種體型龐大的類河… | The Shikigami is a large, hippopotamus-like creature. … | ドリーフィアは体が巨大で河馬… | 3.31 | 1.31 |
| anime 80 | 這也成了大斷層裡一處令人… | there's an ancient ship. … | 古びた船が埋め込まれているの… | 1.33 | 0.94 |
| anime 100 | 利可也不幸掉進過它的大胃… | Liko also unfortunately fell into its large stomach, and finally managed to … | リコも不幸にもその大きな胃袋… | 4.23 | 1.39 |

  What the samples show (my reading, not ground truth): the sentences read well. Names written in Chinese
  by transliteration are garbled in both targets (Flagstaff became フィガロタウン, the person 艾德 became
  "Aide" and エイド); the model takes a Chinese reading of a Western name, not its Latin spelling.

## 5. E4 detection (Whisper `-l auto -dl`, pieces cut at random from FLEURS test, the app's `name_languages`) (measured)

5 s pieces, 150 per language, all pieces: zh 149 of 150 named zh (one named en), ja 150, ko 150, en 150. No
Mandarin/Japanese confusion in either direction. Pieces the detector would count (probability at least 0.5 and
0.5 s of speech): 599 of 600, all right. 2 s pieces: raw 88.7% zh, 91.3% ja, 90.7% ko, 100% en; the wrong ones
are low-probability (13 of 17 zh errors under 0.5, mostly named en); after the same filter 529 of 600 pieces
count and all are right. Simulating 24-piece talks from these pieces with `zh` added to `decide`: Mandarin
only is called zh in 100% of trials, Mandarin 90 / English 10 is called mixed in 23.1% (the 15% rule), 80 / 20
mixed in 74.7%, 50 / 50 Mandarin and Japanese always mixed, Korean gives no answer. Limits: read speech, clean
audio, one speaker per piece. Plan (inferred): add `zh` to `LANGUAGES`, keep 5 s pieces and the 0.5 and 0.5 s
filters; a talk with English asides will often read as mixed, which the mixed path rejects today (out of
scope for Z1).

## 6. E5 the anime video (hard-sub reference; a stress test)

600 s window from 300 s. The strip at the bottom of the picture was read at 10 frames per second: 219 raw
lines, 551 s of 600 s with a subtitle (line length p50 2.5 s, p90 3.8 s). The reference is 69 lines (875
characters, 6 stretches) that I read by eye from the frames; hard subs are edited and condensed and my reading
can be wrong, so CER against it is an upper bound and a sanity check, not ground truth. OCR route: Windows
OCR (`Windows.Media.Ocr`, zh-Hant-TW, already installed) read plain backgrounds well and failed on busy ones
(of the 72 lines I viewed, at least 4 read blank or as noise); it was only a first draft.

| run | CER vs hard subs | script written | cue start error p50 / p90 | reference starts within 0.5 s | cue chars p50 / p90 / max |
|---|---|---|---|---|---|
| whisper, tokens merged as the shipped code does (`is_spaced("zh")` true) | 19.2% (artifact, see below) | Simplified | 1.36 / 1.71 s | 7% | 16 / 24 / 118 |
| whisper, unspaced (as a `zh` row would make it) | 6.89% | Simplified | 0.54 / 1.67 s | 28% | 20 / 32 / 35 |
| Qwen3 `-l zh` | 6.77% | Simplified | 0.06 / 0.17 s | 61% | 21 / 33 / 38 |
| Qwen3 `-l zh-Hant` | 6.89% | 28 Traditional, 193 Simplified characters | 0.06 / 0.17 s | 61% | 21 / 33 / 38 |

- The unspaced `zh` row is mandatory: with the shipped spaced default whisper's Chinese tokens merge into 197
  words, the longest of 118 characters (the P22 bug again), and the stretch-scored CER rises from 6.89% to
  19.2%. That rise is a scoring artifact: the recognised text is almost the same (2679 against 2682
  characters), and the scorer assigns each word to a hard-sub stretch by its midpoint, so a 118-character
  word lands in the wrong stretch. The real harm is timing and cue building: start error p50 1.36 s and a
  118-character cue. It is not a recognition failure. The conclusion (an unspaced row is needed) stands.
  measured.
- Qwen3's aligner times cues about 9 times closer to the hard subs than whisper's tokens (start error p50 0.06
  against 0.54 s), measured on this one video. The hard subs mix a few mainland forms (里, 着) into Traditional.
- Names (this video's Chinese through the converter and Qwen3-8B; `draft` prompt; 11 names, accepted
  renderings are the series' official English and Japanese names as I know them, unchecked, so a miss is a
  difference to read, not proof of error). Cues = hard-sub lines plus ASR cues that hold the name. measured:

| name | cues | English accepted | Japanese accepted | what the model wrote |
|---|---|---|---|---|
| 莉可 | 3 | 0 | 2 | English "Liko" (pinyin reading of the characters), Japanese リコ |
| 阿庇斯 | 2 | 0 | 0 | "Apis", "Abis"; アピス (series: Abyss, アビス) |
| 深界 | 15 | 15 | 15 | layer, 深界 |
| 探窟家 | 12 | 0 | 12 | English "explorers" 12 of 12 (series term: Cave Raider); Japanese kept |
| 赤笛 / 青笛 / 蒼笛 | 2 / 1 / 1 | 0 | 2 / 1 / 1 | English "Red Pipe", "Red Flute", "Red Di", "Qing Di" (pinyin) |
| 星之羅盤 | 2 | 2 | 1 | Star Compass; スターコンパス |
| 奧森 | 2 | 0 | 0 | "Osan", "Unmoto Kiyohiro"; オーセン, 不动清 (a Simplified character) |
| 孤兒院 | 2 | 2 | 2 | correct |
| 巨人之杯 | 2 | 2 | 1 | Giant's Cup; 巨人のグラス |

  So the model turns names into transliterations in English: 7 of 11 names had no accepted English rendering
  (pinyin readings such as Liko and Qing Di, or a translated common noun), while kanji names survive in
  Japanese (2 of 11 had no accepted Japanese rendering, both spelling variants: アピス and オーセン; three
  more were missed in one of two cues).
  A glossary with aliases is needed, as P25 and P30 did for Japanese. The ASR itself garbles some names
  (驅形獸 for the creature, 利可 for 莉可). One anime cue stays in Chinese characters after four tries.

## 7. E6 the TGDF talk (no hard subs; the engines read against each other; a reading, not ground truth)

55.0 min, 3185 s of speech, 130 chunks. Whisper `-l zh`: 13,135 Han characters, 616 cues; Qwen3: 14,642
characters, 757 cues. Script: Qwen3 0% Traditional, whisper 8.5% (a Taiwanese speaker, Simplified output).
Disagreement over 20 stretches of 30 s, script-free, Qwen3 as the reference: whisper 14.83% (stretch p50 14.5%,
max 39.1%); whisper with the Traditional prompt 14.63%; Qwen3 `zh-Hant` 0.33%. Reading three stretches: Qwen3
keeps spoken fillers and repeats (嗯, 呃, 我我) and punctuates (103 marks per 1000 Han characters); whisper
drops fillers and repeats, writes no punctuation (1 per 1000), changed script in the middle of a stretch, and
made two content errors in the stretches I read (圓形 for 原型; a wrong word for "concept designer"). Both write
"Unreal Engine" as Latin text (9 and 10 times) and keep Blender, Photoshop and Visual Slice; the domain terms
are right in both. The 14.8% disagreement is mostly fillers and repeats, so it is not an error rate of either
engine. Cues (the app's builder, 40 / 14.0): Qwen3 13.8 per minute, 24 characters p50 / 40 p90 / 66 max.

## 8. Recommendation (each item labelled)

1. **Engine (the operator's call; the numbers support this order).** Use Qwen3-ASR for Chinese where the
   profile has it (the 24 GB profile) and whisper turbo `-l zh` everywhere else. Qwen3: CER 4.0% against 5.4%
   (measured, 95% interval of the gap +0.98 to +1.74 points), real punctuation (89 against 12 marks per 1000
   characters; whisper's cues would break only on pauses), cue starts 0.06 s against 0.54 s from the hard subs
   (one video), RTF 0.029 against 0.016; but +7.2 GB GPU against +2.3 GB, no CPU path, and it keeps fillers
   and repeats (a source prompt rule or a post-filter must drop 嗯 and 呃; inferred). **Whisper only** adds no
   model, registry row or licence and works on every profile including CPU and Mac, at the cost of 1.35
   points of CER, no punctuation, weaker cue timing and an occasional wrong content word (measured on
   FLEURS, the anime video and one talk). **Qwen3 only** would make Chinese 24 GB-only (inferred from the
   profiles in the plan). A per-profile choice costs one row of engine selection (inferred).
2. **Conversion.** Always convert the recognised text to Traditional characters after recognition (no engine
   setting is reliable: measured). `opencc-purepy` `s2tw` (code MIT, dictionaries Apache-2.0, no native code, 0.26% round
   trip) or native `opencc` `s2tw` (Apache-2.0, 0.28%), both notices in THIRD-PARTY-NOTICES; the 台灣 or 臺灣
   form is the operator's choice (section 3); never `s2twp` (changes wording), never `zhconv-rs` (GPL, 裡 to 里).
   This is inferred from the round-trip and wording numbers above.
3. **Unspaced `zh` row is mandatory** (measured: with the shipped spaced default whisper's tokens merge into
   a 118-character word, cue start error p50 1.36 s against 0.54 s, and the stretch-scored CER is 19.2%
   against 6.89%, an artifact of assigning words by midpoint; the text itself is almost unchanged).
   `CueRules(max_line_chars=40, unspaced=True, max_cps=14.0)` (the limit never binds: max 7.4 characters per
   second on 130 cues; not tuned for Chinese);
   `chars_per_token` 1.3 (measured), `chars_per_word` 1.7 (guess); English `Density(7.4, 8, 0.3)`, Japanese
   `Density(2.7, 8, 0.4)` (inferred from p90 of 319 cues per target); route-level `needs_script` and a kana
   requirement for Japanese (measured: 11 of 130 kana-free replies with the English-source prompt).
4. **Names.** Ship a glossary with aliases and a source-prompt rule for Chinese-reading names, because English
   output turns names into pinyin readings (measured: 7 of 11 names without an accepted English rendering).
5. **Detection.** Add `zh` to `LANGUAGES` with the existing 5 s method and filters (measured on read speech;
   a talk with English asides will read as mixed).

## 9. What I could not measure or did not run

- Real Taiwanese speech with a reference transcript: none is public in this round; the proxy voice is
  synthetic and the talk has no reference (only engine agreement). Common Voice was not downloaded.
- Human transcripts: the anime reference is my reading of frames; the CER there is an upper bound.
- Quality of the translations beyond my own reading of samples and the structural checks: no native reader.
  The accepted names are my own knowledge of the series, unchecked.
- `chars_per_word` (guess); Chinese cue-break hints (function words) were not tried; Qwen3 without aligner was
  timed but not scored for CER; the Qwen3 speed limiter was not profiled.
- The Taiwanese-wording check of the converted text (`zh_tw` term tables stay out of the path by design).
- Burn-in fonts, macOS, CPU-profile speed, Cantonese, Chinese and English code-switching talks.
- Only one anime window (10 min of 34), one talk, one machine (RTX 4090) shared with other work, so the
  speed numbers are low to medium confidence. How often 臺 occurs in real Taiwanese subtitles (the 台灣 or
  臺灣 post-fix) was not checked.

## 10. Rerun

Use the repository's Python with `PYTHONPATH=<repo>;<repo>/scripts` (set `ZH_Z0_DATA` and `ZH_Z0_WORK` when the
data is not under the main checkout's `.work/zh-z0`), and scratch environments for the
converters (`uv venv .work/zh-z0/venv-native`, `uv pip install opencc opencc-purepy zhconv-rs`; and
`venv-reimpl` with `opencc-python-reimplemented`). Commands, in order: `zh_z0_data.py fetch` then `extract`;
`sh scripts/zh_z0_run_e1.sh`; `zh_z0_score.py <tags>` (and `--pair a b`); `zh_z0_convert.py run --out X`
(`--opencc-label opencc-reimpl` in the second environment) then `report`; `zh_z0_asr_convert.py <tag>`;
`zh_z0_tts.py` then `sh scripts/zh_z0_run_e2_e5.sh`; `ROUNDS="1 2 3 4 5" sh scripts/zh_z0_run_speed.sh`;
`zh_z0_rate.py rate` and `cues --run e5-q`; `zh_z0_detect.py run` then `report`; the video steps (`zh_z0_e5.py
timeline|strips|ocr|audio`, a hand-read `e5/reference.tsv`, `zh_z0_e5_score.py`, `zh_z0_e6.py audio`, `sh
scripts/zh_z0_run_e6.sh`, `zh_z0_e6.py compare`); and the translation probe (`zh_z0_units.py` in the converter
environment, `zh_z0_translate.py run --variant draft` and `standin`, `report`, `samples`, `zh_z0_names.py`,
`zh_z0_tokens.py`).
