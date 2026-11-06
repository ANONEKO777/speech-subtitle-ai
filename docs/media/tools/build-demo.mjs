// Turns the two screencasts into docs/media/demo.mp4 and poster.png with amber-on-graphite captions.
// node docs/media/tools/build-demo.mjs <shots-dir> <work-dir> <out-dir> <hero.png>
// <shots-dir> holds cast-import/, marks-import.json, and tour/ (cast-tour/, marks-tour.json).
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const [shots, work, out, hero] = process.argv.slice(2);
if (!shots || !work || !out || !hero) throw new Error("usage: build-demo.mjs <shots> <work> <out> <hero.png>");
mkdirSync(work, { recursive: true });
mkdirSync(out, { recursive: true });

const FONT = "C\\:/Windows/Fonts/segoeuib.ttf";
const FONT_LIGHT = "C\\:/Windows/Fonts/segoeui.ttf";
const AMBER = "0xf0b23e";
const GRAPHITE = "0x0b0b0d";
const FPS = 30;
const W = 1280;
const BAR = 80;
const H = 720 + BAR;
const ffmpeg = (...args) => execFileSync("ffmpeg", ["-v", "error", "-y", ...args], { stdio: "inherit" });

const marksImport = JSON.parse(readFileSync(join(shots, "marks-import.json"), "utf8"));
const marksTour = JSON.parse(readFileSync(join(shots, "tour", "marks-tour.json"), "utf8"));

function castToVideo(dir, file) {
  ffmpeg("-f", "concat", "-safe", "0", "-i", join(dir, "list.txt"), "-vf", `fps=${FPS},scale=${W}:720:flags=lanczos,format=yuv420p`, "-c:v", "libx264", "-crf", "14", "-preset", "fast", file);
}
const importVideo = join(work, "import.mp4");
const tourVideo = join(work, "tour.mp4");
castToVideo(join(shots, "cast-import"), importVideo);
castToVideo(join(shots, "tour", "cast-tour"), tourVideo);

const caption = (text) =>
  `pad=${W}:${H}:0:0:color=${GRAPHITE},drawbox=x=0:y=720:w=${W}:h=1:color=0x2a2a30@1:t=fill,` +
  `drawtext=fontfile='${FONT}':text='${text}':fontcolor=${AMBER}:fontsize=30:x=(w-text_w)/2:y=720+(${BAR}-text_h)/2`;

const pieces = [];
function piece(name, source, from, to, text, speed = 1) {
  const file = join(work, `${name}.mp4`);
  const filter = `${speed === 1 ? "" : `setpts=PTS/${speed},fps=${FPS},`}${caption(text)}`;
  ffmpeg("-ss", String(from), "-t", String(to - from), "-i", source, "-vf", filter, "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", String(FPS), file);
  pieces.push(file);
}
function card(name, seconds, title, line, small) {
  const file = join(work, `${name}.mp4`);
  const filter =
    `drawtext=fontfile='${FONT}':text='${title}':fontcolor=${AMBER}:fontsize=64:x=(w-text_w)/2:y=h/2-70,` +
    `drawtext=fontfile='${FONT_LIGHT}':text='${line}':fontcolor=0xe8e8ec:fontsize=30:x=(w-text_w)/2:y=h/2+30,` +
    `drawtext=fontfile='${FONT_LIGHT}':text='${small}':fontcolor=0x8a8a93:fontsize=22:x=(w-text_w)/2:y=h-90,fade=t=in:d=0.5,fade=t=out:st=${seconds - 0.5}:d=0.5`;
  ffmpeg("-f", "lavfi", "-i", `color=c=${GRAPHITE}:s=${W}x${H}:r=${FPS}:d=${seconds}`, "-vf", filter, "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", file);
  pieces.push(file);
}

const i = marksImport;
const sped = Math.max(4, i.player - 0.4 - (i.click + 0.9));
const speed = Math.max(2, Math.round(sped / 9));
card("title", 3, "Video Subtitle Translator", "English talks in, well-timed subtitles out", "Runs on your own GPU. Nothing leaves this PC by default.");
piece("import-a", importVideo, 0.8, i.click + 0.9, "Pick a talk video");
piece("import-b", importVideo, i.click + 0.9, i.player - 0.4, "Speech, translation and summary run locally (sped up)", speed);
const t = marksTour;
const tour = [
  ["play", "modes", "Bilingual subtitles under the video"],
  ["modes", "edit", "English only, Chinese only, or both"],
  ["edit", "summary", "Fix a line. Your edit survives a re-translation"],
  ["summary", "lang", "Key points and chapters, one click to jump"],
  ["lang", "export", "The same talk in Japanese"],
  ["export", "end", "Export SRT, ASS, VTT and the summary"],
];
tour.forEach(([a, b, text]) => piece(`tour-${a}`, tourVideo, t[a], t[b], text));
card("outro", 3.5, "Local first. Open source.", "AGPL-3.0-or-later", "Demo video from the NASA State of NASA 2023 address, NASA media");

const list = join(work, "concat.txt");
import("node:fs").then(({ writeFileSync }) => {
  writeFileSync(list, pieces.map((p) => `file '${p.replaceAll("\\", "/")}'`).join("\n") + "\n");
  const demo = join(out, "demo.mp4");
  ffmpeg("-f", "concat", "-safe", "0", "-i", list, "-c:v", "libx264", "-crf", "24", "-preset", "slower", "-pix_fmt", "yuv420p", "-r", String(FPS), "-movflags", "+faststart", "-an", demo);
  ffmpeg("-i", hero, "-vf", `scale=${W}:720:flags=lanczos,${caption("Bilingual subtitles for long English talks")}`, "-frames:v", "1", join(work, "poster-raw.png"));
  console.log("demo", demo, "poster source", join(work, "poster-raw.png"));
});
