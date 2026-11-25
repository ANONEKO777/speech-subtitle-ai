# Plan: Chinese videos as a source, translated into English or Japanese

Status: plan only, nothing is implemented. Written 2026-11-26 from a read-only exploration of `main` (every claim below about the code was read from it; claims about model behavior are marked as unmeasured).

## Goal

A person picks a video with Mandarin speech, and the app produces well-timed subtitles in the original Chinese plus a translation into English or into Japanese, with the same summary, editor, exports and burn-in it has for English and Japanese videos. Chinese is not a target here: a Chinese source translated to Traditional or Simplified Chinese is script conversion, not translation, and is excluded.

Today Chinese is not an accepted source. Language detection counts only Japanese and English, so Chinese speech returns "no guess".

## What the exploration found

The design already has the seam. A source language is one row in `backend/core/source_langs.py`, with per-target routes in `backend/core/ja_routes.py` and `target_routes.py`, and Japanese to English already ships that way. A `zh` row with an `en` route and a `ja` route expresses both pairs. Two corrections to earlier assumptions: pure Japanese uses whisper `large-v3-turbo` with `-l ja` (Qwen3-ASR is pinned only for the mixed Japanese and English source), and nothing tied to the Traditional Chinese target (`zh_tw.py`, Taiwan wording) is touched by a Chinese source.

The three real coupling points are these.

1. **Checks that assume a spaced or kana source.** The "must contain a translated script" check counts source words, so Chinese never requires one. The Japanese-output check accepts any ideograph and only demands kana when the English text has more than 5 words, so a reply that copies the Chinese into the Japanese line would pass. Length limits are measured in source characters and nobody has measured English or Japanese per Chinese character. The route object already has the fields to fix this (`needs_script`, `problem`, `density`). The Simplified-versus-Japanese test must use JIS membership, not the Simplified-only set, because characters such as 国, 学 and 会 are valid in both.
2. **ASR language and script are unmeasured, and unspaced handling turns on only through the row.** An unknown language code counts as spaced, so whisper's Chinese tokens would merge into one word (the bug P22 found for Japanese). The repository says nothing about whether whisper or Qwen3 writes Simplified or Traditional Chinese, nothing about whether CrispASR accepts `-l zh`, and nothing about which languages the forced aligner covers.
3. **Closed sets and the default target.** The frontend `SourceLang` type is closed and turns an unknown code into `en`. `zh-TW` is the default target in five places (`Settings`, `Request`, `JobBody`, `JobOptions`, the CLI), so a Chinese job without a target gets a 422. Cue breaking in `unspaced.py` is shaped by Japanese particles and endings, so every cut between two Chinese characters costs the same and a cue can split inside a word.

## Decisions (my recommendation; say so if you want another)

1. **Engine: start with whisper `large-v3-turbo` and `-l zh`.** It adds no model, registry row, licence or download, works on every profile including CPU and Mac, and is how Japanese works. Qwen3-ASR stays a measured alternative: it would make Chinese 24 GB-only with no CPU path. The choice is made by experiment E1 below, as P22 chose for Japanese, not by assumption.
2. **A default target per source.** Replace the `zh-TW` constant in five places with one function, `default_target(source)`: `zh-TW` for English and Japanese sources (unchanged), `en` for a Chinese source. The target picker lists only the targets a source allows. This is the domain model change that makes the rest simple.
3. **A `zh` source row** with `targets = {en, ja}`, `CueRules(unspaced=True)` with values from experiment E3 (starting guess: the Japanese values), its own source prompt (Chinese fillers such as 嗯, 呃, 那个, 就是, 然后, dropped subjects, names), routes to English and to Japanese in a new `zh_routes.py` modeled on `ja_routes.py`, with route-level `needs_script`, `problem` and `density`. Failure fallback for Chinese to Japanese: leave the line empty or pivot through the Chinese-to-English route, decided in Z1 by measurement. A Chinese summary prompt per target (`summarize_map_zh_to.md`), because today's summary prompts are English-only or hard-code Japanese.
4. **Chinese cue breaking.** Add function-word and conjunction hints (的, 了, 但是, 因为, 所以 and the Traditional forms) as a hook in `unspaced._boundary` that does nothing for Japanese, so Japanese output stays byte-identical, proven by the existing test and a before and after run.
5. **Source script.** Keep the text as the engine writes it. If the engine writes Simplified for a Taiwanese speaker, a bias (an initial prompt to whisper) or a source-line conversion is a follow-up decided by E2 and by you, since the Traditional Chinese audience is likely your main one.
6. **Detection is a convenience, not a gate.** A Chinese project works with the language picked by hand. Recognising Chinese is a later wave (Z3): `LANGUAGES` grows beyond the mixed source's two members, `Sample.clear` and `decide` change, the frontend `Detection` type generalizes, and Chinese versus Japanese confusion on short pieces is measured first.
7. **Out of scope:** Cantonese and other dialects, Chinese and English code-switching talks (the mixed path rejects Simplified characters today), Chinese as a target, speaker labels.

## Waves (each a PR with an independent verifier; Z0 changes no product code)

- **Z0, experiments (needs your OK to download test audio).** On a GPU, one model at a time. E1: Mandarin CER, real-time factor and VRAM for whisper turbo (`-l zh`) and Qwen3-ASR with and without the forced aligner, whether CrispASR accepts `-l zh`, and the script and punctuation each writes. E2: whether an initial prompt moves whisper to Traditional characters. E3: Mandarin speech rate in characters per second, cue-size values, and English and Japanese output length per Chinese character, from real translations. E4: whisper's language id on 5 second pieces for Chinese versus Japanese versus Korean. Output is a decision document with numbers, like `docs/P22-japanese-asr-decision.md`.
- **Z1, backend.** `default_target(source)`, the `zh` row, `zh_routes.py`, prompts, checks, cue break hook, summary prompts, CLI (`--source-lang zh --lang en`), tests and mutants, a structure check that every source row has a route per allowed target.
- **Z2, frontend.** `SourceLang` gains `zh`, label, tag and note ("Chinese: subtitles in English or Japanese"), the target picker filtered by source, the export names (`<video>.zh.srt`), library tag. Do this after i18n wave W2 so the strings go straight into the catalog instead of the old table.
- **Z3, detection (optional).** As in decision 6.
- **Z4, quality pass.** End to end on real clips in the real window, you read the Chinese to English and Chinese to Japanese output, fix recurring mistakes through a term table as P25 and P30 did, check the Chinese source line in the burned-in subtitle (the font must be a Chinese font on Windows and on macOS), update README, SPEC and the feature docs ("Only English and Japanese are recognized" stops being true).

## Test audio and quality

The repository has no Chinese audio (only an English test clip and the demo video). For measurement I propose public read-speech sets with open licences, to be checked before use and downloaded only with your OK: Mozilla Common Voice (zh-TW, CC0), FLEURS (Mandarin, CC BY 4.0) and AISHELL-1 (Apache-2.0). These licence names come from my own knowledge and are not verified here. For long-form behavior (cues, summary, translation) I need one or two Chinese talks, ideally yours, because anything I pick must be legal to keep next to the repository and a private clip need not be. Quality has no ground truth beyond CER for Chinese ASR, so translation quality is judged by structural checks (the P25 harness pattern) plus you reading samples.

## Risks

- Whisper may write Simplified characters for a Taiwanese speaker, and may drop punctuation (unmeasured).
- Qwen3-8B may turn product names into Chinese transliterations that the English and Japanese output should write in Latin letters or katakana. The glossary and the term table are the existing levers.
- Chinese to Japanese passes through a model pair never evaluated for it. The length and script checks are the safety net, and the fallback is a decision, not a guess.
- The i18n program also edits `app/src/api/sourceLang.ts`. Z2 waits for it to avoid a conflict. The i18n plan's statement that the app takes "Japanese or English in" must be updated when Chinese ships.

## What I need from you

Nothing blocks Z0 except permission to download test audio and a decision on the audience. If you do not answer, Z0 uses whisper turbo as the default engine under test, Common Voice zh-TW and FLEURS Mandarin as the sets, treats Taiwan Mandarin in Traditional characters as the primary audience, and asks you for a talk clip when Z1 is ready. Tell me in your own words if your main audience is mainland Mandarin in Simplified characters instead, if you want Qwen3-ASR as the default engine, or if you want a different order.
