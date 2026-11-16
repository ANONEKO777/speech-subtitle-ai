# P25: evidence for translating a Japanese talk into 12 other languages

Status: evidence and a recommendation for the P26 scope. No human and no independent model has judged
the quality of any output yet. Every number below comes from automatic checks, or from the same
local model (Qwen3-8B) grading its own back-translations. Read the numbers as a screen for
failures, not as a quality ranking.

The evidence files named in this document live outside the repository, in
`C:\Users\abcd1997\.claude\orchestrate\video-subtitle-translator\swarm\P25\` (written here as
`swarm\P25\`). They hold text from the operator's talks, so they are not committed. The two scripts
that made them are: `scripts/p25_ja_multilang.py` and `scripts/p25_check.py`.

## What was run

- **Sample.** 40 sentence units spread over the Japanese talk, and 10 Japanese units from the
  Japanese and English talk (Japanese cues only). One unit is picked at random from each of 40
  (and 10) equal slices of the units, with seed 2511, units under 12 characters left out. The ids
  are in `swarm\P25\unit-ids.txt` and `swarm\P25\units.json`. Together they are 149 cues.
- **Targets.** English, Simplified Chinese, Korean, Spanish, French, German, Portuguese (Brazil),
  Italian, Russian, Vietnamese, Thai, Indonesian.
- **Routes.** `direct`: Japanese to the target. `via-en`: Japanese to English over the whole talk,
  then English to the target, with the real English cues around each unit as context. `via-zh`: the
  same with the Traditional Chinese (Taiwan) output of current main as the middle step. English as
  a target has `direct` and `via-zh` only: its `direct` run is the middle step of `via-en`.
- **Model and settings.** Qwen3-8B Q4_K_M on llama-server, the pipeline's seed, no thinking, 8192
  context, default glossary, `keep_english=True`, batches and retries of `translate.run`.
- **Back-translation.** For 30 of the 50 units (24 and 6), each route's output is translated back
  into Japanese by the same model, in batches of 10 (5 after Thai overflowed the context). The overlap with the Japanese source is the Dice
  coefficient of character bigrams. The same model also scores each pair from 0 to 5.
  The model grades its own work and the scores are saturated (4.2 to 4.9 for everything), so they
  are a weak signal. Sentences that any route left with kana are dropped from the comparison,
  because Japanese back-translates to itself and would look perfect.

### What the harness bypasses

`scripts/p25_ja_multilang.py` calls `translate.run` and the prompt builders, but the registry cannot
take a non-zh-TW target for a Japanese source: `JAPANESE_SOURCE.targets` is `{"zh-TW"}` and its
rules, clean-up and checks are written for Taiwan Chinese. The harness therefore:

1. removes the "Write every Japanese kanji in its Traditional form" and "Use Taiwan wording" rules,
   and says "the target language" where the rules said Chinese or Taiwan;
2. turns off the Japanese source's own clean-up, term table and rewrites;
3. turns off the length check of `_check_text` (a limit of 1000 times), because 1.1 times the
   Japanese length cannot hold a Latin-script language. The measured ratios are below;
4. keeps the target's script check, but `needs_script` counts English words in the Japanese, so for
   a Japanese source it is nearly always false and a reply left in English would pass the pipeline's
   check. `p25_check.py` forces the script check on every output.
5. adds English as a target (the registry has none) and a Chinese middle source for `via-zh`.

`direct.zh-TW` and the `via-zh` middle step use the unchanged zh-TW flow of this checkout.

Not part of the sample: the English cues of the mixed talk were not translated, so the plan's check
that the English and Japanese segments of one video use the same names was not run.

## Results by language and route

Counts are over the 149 sampled cues. "Failed" is a cue left in Japanese or English after four
attempts, plus any output the script check rejects. "Two lines" is a cue wider than two lines of 40
columns, with the Japanese cue timing and split kept. Dice and score are the back-translation
numbers (n = 30; Korean `direct` n = 25, Spanish `direct` n = 29).
Source: `swarm\P25\checks\summary.tsv` and `swarm\P25\checks\routes.tsv`.

| Target | Route | Failed | Two lines | Dice | Score 0-5 |
|---|---|---|---|---|---|
| en | direct | 0 | 27 | 0.434 | 4.77 |
| en | via-zh | 0 | 37 | 0.371 | 4.47 |
| zh-CN | direct | 0 | 0 | 0.422 | 4.63 |
| zh-CN | via-en | 0 | 1 | 0.384 | 4.60 |
| zh-CN | via-zh | 0 | 0 | 0.427 | 4.63 |
| ko | direct | 6 | 6 | 0.514 | 4.72 |
| ko | via-en | 2 | 10 | 0.379 | 4.60 |
| ko | via-zh | 1 | 12 | 0.371 | 4.56 |
| es | direct | 1 | 52 | 0.394 | 4.31 |
| es | via-en | 0 | 45 | 0.386 | 4.41 |
| es | via-zh | 0 | 51 | 0.371 | 4.41 |
| fr | direct | 0 | 63 | 0.384 | 4.83 |
| fr | via-en | 0 | 51 | 0.374 | 4.53 |
| fr | via-zh | 0 | 61 | 0.330 | 4.03 |
| de | direct | 0 | 53 | 0.403 | 4.57 |
| de | via-en | 0 | 40 | 0.391 | 4.43 |
| de | via-zh | 1 | 50 | 0.358 | 3.93 |
| pt | direct | 0 | 47 | 0.407 | 4.60 |
| pt | via-en | 0 | 40 | 0.384 | 4.67 |
| pt | via-zh | 0 | 46 | 0.337 | 4.33 |
| it | direct | 0 | 45 | 0.402 | 4.40 |
| it | via-en | 0 | 40 | 0.401 | 4.53 |
| it | via-zh | 0 | 52 | 0.347 | 4.07 |
| ru | direct | 0 | 44 | 0.388 | 4.40 |
| ru | via-en | 0 | 36 | 0.372 | 4.47 |
| ru | via-zh | 1 | 44 | 0.340 | 4.03 |
| vi | direct | 0 | 42 | 0.362 | 4.57 |
| vi | via-en | 0 | 38 | 0.379 | 4.27 |
| vi | via-zh | 2 | 38 | 0.318 | 3.93 |
| th | direct | 0 | 32 | 0.349 | 4.23 |
| th | via-en | 1 | 18 | 0.338 | 4.17 |
| th | via-zh | 1 | 23 | 0.330 | 4.20 |
| id | direct | 0 | 56 | 0.386 | 4.67 |
| id | via-en | 0 | 35 | 0.385 | 4.30 |
| id | via-zh | 0 | 45 | 0.352 | 4.30 |
| zh-TW (current main) | direct | 0 | 0 | 0.422 | 4.87 |

### How much the numbers can tell

- Dice values only compare across routes of one language. Different targets back-translate with
  different loss. The per-sentence standard deviation of Dice is about 0.1 (0.085 to 0.139 by
  language), and the standard error of the paired difference between two routes on the same
  sentences is 0.013 to 0.03. `direct` against `via-en` is inside two standard errors in every
  language except Korean (+0.158) and Simplified Chinese (+0.038). `direct` against `via-zh` is
  higher by 0.043 to 0.070, which is more than two standard errors, in en, de, fr, it, pt, ru
  and vi; in es and id it is higher by 0.049 and 0.034, under two.
- The 0 to 5 score separates routes only a little. In `routes.tsv`, `direct` scored higher than
  `via-zh` on more sentences than the reverse in every language except Thai and Spanish, by wide
  margins in French (18 to 0), German (15 to 1) and Vietnamese (11 to 1). `direct` against `via-en`
  is close to even in es, it, pt, ru, th and zh-CN, and favours `direct` in de (10 to 4), fr (9 to 1),
  id (8 to 4) and vi (7 to 1).
- The Korean `direct` Dice of 0.514 is the one clear outlier (6 standard errors above `via-en`).
  It may be real, since Japanese and Korean share word order, or an artifact of cues the model left
  partly in Japanese or Chinese characters (sentences with kana are already dropped). It is an
  observation to confirm with a reader, not a finding.
- The "failed" column is the more trustworthy automatic number: it counts outputs a reader would
  reject on sight.

### Time

All times are wall clock on a shared machine (an RTX 4090, one llama-server at a time for the last
runs), not a benchmark: other agents used the GPU during some runs, and the first runs were slowed
by several servers running at once. Source: `swarm\P25\runs\timing.jsonl`.

- The whole-talk Traditional Chinese pass over 678 Japanese cues took 590 s (0.87 s per cue), run
  alone. The whole-talk English pass (1623 s) ran next to three other servers and is not comparable.
- The second step of a pivot took about 88 s per target for 139 cues, and `direct` about 111 s
  (mean of 11 runs each). The pivot's second step is a little faster because its source is short.
- A pivot therefore costs one extra pass over the whole talk, paid once however many targets
  follow. When English is itself a requested target, the English pass is not extra.

## Findings that apply to every language

1. **The pivot did not win anywhere that the automatic numbers can see.** By the 0 to 5 score the
   English pivot ties `direct` in es, it, pt, ru, th, zh-CN and trails it in de, fr, id, vi (by
   Dice, vi reverses by 0.018, inside the noise). The zh-TW pivot trails in every language but
   zh-CN, where it ties. Errors that the pivot adds are visible in the outputs:
   a Japanese honorific for the speaker (a name plus さん or 様) went through English and came out
   as an unrelated word in Korean, and a term the English step guessed wrong (a "shell" for a
   Perforce "shelve") was carried on by the Korean and Russian second steps.
2. **Korean `direct` fails on 6 of 149 cues (4 percent).** The model keeps writing kana or Chinese
   characters inside the Korean, the pipeline rejects four replies, and the cue falls back to the
   Japanese. `via-en` kept no cue in Japanese but had 2 rejected replies. `swarm\P25\checks\problems.tsv`.
3. **Subtitle length is the largest P26 risk, and it is the same in every route.** Japanese cue
   splits and timing keep the cue count, but a Latin-script translation is about 2.3 characters per
   Japanese character. With the Japanese cues kept, 30 to 42 percent of Latin-script cues are wider
   than two 40-column lines (French 42 percent, Indonesian 38, German 36, Spanish 35, Portuguese 32,
   Italian 30), and 26 to 46 percent of the cues of de, es, fr, id, it, pt, ru and vi are over 17
   characters per second. Korean (4 percent over two lines) and Chinese (0) are fine. The ratio and rate columns are in `summary.tsv`.
4. **The Japanese length rule cannot be reused.** The current limit is 1.1 times the Japanese
   characters plus 8. Median ratios of output characters to Japanese characters are:
   Chinese 0.65, Korean 1.0, Thai 1.9, English 2.0, Russian 2.1, Vietnamese 2.1, Portuguese 2.3,
   Italian 2.3, Indonesian 2.3, German 2.3, Spanish 2.3, French 2.5. A first proposal for the
   maximum, 1.5 times the 90th percentile, is: zh-CN 1.4, ko 1.9, en 4.2, th 4.2, vi 4.5, ru 4.7,
   it 4.9, pt 5.0, es 5.0, de 5.1, id 5.3, fr 5.8, with the same slack of 8. This was not tested as
   a rejection rule.
5. **Names and product terms need a per-language glossary.** The default glossary holds the
   Japanese variants of Perforce and works: Perforce is written right in 4 of 4 sampled units in
   every language except the ones listed below. What it lacks is the terms the Taiwan table
   handles for zh-TW only (`backend/core/ja_terms.py`):
   - A Perforce "shelve" (シェルブ) was read as "shell" in English, German, Vietnamese and Thai,
     as "submission" in French, and transliterated as a nonsense word in Russian. Korean wrote it by
     sound (쉘브), which is acceptable.
   - A Perforce "stream" (ストリーム) became the ordinary word for a flow in French (flux) and
     Russian (поток), another word in Vietnamese, and "Stream" or 스트림 in German and Korean.
     Without a rule each language picks its own word.
   - A "branch" (ブランチ) is fine in most languages, but German wrote "Branche" (an industry)
     in one sentence where "Branch" or "Zweig" is right.
   - Person names and the company name come out in three or four spellings across routes, and a
     company variant that the glossary does not list (the glossary has 東陽, the recognition wrote 東洋)
     is transliterated by sound in the `direct` route, while the `via-en` route carried the English
     "Toyo Corporation" through. In the mixed talk a game character's name came out in three
     spellings across ten units in Russian and in Korean (in Russian one of them is the word for a
     fungus), because the recognition wrote it differently each time. Names need a talk-level list.
6. **A katakana repair garbles names.** When a cue fails four attempts, the pipeline's repair
   writes remaining katakana in Latin letters. In Korean and Thai output this produced forms
   such as a Hangul word with a Latin syllable inside it. It is a failure the script check cannot
   see, because Latin letters are allowed.

## Language-specific problems

Examples are invented to show the pattern. Evidence for each: `swarm\P25\checks\style.tsv`,
`terms.tsv`, `problems.tsv`, and the cue files under `swarm\P25\runs\full\`.

- **Korean politeness.** The registry prompt allows both 합니다 and 해요. `direct` output used
  합니다-type endings on 33 cues and 해요-type on 6, and two units mixed both inside one sentence
  group. Informal endings did not occur. Rule: write the 합니다 style only. Also: Latin letters
  inside a Hangul word (for example "리lease" in place of 릴리스) appeared once in `direct`.
- **Thai.** Cues carry spaces in 111 of 149 `direct` outputs, so `Wrap.THAI` has break points.
  Polite particles (ครับ and ค่ะ) appear on 6 cues in `direct`, none in `via-en`, so the register
  is mostly neutral. The model added an apology phrase that the Japanese does not have in one
  unit (a translation of "excuse the inconvenience"). Katakana names came out garbled (see
  finding 6). Thai has the lowest back-translation overlap in `direct` (0.349) and `via-en` (0.338).
- **Vietnamese.** No cue lacked diacritics in `direct`; `via-zh` lost them in 1 cue. The audience is
  addressed as "bạn" (11 `direct` cues) and a formal address appears on 1. A loanword was written with a
  wrong ending ("shellb"). Tokenisation is a non-issue here because Vietnamese is space-separated.
- **Russian.** Cases go wrong where Japanese has a topic particle: the subject is put in the
  genitive ("Сервера нужна стабильность" in place of "Серверу нужна стабильность" in a sentence
  of that shape), seen in one `direct` unit. Formal address (вы) occurs and ты does not.
- **German and French address.** German uses Sie on 20 cues and du on none. French uses vous on 21
  and tu on 1. Spanish and Italian show no address word in `direct` and Portuguese 6 cues, so
  their register is unconstrained. Add a rule: formal address throughout (Sie, vous, usted, Lei, você, вы).
- **Names and katakana.** Perforce and the other glossary names are kept in Latin letters in all
  languages. Terms the glossary does not list are the failure (finding 5).
- **Simplified Chinese.** Zero script failures in `direct`. Because zh-TW and zh-CN share the
  Chinese characters, `via-zh` equals `direct` here, but a plain character conversion of the zh-TW
  output was not tested and may be cheaper and more consistent with the zh-TW run.

## Decision per language

"Recommended route" is the route for the P26 default. "Experimental" means the UI should label the
language until a person who reads it has judged a sample.

| Language | Route | Experimental | Why | Prompt rules to add | Risks |
|---|---|---|---|---|---|
| English | direct | no | 0 failed; `direct` beats `via-zh` on 10 of 12 differing sentences; also the middle step of any pivot | none beyond the shared ones | Cue length 18 percent over two lines |
| Simplified Chinese | direct | no | 0 failed; ties `via-zh`; 0 cues over two lines | Simplified forms and Mainland terms exist in the prompt; add the Perforce terms | A character conversion from zh-TW was not tested |
| Korean | direct, with a per-cue fallback to the English pivot for a cue that fails | yes | 6 failed cues in `direct` (4 percent); `via-en` kept none in Japanese; highest Dice | 합니다 style only; never write kana or Chinese characters; write a name in Latin letters | Fallback needs a cue-level pivot; register drift; an unverified high Dice |
| Spanish | direct | no | 1 failed; tie with `via-en`; no address word appears | formal address (usted) | 35 percent of cues over two lines |
| French | direct | no | 0 failed; `direct` beat `via-zh` on 18 of 18 differing sentences | keep vous; keep the space before ? ! : ; | 42 percent of cues over two lines, the worst |
| German | direct | no | 0 failed; `direct` beats `via-en` 10 to 4 | keep Sie; never write "Branche" for a branch | 36 percent over two lines; compound words |
| Portuguese (Brazil) | direct | no | 0 failed; tie with `via-en` | one address form (você) | 32 percent over two lines |
| Italian | direct | no | 0 failed; tie with `via-en` | formal address (Lei) or voi, one of them | 30 percent over two lines |
| Russian | direct | no | 0 failed; tie with `via-en` | name the subject in the nominative; formal вы | Case errors; 30 percent over two lines |
| Vietnamese | direct | no | 0 failed; `direct` beats `via-en` 7 to 1 | a fixed address word; loanword spelling | A loanword garble; informal register only |
| Thai | direct | yes | lowest overlap; invented phrase; garbled names | no invented politeness or apology phrases; a fixed polite particle or none | No reader of Thai has checked a sample; the registry already marks it experimental |
| Indonesian | direct | no | 0 failed; `direct` beats `via-en` 8 to 4 | one address form (Anda) | 38 percent over two lines |

The English pivot is not recommended for any language. Reason: it ties `direct` in half the
languages, loses in the others, adds a pass over the talk, and spreads term errors. Keep it only as
the Korean fallback. The zh-TW pivot is not recommended for any language.

## Prompt and glossary rules to add for P26

1. Take the Japanese source rules of `JAPANESE_SOURCE` and replace the Taiwan-specific lines with
   per-target text. The harness's `generic_rules` shows the substitutions that were needed, and
   `tests/test_p25_multilang.py` shows they hold.
2. Add Perforce terms to the glossary for non-Chinese targets: shelve (シェルブ, シェルフ) stays
   "shelve"; stream (ストリーム) stays "stream" when it names the Perforce feature; branch has a
   fixed word per language; workflow has a fixed word per language.
3. Add the company name variants the recognition writes, and let the project give a list of names.
4. Make the script check count a reply written in the wrong Latin-script language and use a
   `needs_script` that works for an unspaced source.
5. Per language: Korean 합니다 only; formal address in de, fr, es, it, pt, ru; a single Thai
   register; Russian nominative for the subject; no invented apology.
6. Replace the Japanese density (1.1 times plus 8) with per-language values (finding 4) and give a
   Latin-script target a cue re-split or a wider line, since 30 to 42 percent of its cues do not fit
   two lines.
7. Do not leave Japanese or Chinese characters in the output of a failed cue: pivot that cue, or
   mark it, rather than keep the source.

## What this evidence does not show

- Whether any output is good Korean, Thai or Russian. No person read it. The root will run an opus
  judge on the outputs, which is also a model.
- Whether the English cues of a mixed talk use the same names as the translated Japanese cues.
- The strength of the Korean `direct` Dice, and any difference between routes smaller than the
  noise (about 0.04 in Dice).
- The pipeline's own length-based retries, which the harness turned off. A real run retries more.
- Stability across the whole talk: only 50 units were translated per route. The whole-talk English
  and zh-TW passes cover all cues.
- Speed as a benchmark.

## Blind page

`media\ja-multilang.html` shows 12 sentences in English, Simplified Chinese and Korean, each with
its routes as A, B and C in a random order. English has A and B only. The key is
`swarm\P25\ab\answer-key.tsv`, built by `swarm\P25\build_ab.py`. The page has not been judged.

## Reproduce

```
python scripts/p25_ja_multilang.py pick OUT
python scripts/p25_ja_multilang.py run OUT
python scripts/p25_ja_multilang.py back OUT
python scripts/p25_check.py OUT
```

`run` and `back` start one llama-server on a free port and stop it on exit. They resume: a file
that exists is not translated again. Set `P25_LLAMA_SERVER` to a wrapper to limit its CPU threads.
