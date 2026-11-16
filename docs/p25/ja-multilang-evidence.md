# P25: evidence for translating a Japanese talk into 12 other languages

Status: evidence and a recommendation for the P26 scope. No human has judged the quality of any
output. One blind pass by a second model (opus) over a small sample is in "Second opinion (model
judge)". Every other number below comes from automatic checks, or from the same local model
(Qwen3-8B) grading its own back-translations. Read the numbers as a screen for failures, not as a
quality ranking.

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
  same with a Traditional Chinese (Taiwan) middle step, which is `translate.run` of main at
  `e0caedb` with the default glossary and nothing else (no summary notes and no request terms, which
  the app passes). It is not the output the app makes: only 55 of its 678 cues are identical to the
  older P23a output. English as a target has `direct` and `via-zh` only: its `direct` run is the
  middle step of `via-en`. The three routes do not share a prompt, see "Limits of the comparison".
- **Model and settings.** Qwen3-8B Q4_K_M on llama-server, the pipeline's seed, no thinking, 8192
  context, default glossary, `keep_english=True`, batches and retries of `translate.run`.
- **Back-translation.** For 30 of the 50 units (24 and 6), each route's output is translated back
  into Japanese by the same model. The committed script uses batches of 5 (`BACK_BATCH = 5`).
  The nine files made first (`direct` for de, en, es, fr, id, it, ko, pt, ru) were made with
  batches of 10, which overflowed the context at Thai, and the rest with 5. That is inferred from the
  author's note and the file times, since the files do not record the size, and the committed
  script does not reproduce those nine. The overlap with the Japanese source is the Dice
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
   Japanese length cannot hold a Latin-script language. The measured ratios are below. This holds
   for `direct` and `via-zh` only; `via-en` keeps its own length limits (see below);
4. keeps the target's script check, but `needs_script` counts English words in the Japanese, so for
   a Japanese source it is nearly always false and a reply left in English would pass the pipeline's
   check. This also holds for `direct` and `via-zh` only. `p25_check.py` forces the script check on
   every output afterwards, for all three routes.
5. adds English as a target (the registry has none) and a Chinese middle source for `via-zh`.

`direct.zh-TW` and the `via-zh` middle step are `translate.run` of main at `e0caedb` with the default
glossary only: no summary notes and no request terms, which the app passes. Only 55 of its 678 cues
match the older P23a output, so "zh-TW" below is a reference for this harness, not for the app.
Main has moved since (P35 changed `ja_terms.py`).

### Limits of the comparison

The routes are the same functions (`translate.run`, `build_request`) with three different source
prompts. Every difference below is in the code, and each one can move a number in the tables.

- **`direct`** uses `GENERIC_JA`: the Japanese rules without the Taiwan lines, no worked examples
  (the source prompt gets an empty examples table), no Japanese clean-up or term table, a kana check
  as its only source check, and no length limit.
- **`via-en`** uses `ENGLISH_SOURCE` unchanged. Its density is not turned off, so the target's own
  length limits apply, and its text has English words, so the pipeline's script check is on and a
  reply in the wrong script is retried. The verification measured the length limit at cue level: no `via-en` cue
  of 11 targets over 2 talks exceeds its maximum or minimum, so it probably changed no output. The
  script check is another matter. It gave `via-en` retries that `direct` did not get, which is part
  of why Korean `direct` has 6 failed cues against 2 for `via-en`. The size of that part is not
  measured.
- **`via-zh`** uses `ZH_SOURCE`, a prompt written for this harness (about 35 lines in the script)
  and never run as a product path, while `via-en` uses the tuned production English prompt. So "`direct`
  beats `via-zh`" compares the Japanese prompt with a hand-written one. It does not show that a
  Traditional Chinese middle step is worse than an English one, and the advice against the zh-TW
  pivot carries this confound.
- **Both pivots** drop the glossary's Japanese-variant entries (`keep_only`), while `direct` keeps
  them. `direct` also gets the Japanese hints for Perforce and the company name in its rules.
  Both favor `direct`.
- **Back-translation batches** differ for the nine `direct` files made first (10 against 5, see
  above). Whether batch size moves Dice or the score was not tested.
- **The same 30 sentences** are back-translated in every language, so the languages are not
  independent samples of the question "does `direct` beat a pivot".

Not part of the sample: the English cues of the mixed talk were not translated, so the plan's check
that the English and Japanese segments of one video use the same names was not run.

## Results by language and route

Counts are over the 149 sampled cues. "Failed" is a cue left in Japanese or English after four
attempts, plus any output the script check rejects. "Two lines" is a cue wider than two lines of 40
columns, with the Japanese cue timing and split kept. Dice and score are the back-translation
numbers (n = 30 sentences; for Korean all three routes use the shared 25 sentences and for Spanish
the shared 29, so the Korean and Spanish `via-en` and `via-zh` rows come from `routes.tsv`, not `summary.tsv`,
which holds, on each route's own 30 sentences, 0.390 (`via-en`) and 0.382 (`via-zh`) for Korean and
0.382 (`via-en`) and 0.362 (`via-zh`) for Spanish). The zh-TW row is main at `e0caedb`, `translate.run` only (see
above). Source: `swarm\P25\checks\summary.tsv` and `swarm\P25\checks\routes.tsv`.

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
| zh-TW (main at `e0caedb`, `translate.run` only) | direct | 0 | 0 | 0.422 | 4.87 |

### How much the numbers can tell

- Dice values only compare across routes of one language. Different targets back-translate with
  different loss. The per-sentence standard deviation of Dice is about 0.1 (0.079 to 0.138 by
  language and route), and the standard error of the paired difference between two routes on the
  same sentences is 0.013 to 0.03 (sentences with no kana in either route). `direct` against
  `via-en` is inside two standard errors in every language except Korean (+0.135, SE 0.031, 4.4
  SE) and Simplified Chinese (+0.038, SE 0.014, 2.8 SE). `direct` against `via-zh` is higher by
  0.043 to 0.070, which is more than two standard errors, in en, de, fr, it, pt, ru and vi, and by
  +0.143 (SE 0.030, 4.7 SE) in Korean. It is under two standard errors in es (+0.023, SE 0.019,
  1.2 SE), id (+0.034, 1.6 SE), th (+0.019, 1.4 SE) and zh-CN (-0.005, -0.4 SE). The 0.043 to
  0.070 range covers the seven languages named, not Korean.
- Two caveats bound every statement of that kind. First, all twelve languages are scored on the
  same 30 sentences, so "seven languages agree" is one sample of 30 sentences seen seven times, not
  seven independent confirmations. Second, there are 23 paired comparisons (11 against `via-en`, 12
  against `via-zh`). A difference of 2.2 to 2.8 standard errors (`via-zh` vi and de, `via-en` zh-CN)
  does not survive a correction for that many comparisons, which needs about 3.1. The ones that
  survive are en, fr, it, pt, ru and ko against `via-zh`, and ko against `via-en`. Dice and the
  score are also weak measures graded by the model that translated (see the top of the document).
- The 0 to 5 score separates routes only a little. In `routes.tsv`, `direct` scored higher than
  `via-zh` on more sentences than the reverse in every language except Thai (5 to 6) and Spanish
  (7 to 7, and the mean score of `via-zh` 4.414 is above `direct` 4.31), by wide
  margins in French (18 to 0), German (15 to 1) and Vietnamese (11 to 1). `direct` against `via-en`
  is close to even in es, it, pt, ru, th and zh-CN, and favours `direct` in de (10 to 4), fr (9 to 1),
  id (8 to 4) and vi (7 to 1).
- The Korean `direct` Dice of 0.514 is the one clear outlier (4.4 standard errors above `via-en`,
  +0.135 on the 25 shared sentences). It may be real, since Japanese and Korean share word order, or
  an artifact: there are no Han characters in the Korean `direct` back-translation set, and 5 of the
  30 sentences were dropped for kana, so the 0.514 is on the 25 that worked. Another suspect is the
  harness: the Korean `direct` back-translation was made (by inference, see above) in batches of 10 against 5 for the other
  two routes, and `via-en` has the pipeline's script retries that `direct` has not. It is an
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
   Dice, vi reverses by 0.018, inside the noise). The zh-TW pivot is behind `direct` by Dice in
   every language but zh-CN (-0.005); by score it is behind in every language except es, where it
   is ahead by mean score (4.414 against 4.31), th and zh-CN, where it ties. In es and th the Dice
   gap (+0.023, +0.019) is inside the noise. Read this with the limits above: the 30 sentences are
   shared by all languages, and the zh-TW route runs on a prompt written for the harness. Errors
   that the pivot adds are visible in the outputs:
   a Japanese honorific for the speaker (a name plus さん or 様) went through English and came out
   as an unrelated word in Korean, and a term the English step guessed wrong (a "shell" for a
   Perforce "shelve") was carried on by the Korean and Russian second steps.
2. **Korean `direct` fails on 6 of 149 cues (4 percent).** The model keeps writing kana or Chinese
   characters inside the Korean, the pipeline rejects four replies, and the cue falls back to the
   Japanese. `via-en` kept no cue in Japanese but had 2 rejected replies. Part of the difference is
   the harness: `via-en` keeps the pipeline's script check and its retries on a wrong-script reply,
   and `direct` has no such check (see "Limits of the comparison"). `swarm\P25\checks\problems.tsv`.
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
   every row of the tables except five, which have 3 of 4: `direct` ko, `via-zh` ko, `via-zh` th,
   `via-zh` zh-CN and the zh-TW reference. What it lacks is the terms the Taiwan table
   handles for zh-TW only (`backend/core/ja_terms.py`). The sample holds few units of each term, so
   each pattern below is a hint. Counts of sampled units (from `terms.tsv`): Perforce 4, shelve 1,
   stream 2, branch 5, workflow 2.
   - A Perforce "shelve" (シェルブ), 1 sampled unit, was read as "shell" in English, German, Vietnamese and Thai,
     as "submission" in French, and transliterated as a nonsense word in Russian. Korean wrote it by
     sound (쉘브), which is acceptable.
   - A Perforce "stream" (ストリーム), 2 sampled units, became the ordinary word for a flow in French (flux) and
     Russian (поток), another word in Vietnamese, and "Stream" or 스트림 in German and Korean.
     Without a rule each language picks its own word.
   - A "branch" (ブランチ), 5 sampled units, is fine in most languages, but German `direct` wrote
     "Branche" or "Branchen" (an industry) in 2 of the 5 units (119 and 596), and `via-zh` in 3,
     where "Branch" or "Zweig" is right. `via-en` did not.
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
  합니다-type endings (니다 or 까) on 43 cues and 해요-type (요) on 6, and two units mixed both inside
  one sentence group. `style.tsv` counts 49 formal and 0 informal, because its formal pattern also takes the 요 forms. Informal endings did not occur. Rule: write the 합니다 style only. Also: Latin letters
  inside a Hangul word (for example "리lease" in place of 릴리스) appeared once in `direct`.
- **Thai.** Cues carry spaces in 111 of 149 `direct` outputs, so `Wrap.THAI` has break points.
  Polite particles (ครับ and ค่ะ) appear on 6 cues in `direct`, none in `via-en`, so the register
  is mostly neutral. The model added an apology phrase that the Japanese does not have in one
  unit (a translation of "excuse the inconvenience"). Katakana names came out garbled (see
  finding 6). Thai `direct` is level with its own other routes on Dice (0.349 against 0.338 for
  `via-en`, 0.330 for `via-zh`, all inside two standard errors). Dice cannot compare Thai with the
  other languages, so Thai's low value is no reason by itself; the reasons are the invented phrase,
  the garbled names and that nobody read it.
- **Vietnamese.** No cue lacked diacritics in `direct`; `via-zh` lost them in 1 cue. The audience is
  addressed as "bạn" (11 `direct` cues) and a formal address appears on 1. A loanword was written with a
  wrong ending ("shellb"). Tokenisation is a non-issue here because Vietnamese is space-separated.
- **Russian.** Cases go wrong where Japanese has a topic particle: the subject is put in the
  genitive ("Сервера нужна стабильность" in place of "Серверу нужна стабильность" in a sentence
  of that shape), seen in one `direct` unit. Formal address (вы) occurs and ты does not.
- **German and French address.** German uses Sie on 20 cues and du on none. French uses vous on 21
  and tu on 1. Spanish and Italian show no address word in `direct` and Portuguese 6 cues, so
  their register is unconstrained. Add a rule: formal address throughout (Sie, vous, usted, Lei, você, вы).
- **Names and katakana.** Perforce and the other glossary names are kept in Latin letters in the
  `direct` route of every language but Korean and zh-TW (3 of 4 sampled units). Terms the glossary does not list are the failure (finding 5).
- **Simplified Chinese.** Zero script failures in `direct`. Because zh-TW and zh-CN share the
  Chinese characters, `via-zh` equals `direct` here, but a plain character conversion of the zh-TW
  output was not tested and may be cheaper and more consistent with the zh-TW run.

## Second opinion (model judge)

An opus model judged the routes blind, and then unblinded its verdicts with the key. It is a
model, not a native speaker. Method: the 12 windows of the blind page for English, Simplified
Chinese and Korean, and for the other nine languages 8 cues each (a seeded script, the same cue
index in all three routes), judged from a file with no route names. The judge did not read
`checks\*`. Cues are mid-sentence fragments, so alignment drift adds noise to every count. The judge
is strongest in English and Chinese, good in Korean, French, German, Spanish, Russian, Italian and
Portuguese, and weak in Thai, Vietnamese and Indonesian (low confidence). Files:
`swarm\P25\judge\report.md`, `part1.tsv`, `part2.tsv` and their `-unblinded` copies.

Best route per sentence:

| Language | n | direct | via-en | via-zh | The judge's pick |
|---|---|---|---|---|---|
| English | 12 | 8 | n/a | 3 | direct |
| Simplified Chinese | 12 | 6 | 2 | 4 | direct |
| Korean | 12 | 3 | 4 | 5 | no route usable as is |
| Spanish | 8 | 2 | 2 | 3 | no clear winner |
| French | 8 | 3 | 3 | 2 | no clear winner |
| German | 8 | 4 | 3 | 1 | direct (weak) |
| Portuguese | 8 | 0 | 4 | 4 | not `direct` (weak) |
| Italian | 8 | 2 | 1 | 5 | `via-zh` (weak) |
| Russian | 8 | 5 | 1 | 2 | direct (weak) |
| Vietnamese | 8 | 4 | 1 | 3 | direct (weak, low confidence) |
| Thai | 8 | 2 | 4 | 2 | `via-en` (weak, low confidence) |
| Indonesian | 8 | 4 | 1 | 2 | direct (weak, low confidence) |

Rows do not always add up to n because a sentence can be a tie. Over the 72 cues of the nine
languages the totals are `direct` 26, `via-en` 20, `via-zh` 24, and 2 all tied. A gap of one or
two cues out of 8 is noise, and the statistical significance at n = 8 was not judged.

- **English and Simplified Chinese.** `direct` is best in both (8 of 12, 6 of 12). In zh-CN `via-zh`
  leaks Taiwan terms (for example 支援, 影像, 原始码) and `via-en` copies the English middle step's
  errors. Russian leans `direct` (5 of 8 cues), which is a lead, not a separation.
- **Korean.** No route is usable as is. `direct` was the worst in the sample (3 of 12) and the only
  route that left Japanese on screen (2 of the 12 windows). Mixed scripts and mixed registers
  appear. `via-en` leaves an English tail and `via-zh` a Chinese tail and garbled names, and every
  route garbles the game character's name. The English-pivot fallback design stands, but the claim
  "`direct` is best for Korean" is not supported.
- **The other nine languages.** The routes are about even and 8 cues per language cannot separate
  them. `direct` as the default rests on simplicity and risk (one pass, pivot errors do not
  compound, no Chinese or English leakage), not on measured quality. "Never `via-zh`" holds for
  zh-CN. Elsewhere it is a cost and leak-risk rule, not a quality finding. Portuguese leaned against
  `direct` (0 of 8) and needs a larger sample before a decision. Thai stays experimental.
- **Typical errors the judge named.** Names and ASR garbles, "Branchen" for a branch in German,
  gender and agreement slips in French and Portuguese, register switches (du and Sie in German,
  해요 and 합니다 in Korean), calques in zh-CN.
- **Cannot judge.** Fluency and register in Thai, Vietnamese and Indonesian, on-screen timing, and
  faithfulness of a single cue when the routes split a sentence differently.

This agrees with the automatic numbers on `direct` for English, zh-CN and Russian, and on the
Korean failure mode. It disagrees with them on Korean `direct` (the high Dice does not mean a good
translation) and, weakly, on Portuguese, Italian and Thai.

## Decision per language

"Recommended route" is the route for the P26 default. "Experimental" means the UI should label the
language until a person who reads it has judged a sample. Where the model judge's sample is small
(8 cues), the route in the table is a default chosen for simplicity and risk, not a measured
winner.

| Language | Route | Experimental | Why | Prompt rules to add | Risks |
|---|---|---|---|---|---|
| English | direct | no | 0 failed; `direct` beats `via-zh` on 10 of 12 differing sentences; also the middle step of any pivot | none beyond the shared ones | Cue length 18 percent over two lines |
| Simplified Chinese | direct | no | 0 failed; ties `via-zh`; 0 cues over two lines | Simplified forms and Mainland terms exist in the prompt; add the Perforce terms | A character conversion from zh-TW was not tested |
| Korean | no route is usable as is; `direct` is the base, with a per-cue fallback to the English pivot for a cue that fails | yes | 6 failed cues in `direct` (4 percent); `via-en` kept none in Japanese (but has the script retries `direct` lacks); `direct` Dice is the one outlier, +0.135 (4.4 SE), yet the judge ranked `direct` worst (3 of 12) and the only route that left Japanese on screen | 합니다 style only; never write kana or Chinese characters; write a name in Latin letters | Fallback needs a cue-level pivot and a script check for leftover Chinese characters and English; register drift; an unverified high Dice; every route garbles names |
| Spanish | direct | no | 1 failed; tie with `via-en`; no address word appears | formal address (usted) | 35 percent of cues over two lines |
| French | direct | no | 0 failed; `direct` beat `via-zh` on 18 of 18 differing sentences | keep vous; keep the space before ? ! : ; | 42 percent of cues over two lines, the worst |
| German | direct | no | 0 failed; `direct` beats `via-en` 10 to 4 | keep Sie; never write "Branche" for a branch | 36 percent over two lines; compound words |
| Portuguese (Brazil) | direct, as a default | no | 0 failed; tie with `via-en` by the numbers; the judge leaned against `direct` (0 of 8), so sample more | one address form (você) | 32 percent over two lines |
| Italian | direct, as a default | no | 0 failed; tie with `via-en`; the judge leaned `via-zh` (5 of 8, weak) | formal address (Lei) or voi, one of them | 30 percent over two lines |
| Russian | direct | no | 0 failed; tie with `via-en` | name the subject in the nominative; formal вы | Case errors; 30 percent over two lines |
| Vietnamese | direct | no | 0 failed; `direct` beats `via-en` 7 to 1 | a fixed address word; loanword spelling | A loanword garble; informal register only |
| Thai | direct, as a default | yes | invented phrase; garbled names; level with its other routes on Dice; the judge (weak in Thai) leaned `via-en` 4 of 8; no native reader | no invented politeness or apology phrases; a fixed polite particle or none | No reader of Thai has checked a sample; the registry already marks it experimental |
| Indonesian | direct | no | 0 failed; `direct` beats `via-en` 8 to 4 | one address form (Anda) | 38 percent over two lines |

What the two kinds of evidence support together:

- `direct` is clearly the best route in English and Simplified Chinese (the judge: 8 of 12 and 6
  of 12), and it leads in Russian (5 of 8, weak).
- Korean has no usable route. `direct` fails on 6 of 149 cues and was the worst in the judge's
  sample, so do not write that `direct` is best for Korean. Keep the English pivot as a per-cue
  fallback for the cues that fail, and add a script check that catches leftover Chinese characters
  and English words, since the pivot leaves an English tail.
- For the other languages the routes are about even (judge: `direct` 26, `via-en` 20, `via-zh` 24
  of 72 cues; the automatic numbers: `direct` at least as good in this harness on 30 shared
  sentences, not surviving a correction for 23 comparisons everywhere). `direct` is the default
  because it is one pass, pivot errors do not compound and nothing leaks from another language. That
  is a rule of simplicity and risk, not measured quality. Portuguese needs a larger sample.
- The English pivot ties `direct` in half the languages, loses by score in others, adds a pass over
  the talk, and spreads term errors, so it is not recommended on this evidence apart from the Korean
  fallback, which rests on 6 failed cues in one talk and on a `via-en` route that has the script
  retries.
- The zh-TW pivot is not recommended, and for zh-CN the judge saw Taiwan terms leak. For the other
  languages that advice is a cost rule with this confound: the route ran on a prompt written for
  the harness and on a middle step that is not what the app produces, so the result does not show
  that a Traditional Chinese middle step is worse than an English one.

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
   mark it, rather than keep the source. The pivoted Korean cue also needs a script check for
   leftover Chinese characters and English words.

## What this evidence does not show

- Whether any output is good Korean, Thai or Russian. No person read it. The opus judge is also a
  model, weak in Thai, Vietnamese and Indonesian, and its sample is 12 windows for en, zh-CN and ko
  and 8 cues for the other nine languages, too small to separate the routes in those nine.
- Whether the English cues of a mixed talk use the same names as the translated Japanese cues.
- The strength of the Korean `direct` Dice, and any difference between routes smaller than the
  noise (about 0.04 in Dice).
- Seven independent confirmations. The 30 back-translated sentences are the same in every language,
  and the comparisons that reach 2.2 to 2.8 standard errors (`via-zh` vi and de, `via-en` zh-CN) do
  not survive a correction for 23 comparisons.
- That a pivot is worse in itself. The three routes run on three different source prompts (see
  "Limits of the comparison"), and the zh-TW middle step is not the app's.
- The pipeline's own length-based retries, which the harness turned off. A real run retries more.
- Stability across the whole talk: only 50 units were translated per route. The whole-talk English
  and zh-TW passes cover all cues.
- Speed as a benchmark.

## Blind page

`media\ja-multilang.html` shows 12 sentences in English, Simplified Chinese and Korean, each with
its routes as A, B and C in a random order. English has A and B only. The key is
`swarm\P25\ab\answer-key.tsv`, built by `swarm\P25\build_ab.py`. The opus judge read its 12 sentences blind (see "Second opinion"). No human has judged it, and it has not been shown to the operator.

## Reproduce

```
python scripts/p25_ja_multilang.py pick OUT
python scripts/p25_ja_multilang.py run OUT
python scripts/p25_ja_multilang.py back OUT
python scripts/p25_check.py OUT
```

The scripts name the two talks by their paths under `.work` of the author's checkout (`TALKS` in
`scripts/p25_ja_multilang.py`), so they do not run elsewhere without editing that table.

`run` and `back` start one llama-server on a free port and stop it on exit. They resume: a file
that exists is not translated again. Set `P25_LLAMA_SERVER` to a wrapper to limit its CPU threads.
