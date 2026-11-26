import type { languages as en } from "../en/languages";

export const languages = {
  "lang.zh-TW": "繁體中文",
  "lang.zh-CN": "简体中文",
  "lang.en": "English",
  "lang.ja": "日本語",
  "lang.ko": "한국어",
  "lang.es": "Español",
  "lang.fr": "Français",
  "lang.de": "Deutsch",
  "lang.pt": "Português",
  "lang.it": "Italiano",
  "lang.ru": "Русский",
  "lang.vi": "Tiếng Việt",
  "lang.th": "ไทย",
  "lang.id": "Bahasa Indonesia",
} satisfies Record<keyof typeof en, string>;
