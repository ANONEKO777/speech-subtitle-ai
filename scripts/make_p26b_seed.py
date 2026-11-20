"""Build a finished Japanese project with three targets for the P26b window checks.

    uv run python scripts/make_p26b_seed.py OUT [NAME [TARGET ...]]

It makes a 30 s colour video with ffmpeg and runs the real pipeline over it with the ports a test
uses: no model runs. The Japanese talk is eight invented sentences, and the translations are
written here by hand. Two cues fail on purpose: the English target leaves cue 6 empty, and the
Korean one shows cue 4 in English and leaves cue 6 empty, as the routes of the registry do.

`OUT/NAME.mp4` (`talk-demo-ja`, targets zh-TW en ko, by default) is the video to import and
`OUT/projects/<id>` the project folder to copy
into the app's projects folder (`project.json` keeps the video path, so the window plays it).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_ja_targets import TargetFakes  # noqa: E402
from test_japanese import ja_settings  # noqa: E402

from backend.core.languages import get as get_language  # noqa: E402
from backend.core.model import Word  # noqa: E402
from backend.core.pipeline import run  # noqa: E402
from backend.core.projects import project_id  # noqa: E402
from backend.llm.client import Message  # noqa: E402

SENTENCES = [
    "今日は、町の祭りについてお話しします。",
    "毎年、秋に広場で開かれます。",
    "子どもたちは、手作りのランタンを持って歩きます。",
    "去年は、三百人以上の人が集まりました。",
    "準備には、ボランティアの力が欠かせません。",
    "雨の日は、体育館に会場を移します。",
    "来年は、音楽の時間をもっと増やしたいです。",
    "ご清聴ありがとうございました。",
]
TRANSLATIONS = {
    "zh-TW": [
        "今天我要來談談鎮上的祭典。",
        "每年秋天都會在廣場舉辦。",
        "孩子們提著自己做的燈籠走過街道。",
        "去年有三百多人聚在一起。",
        "籌備工作少不了志工的力量。",
        "下雨的時候，會場會移到體育館。",
        "明年我們想增加更多音樂的時間。",
        "感謝大家聆聽。",
    ],
    "en": [
        "Today I will talk about the town festival.",
        "It is held in the square every autumn.",
        "The children walk with lanterns they made by hand.",
        "Last year more than three hundred people came.",
        "The preparation cannot do without volunteers.",
        "On a rainy day we move the venue to the gym.",
        "Next year we want to add more time for music.",
        "Thank you for listening.",
    ],
    "ko": [
        "오늘은 마을 축제에 대해 말씀드리겠습니다.",
        "매년 가을에 광장에서 열립니다.",
        "아이들은 손으로 만든 등불을 들고 걷습니다.",
        "",
        "준비에는 자원봉사자의 힘이 꼭 필요합니다.",
        "",
        "내년에는 음악 시간을 더 늘리고 싶습니다.",
        "경청해 주셔서 감사합니다.",
    ],
}
FAILS = {"en": {5}, "ko": {3, 5}}
STEP_S = 3.7
SPEAK_S = 2.2


class Demo(TargetFakes):
    """Translates the eight sentences by the table above, and fails the cues named in `FAILS`."""

    def translate(self, messages: Sequence[Message], temperature: float) -> str:
        self.translate_calls += 1
        system = messages[0]["content"]
        code = next(
            c
            for c in ("ko", "zh-CN", "en", "zh-TW")
            if f"into {get_language(c).prompt.target}." in system
        )
        key = get_language(code).prompt.key
        out: list[dict[str, object]] = []
        for entry in json.loads(messages[1]["content"])["translate"]:
            pieces = re.split(r"(\[\[\d+\]\])", entry["ja"])
            text = ""
            for piece in pieces:
                if re.fullmatch(r"\[\[\d+\]\]", piece):
                    text += piece
                elif piece.strip() in SENTENCES:
                    at = SENTENCES.index(piece.strip())
                    bad = at in FAILS.get(code, set())
                    text += (
                        "ブランチ" if bad else (TRANSLATIONS[code][at] or TRANSLATIONS["en"][at])
                    )
            out.append({"id": entry["id"], key: text})
        return json.dumps({"translations": out}, ensure_ascii=False)


def make_video(path: Path) -> None:
    seconds = STEP_S * len(SENTENCES)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x1f3a5f:s=1280x720:r=10:d={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=330:duration={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    name = sys.argv[2] if len(sys.argv) > 2 else "talk-demo-ja"
    targets = sys.argv[3:] or ["zh-TW", "en", "ko"]
    out.mkdir(parents=True, exist_ok=True)
    video = out / f"{name}.mp4"
    make_video(video)
    folder = out / "projects" / project_id(video)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    words = [
        Word(text, int(i * STEP_S * 1000) + 200, int((i * STEP_S + SPEAK_S) * 1000) + 200, "ja")
        for i, text in enumerate(SENTENCES)
    ]
    fakes = Demo(words=words)
    for code in targets:
        run(video, folder, ja_settings(target_lang=code), fakes.ports())
    print(f"project folder {folder}")
    print(f"import this video {video}")


if __name__ == "__main__":
    main()
