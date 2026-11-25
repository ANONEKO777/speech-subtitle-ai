# ZH-ASR-DECISION: Chinese as a source, measured (Z0, PARTIAL)

Status: written 2026-11-26 and stopped early by the operator's usage gate. Parts marked TODO are not
done. Nothing in `backend/`, `app/` or `tests/` changed. Every number below is measured unless it
says inferred or guess. Raw outputs are under `.work/zh-z0/` (not committed).

Goal (operator): the app takes Mandarin videos and translates them into English or Japanese for a
foreign audience. The Chinese line is Traditional by default, characters only, no Taiwan wording.

## 1. Data, licences, rights

- FLEURS test split (`google/fleurs`, Hugging Face, public, not gated, CC BY 4.0 from the dataset
  card's `license:` field and its closing paragraph): `cmn_hans_cn` 945 utterances 3.07 h (525,346,466
  bytes), `ja_jp` 650 utt (448,762,391), `ko_kr` 382 utt (214,425,558), `en_us` 647 utt (289,851,356).
  Files are 32-bit float wav, converted to 16 kHz mono 16-bit with ffmpeg. Common Voice was not
  downloaded (needs an account and accepted terms: the operator would have to do it by hand).
- Two long videos from the operator, kept outside the repository, rights belong to their authors and
  the operator: the anime explainer "詳解【來自深淵】的全部七層！動漫界獨一份的超神設定" (burned-in
  Traditional subtitles, fast speech, music, many names), and the conference talk "[2025 TGDF]
  從概念設計到虛幻引擎，在前期階段探索遊戲視覺的可能性 (陳族維)" (55 min, one speaker, slides; the
  picture holds only the session title at the bottom, no subtitles of the speech).
- A Taiwanese-voice proxy: 120 sentences of the repository's own zh-TW text read by the Windows voice
  `Microsoft Hanhan Desktop` (874 s). Clean synthetic speech: it shows script behaviour, not accuracy.

## 2. E1 engines (full FLEURS Mandarin test, 945 utterances, repository wrappers)

CER is script-free (both sides made Simplified with OpenCC `t2s`), punctuation and spaces dropped,
parenthesised Latin glosses of the reference removed. `plain` = references without Latin or digits.
RTF is wall time over audio time, model loading included, one run, utterances as chunks.

| run | CER | plain | utt p50 / p90 | punct per 1000 Han | RTF | GPU peak over baseline |
|---|---|---|---|---|---|---|
| whisper turbo `-l zh` | 5.36% | 4.29% | 3.4% / 13.0% | 12 | 0.0202 | +2.3 GB |
| whisper `-l auto` | 5.36% (same text, LID names zh) | | | | 0.0223 | +2.4 GB |
| whisper `-l zh`, prompt "以下是繁體中文的句子。" | 5.50% | 4.65% | | 32 | 0.0195 | +2.5 GB |
| Qwen3-ASR `-l zh`, aligner | 4.01% | 2.23% | 0.0% / 11.9% | 89 | 0.0311 | +7.2 GB |
| Qwen3-ASR `-l auto` | 4.01% (same text) | | | | 0.0462 | +7.5 GB |
| Qwen3-ASR `-l zh-Hant` | 4.17% (raw 28.5%) | 2.63% | | 90 | 0.0342 | +7.3 GB |
| Qwen3-ASR `-l zh`, no aligner | not scored | | | | 0.0264 | +4.6 GB |

- Paired bootstrap over utterances: whisper minus Qwen3 = +1.35 points (95% +0.98 to +1.74). measured.
- CrispASR v0.8.49 accepts `-l zh` (exit 0). It accepts any string: `xx`, `en` and `Chinese` give the same
  text as `zh`, `ja` only moves punctuation. `-l auto` runs a Whisper tiny language-id model from
  `~/.cache/crispasr/ggml-tiny.bin` (77 MB, downloaded from Hugging Face when absent), which costs
  about 48% more time. The forced aligner covers Chinese: all 945 outputs have word times. measured.
- Both engines write Simplified for this mainland audio (943 of 945 utterances). Whisper writes almost no
  punctuation (12 per 1000 Han characters), Qwen3 writes 89 (about one mark per 11 characters).
- Speed, subset of 189 utterances (2167 s), 2 rounds alternating (the brief asks 5; stopped early):
  whisper 0.0178 and 0.0211; Qwen3 0.0306 and 0.0497; Qwen3 without aligner 0.0246 and 0.0487.
  Whisper is bound by token decoding and sampling, 78% of its own time (sample 84 s plus batch decode
  88 s of 221 s on the full run), encode 11%, model load 4%, GPU load mean 35%: a CPU-side loop, not
  the GPU. Qwen3: GPU load mean 43%; the 1.6x spread between rounds is not explained (other load on
  the PC is likely, not checked). The aligner costs about 2.6 GB and 15 to 25% time in round 1. All
  runs are far faster than real time (RTF under 0.05).
- The first whisper batch ran at Normal priority, not Idle: my priority call had a bug (fixed in
  `zh_z0_common.py`); later runs are Idle.

## 3. E2 script and conversion

| source of speech | whisper | whisper + Traditional prompt | Qwen3 `-l zh` | Qwen3 `-l zh-Hant` |
|---|---|---|---|---|
| mainland FLEURS, utterances all Simplified | 943 / 945 | 865 (49 Traditional, 31 mixed) | 943 | 124 Simplified, 716 Traditional, 105 mixed |
| Taiwanese voice proxy, 120 sentences | 120 Simplified | 113 Simplified, 5 Traditional, 2 mixed | 118 Simplified | 22 Simplified, 84 Traditional, 14 mixed |
| real Taiwanese talk (E6), share of marked characters that are Traditional | 8.5% | 32.9% | 0.0% | 27.4% |

No engine setting makes the output Traditional, and a prompt or `zh-Hant` mixes the two scripts inside
one stretch. So conversion after recognition is needed whatever the engine writes (inferred from these
numbers).

Converters (scratch environments, nothing added to the repository). Round trip on 34,089 Han
characters of the repository's own Traditional text (lines with kana or Simplified-only characters
removed): Traditional to Simplified with the package's `t2s`, back with its `s2t`.

| converter (licence, install) | round-trip differences | note |
|---|---|---|
| `opencc-purepy` 1.5.2 `s2t` (MIT, pure Python wheel 1.41 MB) | 0.25% | writes 裡, 麵; leaves wording alone |
| `opencc-purepy` `s2tw` / `s2twp` | 0.26% / 1.07% | `s2twp` changed 27 of 38 mainland terms to Taiwan terms |
| `opencc` 1.4.2 (Apache-2.0, native wheels: win_amd64 2.89 MB, macOS x86_64 2.15 MB, arm64 2.05 MB, cp311) `s2t` | 1.00% | writes variant forms 爲 裏 啓 纔 峯 (not Taiwan standard) |
| `opencc` `s2tw` / `s2twp` | 0.29% / 1.18% | `s2tw` changes character forms only; `s2twp` 28 of 38 terms |
| `zhconv-rs` 0.4.2 (GPL-2.0-or-later, wheels 1.2 MB) `zh-hant` | 0.22% | turns 裡 into 里 43 times, a visible error |
| `opencc-python-reimplemented` 0.1.7 (Apache-2.0, 2023) | TODO | same module name `opencc`, so it needs its own environment |

- TODO: the `opencc` rows may come from a report merge in which the reimplemented package overwrote the
  native one for `s2t`; rerun `zh_z0_convert.py run` with distinct names before trusting rows 3 and 4.
- Plain `s2t` and `s2tw` change 1 of 38 test terms; `s2twp` changes 27 or 28. On 945 recognised utterances
  `s2tw` differs from `s2t` in 36.3% (variant characters 爲 to 為 x230, 裏 to 裡 x58, 羣 to 群 x57, 着 to 著
  x45) and `s2twp` differs from `s2tw` in 15.4% (wording: 項目 to 專案, 博客 to 部落格, 信息 to 資訊). So
  `s2tw` is not the wording-changing one the plan assumed; `s2twp` is.
- Disagreements between converters on that text (the one-to-many places): 著/着 x45, 佈/布 x24, 裡/里
  x19, 臺/台 x18, 週/周 x17, 佔/占 x14. The hard subs of the anime video themselves mix 着 and 里 into
  Traditional text, so real Traditional writing is not uniform. Speed is not a limit (400,000 characters per
  second or more for every converter).
- Recommendation (inferred, TODO confirm after the rerun above): convert with the pure-Python
  `opencc-purepy` `s2t` (MIT, no binary in the installer, 0.25%), or the native `opencc` wheel with
  `s2tw`; never `s2twp`.

## 4. E3 sizes and length

- Mandarin speech rate, FLEURS reference text: 5.28 characters per speech second (p10 4.46, p50 5.23, p90
  6.12; speech seconds by the app's Silero VAD, 1.88 h of 3.07 h), 3.22 per audio second. Anime video, ASR
  text: 4.5 per VAD speech second. Hard subs: 5.0 characters per second a line is on screen (p50 line 13
  characters, p90 19, max 20, one line). Talk: Qwen3 4.60, whisper 4.12 Han characters per speech second.
- `CueRules` start (the app's cue builder over the anime video's Qwen3 words, 600 s, 130 cues): with the
  Japanese values `max_line_chars=40` (20 full-width) and `max_cps=14.0`: cue 21 characters p50, 33 p90, 38
  max; 3.8 s p50; speed p90 6.1, max 7.4 characters per second; 0 violations; half the cues use two lines.
  Lines 32 or 28 columns give 98 or 109 two-line cues of 133 or 146. Start: **40 / 14.0** (measured; the
  Japanese values hold). `chars_per_token` and `chars_per_word` (summary sizing): not measured, TODO
  (guess: the Japanese 1.2 and 2.0).
- Density, from 80 cues of each set through Qwen3-8B with a draft Chinese source prompt (`draft` in
  `zh_z0_translate.py`: the shape of `ja_routes.HOME_RULES` without the kana, honorific and Taiwan
  lines; a stand-in written for this probe, not the app's prompt), length limits off, the target checks of
  the app on. Output characters per Chinese source character (source text in Traditional, punctuation
  counted):

| set | target | p50 | p90 | p99 | empty | kana in English | Han in English | Japanese without kana |
|---|---|---|---|---|---|---|---|---|
| FLEURS ASR | English | 3.33 | 3.96 | 4.88 | 0 | 0 | 0 | |
| anime ASR cues | English | 3.44 | 4.07 | 5.09 | 0 | 0 | 0 | |
| FLEURS ASR | Japanese | 1.34 | 1.63 | 1.90 | 0 | | | 0 |
| anime ASR cues | Japanese | 1.28 | 1.50 | 1.90 | 0 | | | 0 |

  By the P25 rule (1.5 times p90, slack 8): `Density(6.0, 8, 0.3)` for English and `Density(2.5, 8, 0.4)` for
  Japanese (inferred from 160 cues per target; the minimum ratios are a guess).
- TODO: the literal stand-in run (the Japanese source's prompts as the brief asks; `--variant standin`) was
  killed by the gate. TODO: product names turned into transliterations (sample reading showed 雞乳房 became
  "chicken breast" and 咪咪石 "ミミストーン"); the 20 sample cues with source, English, Japanese and density
  for the document. The cue files exist in `.work/zh-z0/runs/tr-draft-*.json`.

## 5. E4 detection (Whisper `-l auto -dl`, pieces cut at random from FLEURS test, app's `name_languages`)

5 s pieces, 150 per language, all pieces: zh 149/150 named zh (one named en), ja 150/150, ko 150/150,
en 150/150. No zh/ja confusion in either direction. Pieces the detector counts (probability at least 0.5
and 0.5 s of speech): 599 of 600, all right. 2 s pieces: raw 88.7% zh, 91.3% ja, 90.7% ko, 100% en; the
wrong ones are low-probability (13 of 17 zh errors under 0.5, and mostly named en); after the same filter
529 of 600 pieces count and all are right. Simulating 24-piece talks from these pieces with `zh` added to
`decide`: Mandarin only is called zh in 100% of trials; Mandarin 90 / English 10 is called mixed in 23.1%
(the 15% rule), 80 / 20 mixed in 74.7%; 50 / 50 Mandarin and Japanese always mixed; Korean gives no
answer. Limits: read speech, clean audio, three other languages only. measured; the plan (Z3) is: add
`zh` to `LANGUAGES`, keep the 5 s pieces and the 0.5 and 0.5 filters (inferred).

## 6. E5 the anime video (hard-sub reference, stress test)

600 s window from 300 s. The strip at the bottom was read at 10 frames per second: 219 raw lines, 551 s of
600 s with a subtitle (cue length p50 2.5 s, p90 3.8 s). Reference: 69 lines (875 characters, 6 stretches)
that a model read from the frames. Windows OCR (`Windows.Media.Ocr`, zh-Hant-TW, already installed) read
plain backgrounds well and failed on busy ones (lines 50, 55, 56 of the raw list); OCR text was used only
as a first draft. Hard subs are condensed and edited, my reading can be wrong: CER is an upper bound.

| run | CER vs hard subs | script written | cue start error p50 / p90 | ref line starts within 0.5 s | cue chars p50 / p90 / max |
|---|---|---|---|---|---|
| whisper `-l zh`, tokens as the shipped code merges them | 19.2% | Simplified | 1.36 / 1.71 s | 7% | 16 / 24 / 118 |
| whisper `-l zh`, unspaced (as a `zh` row would make it) | 6.89% | Simplified | 0.54 / 1.67 s | 28% | 20 / 32 / 35 |
| Qwen3 `-l zh` | 6.77% | Simplified | 0.06 / 0.17 s | 61% | 21 / 33 / 38 |
| Qwen3 `-l zh-Hant` | 6.89% | 28 Traditional, 193 Simplified characters | 0.06 / 0.17 s | 61% | 21 / 33 / 38 |

The shipped `is_spaced("zh")` is true: whisper's Chinese tokens merge into one 118-character word (the P22
bug), so a `zh` row with `unspaced=True` is required (measured). Qwen3's aligner times cues far better
than whisper's tokens. The hard subs themselves are Traditional with a few mainland forms (里, 着).
TODO: feed this video's Chinese through the converter and Qwen3-8B and list garbled proper names (character
names, titles).

## 7. E6 the TGDF talk (no hard subs, engines read against each other; a reading, not ground truth)

55.0 min, 3185 s of speech, 130 chunks. Whisper `-l zh`: 13,135 Han characters, 616 cues; Qwen3: 14,642
characters, 757 cues. Script: Qwen3 0% Traditional, whisper 8.5%. Disagreement over 20 stretches of 30 s,
script-free, Qwen3 as reference: whisper 14.83% (stretch p50 14.5%, max 39.1%); whisper with prompt 14.63%;
Qwen3 `zh-Hant` 0.33%. Reading three stretches: Qwen3 keeps spoken fillers and repeats (嗯, 呃, 我我) and
punctuates (103 per 1000 Han characters); whisper drops fillers, writes no punctuation (1 per 1000), writes a
passage in Traditional in the middle of Simplified text, and made two content errors in the stretches read
(圓形 for 原型; 幹線設計師 for a concept-designer phrase). Both write "Unreal Engine" as Latin text (9 and 10
times) and keep Blender, Photoshop, Visual Slice; the domain terms are right in both. Cues (the app's
builder, 40 / 14.0): Qwen3 13.8 per minute, 24 characters p50 / 40 p90 / 66 max.

## 8. Recommendation (labels: measured, inferred, guess)

1. Engine: Qwen3-ASR has the better CER (4.0% against 5.4%, measured), real punctuation, and cue times 6 to 8
   times closer to the hard subs (measured on one video); it costs 7 GB of GPU and 24 GB profiles only.
   Whisper keeps CPU and 8 GB profiles and drops fillers (inferred: start with whisper `-l zh` as the plan
   proposes, keep Qwen3 as the 24 GB choice; the operator should decide, the numbers support Qwen3 on
   quality and whisper on reach).
2. Always convert the recognised text to Traditional characters after recognition (measured: no engine
   setting is reliable); pure-Python OpenCC `s2t`, or native `s2tw`; never `s2twp` (inferred).
3. `zh` row: `CueRules(max_line_chars=40, unspaced=True, max_cps=14.0)` (measured); English
   `Density(6.0, 8, 0.3)`, Japanese `Density(2.5, 8, 0.4)` (inferred); a source prompt rule for fillers
   when Qwen3 is the engine (measured: it keeps them).
4. Detection: add `zh` with the existing 5 s method (measured on read speech only).
5. Chinese cue breaking hints are not yet measured (TODO).

## 9. What I could not measure or did not finish

Real Taiwanese speech with a reference (none public in this round; the proxy is synthetic); human
transcripts; E5 and E6 names and terms through the translator; the literal Japanese-prompt stand-in;
`opencc-python-reimplemented` and the converter rerun; summary sizing; speed with 5 or more rounds;
Qwen3 without aligner CER; the 20 sample cues; Cantonese and code-switching; macOS.

## 10. Rerun

Set `PYTHONPATH=<repo>;<repo>/scripts` and use the repository's Python; converters need scratch environments
(`uv venv`, then `uv pip install opencc opencc-purepy zhconv-rs`; `opencc-python-reimplemented` in another).
`zh_z0_data.py fetch|extract`; `sh scripts/zh_z0_run_e1.sh`; `scripts/zh_z0_score.py <tags>` and `--pair a b`;
`zh_z0_convert.py run` and `report`; `zh_z0_asr_convert.py <tag>`; `zh_z0_tts.py` then
`zh_z0_run_e2_e5.sh` (needs `.work/zh-z0/e5` built by `zh_z0_e5.py timeline|strips|ocr|audio` and a hand-read
`reference.tsv`); `zh_z0_detect.py run|report`; `zh_z0_rate.py rate|cues`; `zh_z0_run_speed.sh`;
`zh_z0_e6.py audio`, `zh_z0_run_e6.sh`, `zh_z0_e6.py compare`; `zh_z0_units.py` then `zh_z0_translate.py run`
and `report`.
