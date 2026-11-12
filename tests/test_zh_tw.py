from __future__ import annotations

import json

import pytest

from backend.core.fillers import drop_fillers, strip_markdown_emphasis
from backend.core.languages import get
from backend.core.model import Cue
from backend.core.translate import (
    Batch,
    ReplyError,
    Unit,
    build_request,
    parse_reply,
)
from backend.core.zh_tw import (
    SIMPLIFIED_IN_BIG5,
    SIMPLIFIED_ONLY,
    in_big5,
    simplified_chars,
    taiwan_terms,
    taiwan_terms_from_english,
)

ZH_TW = get("zh-TW")

TAIWAN_SENTENCES = [
    "這個演算法很快。",
    "透過更好的資料結構或演算法讓事情變得可能。",
    "世界面臨新的挑戰。",
    "他的個性能讓人放心。",
    "這是一種特性能夠被重複使用。",
    "我們用程式碼和原始碼來溝通。",
    "點擊介面上的按鈕，使用者就能看到影片。",
    "地球繞著太陽運行。",
    "這台機器運行良好。",
    "大數據改變了世界，數據機也還在用。",
    "零組件供應商和小組件都換了。",
    "針線程序很細。",
    "我們在內存在的問題上很小心。",
    "他們在路障設置了崗哨。",
    "我們設置了新的廚房。",
    "主程序員負責審查。",
    "我相信息不會洩漏。",
    "預設值是記憶體、螢幕和滑鼠的設定。",
]


KITCHEN_CUES = [
    "成果負責任，並思考我們的廚房設置，對吧？",
    "根據你如何設置你的主廚、副廚，你知道的，他們所使用的設備種類，",
    "你真的可以設置，嗯，一個米其林廚房或一個軟體工廠，其中，嗯，因為你花了很多",
    "我們正在以一種有邏輯的方式設置我們的廚房，對吧？為了",
    "嗯，嗯，我想你可以透過Grokbot為自己設置這個個人米其林廚房，",
    "[[1]]我們正在訓練他們，[[2]]我們正在設置[[3]]廚房。",
]

MAINLAND_CUES = [
    (
        "我今天這場演講的論點和主張是，如果你為你的代理設置一個非常好的環境，",
        "我今天這場演講的論點和主張是，如果你為你的代理設定一個非常好的環境，",
    ),
    (
        "你可以花時間去設置你的[[169]]程式碼庫，以一種方式，",
        "你可以花時間去設定你的[[169]]程式碼庫，以一種方式，",
    ),
    ("我想，是如何設置它，讓即使代理人，嗯，", "我想，是如何設定它，讓即使代理人，嗯，"),
    ("它們可以運行[[87]]應用程式，但只是在猜測", "它們可以執行[[87]]應用程式，但只是在猜測"),
    ("不允許在渲染執行緒上運行。我們有意地", "不允許在渲染執行緒上執行。我們有意地"),
    ("不允許在渲染線程上運行。我們有意地", "不允許在渲染執行緒上執行。我們有意地"),
    ("嗯，會導致運行緩慢的程式碼。而，嗯，在渲染", "嗯，會導致執行緩慢的程式碼。而，嗯，在渲染"),
    ("telemetry 關於應用程序的表現。嗯，因此，", "telemetry 關於應用程式的表現。嗯，因此，"),
    (
        "例如Grogbot常規程序，讓你可以訂閱，你知道的，Slack線程，到",
        "例如Grogbot常規程式，讓你可以訂閱，你知道的，Slack討論串，到",
    ),
    ("你可以在設置中調整，也可以進行設置。", "你可以在設定中調整，也可以進行設定。"),
    ("設置好之後，程式運行在雲端，你也能運行它。", "設定好之後，程式執行在雲端，你也能執行它。"),
    ("我們用 Docker 運行中的容器，不用運行程式。", "我們用 Docker 執行中的容器，不用執行程式。"),
    ("這是主線程，也是工作線程。", "這是主執行緒，也是工作執行緒。"),
    ("就像它能運行", "就像它能執行"),
    ("它們可以運行[[88]]", "它們可以執行[[88]]"),
    ("來運行 Grochbot。我們", "來執行 Grochbot。我們"),
    ("某些在主程式或主執行緒中運行的程式碼", "某些在主程式或主執行緒中執行的程式碼"),
    ("不允許在渲染執行緒中運行。我們", "不允許在渲染執行緒中執行。我們"),
    ("不允許運行在渲染執行緒上。我們", "不允許執行在渲染執行緒上。我們"),
    ("導致運行速度變慢。", "導致執行速度變慢。"),
    ("是運行整個 Dune 應用程式的東西", "是執行整個 Dune 應用程式的東西"),
    ("我注意到，當我查看實際的工具調用時，", "我注意到，當我查看實際的工具呼叫時，"),
    (
        "我們有一個巨大的單一倉庫，我們有，我也不清楚，",
        "我們有一個巨大的單一儲存庫，我們有，我也不清楚，",
    ),
    ("能為建立一個技能團隊倉庫做出貢獻", "能為建立一個技能團隊儲存庫做出貢獻"),
    ("我們關於代理視窗和 Rockbot 等的反饋。", "我們關於代理視窗和 Rockbot 等的回饋。"),
    (
        "因此我有了創建一種稱為特徵地圖的東西的想法，",
        "因此我有了建立一種稱為特徵地圖的東西的想法，",
    ),
    (
        "你懂的，像是導入或阻斷導入那些不應該被導入的依賴項。",
        "你懂的，像是匯入或阻斷匯入那些不應該被匯入的依賴項。",
    ),
    ("在 Grochbot 虛擬機器上運行。當然", "在 Grochbot 虛擬機器上執行。當然"),
]

KEPT_PROCEDURES = [
    "這違反了程序正義。",
    "依照法律程序處理。",
    "他走完了手續程序。",
    "標準作業程序很重要。",
    "針線程序很細。",
]


ENGLISH_TALK_TERMS = [
    ("代理無法訪問你的資料庫。", "代理無法存取你的資料庫。"),
    ("你需要訪問權限。", "你需要存取權限。"),
    ("我創建了一個新的技能。", "我建立了一個新的技能。"),
    ("我們把資料可視化。", "我們把資料視覺化。"),
    ("記錄存儲在雲端。", "記錄儲存在雲端。"),
    ("它能搜索整個程式碼庫。", "它能搜尋整個程式碼庫。"),
    ("暴露一個 API 接口。", "暴露一個 API 介面。"),
    ("我查看了實際的工具調用。", "我查看了實際的工具呼叫。"),
    ("調用 API，再用 API 調用它。", "呼叫 API，再用 API 呼叫它。"),
    ("透過 API 調用，調用了模型。", "透過 API 呼叫，呼叫了模型。"),
    ("訪問 API 和資料庫。", "存取 API 和資料庫。"),
    ("導入和依賴圖，被導入至渲染執行緒。", "匯入和依賴圖，被匯入至渲染執行緒。"),
    ("從一個目錄導入到另一個目錄的程式碼。", "從一個目錄匯入到另一個目錄的程式碼。"),
    (
        "像是導入或阻斷導入那些不應該被導入的依賴項。",
        "像是匯入或阻斷匯入那些不應該被匯入的依賴項。",
    ),
    ("導入模組，也導入了套件。", "匯入模組，也匯入了套件。"),
    ("暴露一個 API 接口，不是 USB 接口。", "暴露一個 API 介面，不是 USB 接口。"),
    ("它會調用函式，再次調用自己。", "它會呼叫函式，再次呼叫自己。"),
    ("我做過效能優化。", "我做過效能最佳化。"),
    ("它優化了記憶體和速度。", "它最佳化了記憶體和速度。"),
    ("介面並不是為此優化過的。", "介面並不是為此最佳化過的。"),
    ("許多人給我們反饋。", "許多人給我們回饋。"),
    ("這段程式碼被導入到渲染執行緒。", "這段程式碼被匯入到渲染執行緒。"),
    ("我們有一個巨大的單一倉庫。", "我們有一個巨大的單一儲存庫。"),
    ("把技能放進團隊的倉庫，再提交 PR。", "把技能放進團隊的儲存庫，再提交 PR。"),
]

ENGLISH_TALK_KEPT = [
    "我們訪問了那家公司的創辦人。",
    "他們去訪問了東京的工廠。",
    "他創建了這家公司，也共同創建了這個團隊。",
    "這座城市創建於十二世紀。",
    "他是這家公司的創建者。",
    "存儲器的容量不夠。",
    "警方搜索了整棟房子。",
    "搜索隊找到了他們。",
    "地毯式搜索花了一整天。",
    "這台主機的 USB接口壞了。",
    "這台主機的 USB 接口壞了。",
    "HDMI 接口和 Type-C 接口。",
    "USB-C 接口很鬆。",
    "我訪問了系統管理員。",
    "訪問了資料科學家。",
    "她訪問了資料中心的工程師。",
    "訪問了伺服器農場的工人。",
    "他導入了新制度。",
    "公司導入了新流程，學校導入了新課程。",
    "導入了新系統。",
    "我們導入 AI，公司導入 ERP，也導入 ISO 標準。",
    "我們導入了 Git，導入了 Docker。",
    "導入了檔案管理系統。",
    "導入電子病歷，導入太陽能。",
    "電流被導入地面。",
    "把水導入水池。",
    "創建了一個新的樂團。",
    "他們創建了新的流派。",
    "搜索與救援任務。",
    "充電接口很鬆。",
    "他是我們的接口人。",
    "能源碼頭的工人很多。",
    "資源碼不在這裡。",
    "電信運營商的網路。",
    "單元資料不在這裡。",
    "公司調用了所有人手去救火。",
    "指揮部調用了軍隊。",
    "電路的反饋迴路很穩定。",
    "政府優化了營商環境。",
    "我們優化組織架構。",
    "服務優化是下一季的重點。",
    "公司導入新制度之後變好了。",
    "導入期很長。",
    "這本書的導言很短。",
    "他引導入門的新手。",
    "倉庫裡的貨物堆到天花板。",
    "我們把資料放進倉庫。",
    "物流倉庫的貨架很高。",
    "把資料視覺化、存取、儲存、搜尋、回饋。",
]


def reply_for(zh: str, en: str = "") -> str:
    en = en or " ".join(["word"] * len(zh))
    cues = [Cue(1, 0, 1000, en)]
    reply = json.dumps({"translations": [{"id": 1, "zh": zh}]}, ensure_ascii=False)
    return parse_reply(reply, build_request(cues, Batch((Unit(0, 1),))), cues)[1]


@pytest.mark.parametrize("zh", TAIWAN_SENTENCES)
def test_correct_taiwan_text_is_left_alone(zh: str) -> None:
    assert taiwan_terms(zh) == zh
    assert reply_for(zh) == zh


@pytest.mark.parametrize(
    ("mainland", "taiwan"),
    [
        ("這個算法很快", "這個演算法很快"),
        ("程式代碼和源代碼", "程式碼和原始碼"),
        ("閱讀代碼", "閱讀程式碼"),
        ("系統性能很好", "系統效能很好"),
        ("高性能計算", "高效能計算"),
        ("用戶界面", "使用者介面"),
        ("統計數據和數據庫", "統計資料和資料庫"),
        ("多線程和主線程", "多執行緒和主執行緒"),
        ("安裝插件", "安裝外掛"),
        ("拆成組件", "拆成元件"),
        ("運行在主程序上", "執行在主程式上"),
        ("運行應用程式", "執行應用程式"),
        ("你教你的代理如何運行你的應用程式", "你教你的代理如何執行你的應用程式"),
        ("設置環境", "設定環境"),
        ("你為你的代理設置環境", "你為你的代理設定環境"),
        ("設置你的程式碼庫", "設定你的程式碼庫"),
        ("視頻、軟件、信息、網絡", "影片、軟體、資訊、網路"),
        ("默認服務器和內存", "預設伺服器和記憶體"),
        ("屏幕、鼠標、調試", "螢幕、滑鼠、除錯"),
        ("拉取請求", "合併請求"),
        ("你可以閱讀源碼。", "你可以閱讀原始碼。"),
        ("我們的運營團隊很小。", "我們的營運團隊很小。"),
        ("每個檔案都有元數據。", "每個檔案都有中繼資料。"),
        ("每個檔案都有元資料。", "每個檔案都有中繼資料。"),
    ],
)
def test_mainland_terms_become_taiwan_terms(mainland: str, taiwan: str) -> None:
    assert taiwan_terms(mainland) == taiwan


@pytest.mark.parametrize(("mainland", "taiwan"), ENGLISH_TALK_TERMS)
def test_mainland_words_of_an_english_talk_become_taiwan_words(mainland: str, taiwan: str) -> None:
    assert taiwan_terms_from_english(mainland) == taiwan
    assert taiwan_terms_from_english(taiwan) == taiwan
    assert ZH_TW.terms_from("en", mainland) == taiwan
    assert reply_for(mainland) == taiwan


@pytest.mark.parametrize(("mainland", "taiwan"), ENGLISH_TALK_TERMS)
def test_the_english_rules_do_not_run_for_a_japanese_talk(mainland: str, taiwan: str) -> None:
    assert ZH_TW.terms_from("ja", mainland) == taiwan_terms(mainland)
    assert ZH_TW.terms_from("ja+en", mainland) == taiwan_terms(mainland)


@pytest.mark.parametrize("zh", ENGLISH_TALK_KEPT)
def test_a_mainland_word_that_is_the_right_word_is_kept(zh: str) -> None:
    assert taiwan_terms(zh) == zh
    assert taiwan_terms_from_english(zh) == zh
    assert reply_for(zh) == zh


@pytest.mark.parametrize("target", ["zh-CN", "ja", "ko", "es"])
def test_a_target_that_is_not_traditional_chinese_gets_no_taiwan_wording(target: str) -> None:
    text = "導入和依賴圖，訪問權限，倉庫。"
    assert get(target).terms_from("en", text) == text


def test_a_warehouse_is_judged_from_its_own_cue_whatever_the_grouping() -> None:
    code, goods = "我們有一個巨大的單一倉庫。", "把貨放進倉庫。"
    joined = taiwan_terms_from_english(f"[[1]]{code}[[2]]{goods}")
    assert joined == "[[1]]我們有一個巨大的單一儲存庫。[[2]]把貨放進倉庫。"
    assert taiwan_terms_from_english(code) == "我們有一個巨大的單一儲存庫。"
    assert taiwan_terms_from_english(goods) == goods
    assert taiwan_terms_from_english(f"[[1]]{goods}[[2]]{code}") == (
        "[[1]]把貨放進倉庫。[[2]]我們有一個巨大的單一儲存庫。"
    )


@pytest.mark.parametrize("zh", KITCHEN_CUES)
def test_kitchen_setup_and_physical_running_are_not_touched(zh: str) -> None:
    assert taiwan_terms(zh) == zh


@pytest.mark.parametrize(("mainland", "taiwan"), MAINLAND_CUES)
def test_configuration_and_running_software_terms_from_a_real_talk_are_replaced(
    mainland: str, taiwan: str
) -> None:
    assert ZH_TW.terms_from("en", mainland) == taiwan


@pytest.mark.parametrize("zh", KEPT_PROCEDURES)
def test_procedure_senses_of_chengxu_are_kept(zh: str) -> None:
    assert taiwan_terms(zh) == zh


def test_a_term_split_across_cues_is_replaced_in_the_reply() -> None:
    cues = [
        Cue(1, 0, 1000, "You can set up your"),
        Cue(2, 1000, 2000, "code base"),
        Cue(3, 2000, 3000, "and run it."),
    ]
    body = json.dumps(
        {"translations": [{"id": 1, "zh": "[[1]]你可以設置你的[[2]]程式碼庫，[[3]]並運行它。"}]},
        ensure_ascii=False,
    )
    request = build_request(cues, Batch((Unit(0, 3),)))
    assert parse_reply(body, request, cues) == {
        1: "你可以設定你的",
        2: "程式碼庫，",
        3: "並執行它。",
    }


@pytest.mark.parametrize(
    ("zh", "clean"),
    [
        ("但當我們結合_CLI_與功能圖時", "但當我們結合CLI與功能圖時"),
        ("這是 **重要** 的和 *斜體* 字", "這是 重要 的和 斜體 字"),
        ("檔名是 my_file_name.py 和 __init__。", "檔名是 my_file_name.py 和 __init__。"),
        ("2*3*4 等於 24，_ 單獨一個底線", "2*3*4 等於 24，_ 單獨一個底線"),
    ],
)
def test_markdown_emphasis_is_stripped_only_when_it_wraps_a_token(zh: str, clean: str) -> None:
    assert strip_markdown_emphasis(zh) == clean
    assert reply_for(zh) == clean


def test_replacing_twice_changes_nothing_more() -> None:
    for zh in ("演算法和算法", "程式代碼、源代碼、代碼", "設置環境，運行程式", "數據、數據庫"):
        once = taiwan_terms(zh)
        assert taiwan_terms(once) == once


def test_every_simplified_character_is_outside_big5_apart_from_the_named_exceptions() -> None:
    inside = {char for char in SIMPLIFIED_ONLY if in_big5(char)}
    assert inside == set(SIMPLIFIED_IN_BIG5)


def test_valid_traditional_characters_are_not_treated_as_simplified() -> None:
    for text in ("矽谷和谷歌", "伙伴", "胜肽", "珍惜", "骨髓", "甚麼", "裡面和裏面", "臺灣"):
        assert simplified_chars(text) == []


@pytest.mark.parametrize("char", list("这们说个么发无体广厂国时会"))
def test_common_simplified_characters_are_caught(char: str) -> None:
    assert simplified_chars(f"我們{char}樣") == [char]


@pytest.mark.parametrize(
    "zh",
    [
        "我搬到了矽谷。",
        "他們是我在這個專案上的伙伴。",
        "胜肽、珍珠和骨髓。",
        "谷歌的影子在這間公司裡到處都是。",
    ],
)
def test_traditional_text_with_dual_use_characters_is_accepted(zh: str) -> None:
    assert reply_for(zh, "I moved to Silicon Valley with my partner, you know.") == zh


def test_simplified_text_is_rejected_with_the_characters_named() -> None:
    with pytest.raises(ReplyError, match="Simplified characters.*个"):
        reply_for("这是一个测试，没有问题。", "This is a test and there is no problem.")


def test_a_cue_that_is_only_names_joined_by_chinese_punctuation_is_accepted() -> None:
    for en, zh in [
        ("Claude Code, Cursor, Windsurf, Copilot.", "Claude Code、Cursor、Windsurf、Copilot。"),
        ("GPT-4o, o3, o4-mini, Gemini 2.5 Pro.", "GPT-4o、o3、o4-mini、Gemini 2.5 Pro。"),
    ]:
        assert reply_for(zh, en) == zh


def test_an_english_copy_with_english_punctuation_is_still_rejected() -> None:
    en = "Claude Code, Cursor, Windsurf, Copilot."
    with pytest.raises(ReplyError, match="not translated"):
        reply_for(en, en)


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        (
            "uh，不變式是否，你知不知道，總是正確。Um，而且這，um，uh，你可以",
            "不變式是否，總是正確。而且這，你可以",
        ),
        ("開始思考，你知不知道，", "開始思考，"),
        ("你知不知道，驗證，使得你可以檢查", "驗證，使得你可以檢查"),
        ("你知不知道這件事嗎", "你知不知道這件事嗎"),
        ("你知不知道？", "你知不知道？"),
        ("Um，", "Um，"),
        ("這個 umbrella 專案很好用", "這個 umbrella 專案很好用"),
        ("Hmm, 所以我們出貨了", "所以我們出貨了"),
    ],
)
def test_drop_fillers(raw: str, clean: str) -> None:
    assert drop_fillers(raw) == clean


FILLER_CUES = [
    ("and uh you know propagate it", "而且你知不知道，將其散播給所有人"),
    ("in a high trust environment, you know", "一個高信任度的環境，你知不知道 "),
]


@pytest.mark.parametrize(("en", "zh"), FILLER_CUES)
def test_you_know_is_dropped_wherever_the_english_was_you_know(en: str, zh: str) -> None:
    assert "你知不知道" not in reply_for(zh, en)


def test_a_real_do_you_know_question_keeps_its_translation() -> None:
    assert (
        reply_for("你知不知道答案是什麼？", "Do you know what the answer is?")
        == "你知不知道答案是什麼？"
    )


def test_a_filler_glued_to_a_conjunction_leaves_the_sentence_readable() -> None:
    assert (
        reply_for("而且你知不知道，將其散播給所有人", "and uh you know propagate it to everyone")
        == "而且將其散播給所有人"
    )


def test_a_filler_before_a_marker_is_dropped_with_its_trailing_space() -> None:
    cues = [
        Cue(1, 0, 1000, "in a high trust environment, you know"),
        Cue(2, 1000, 2000, "your agents can move fast."),
    ]
    body = json.dumps(
        {
            "translations": [
                {"id": 1, "zh": "[[1]]一個高信任度的環境，你知不知道 [[2]]代理可以很快。"}
            ]
        },
        ensure_ascii=False,
    )
    request = build_request(cues, Batch((Unit(0, 2),)))
    assert parse_reply(body, request, cues) == {1: "一個高信任度的環境，", 2: "代理可以很快。"}


@pytest.mark.parametrize(
    ("mainland", "taiwan"),
    [
        ("你有一個主機，運行在，你知，", "你有一個主機，執行在，你知，"),
        ("雲端，運行更多的代理", "雲端，執行更多的代理"),
        ("在 CI 上運行", "在 CI 上執行"),
        ("像這樣運行", "像這樣執行"),
        ("運行這類模型", "執行這類模型"),
    ],
)
def test_run_in_software_talk_becomes_zhixing(mainland: str, taiwan: str) -> None:
    assert taiwan_terms(mainland) == taiwan
