"""カップヌードルミュージアム横浜(Etix)の指定日・指定時間枠を監視し、
残数表示(「N 現在の残数です」)が出たらntfyに通知する。"""
import os
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = (
    "https://www.etix.com/kketix/e/2011042"
    "?cobrand=cupnoodles-museum.jp&country=JP&language=ja"
)
TARGET_DAY = "29"      # 11/29 の「29」
TARGET_TIME = "10:30"  # 監視する時間枠
TOPIC = os.environ["NTFY_TOPIC"]
DEBUG = os.environ.get("DEBUG") == "1"

STATE_DIR = Path("state")
STATE_FILE = STATE_DIR / "last.txt"
DEBUG_DIR = Path("debug")
HOLDER = {}  # エラー時に画面を保存するため、ページを覚えておく


def notify(message: str) -> None:
    req = urllib.request.Request(
        f"https://ntfy.sh/{TOPIC}",
        data=message.encode("utf-8"),
        headers={"Priority": "high"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def dump(page, name: str) -> None:
    """原因調査用に画面とHTMLを保存する。"""
    DEBUG_DIR.mkdir(exist_ok=True)
    page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)
    (DEBUG_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")


def main() -> int:
    STATE_DIR.mkdir(exist_ok=True)
    last = STATE_FILE.read_text().strip() if STATE_FILE.exists() else ""

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(locale="ja-JP", timezone_id="Asia/Tokyo")
        page = ctx.new_page()
        HOLDER["page"] = page
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # カレンダーで対象日をクリック
        day = page.locator("td, a, button").filter(
            has_text=re.compile(rf"^\s*{TARGET_DAY}\s*$")
        )
        if day.count() == 0:
            dump(page, "calendar_not_found")
            print("カレンダーの対象日が見つかりません", file=sys.stderr)
            return 1
        day.first.click()
        page.wait_for_timeout(3000)

        # プルダウンの選択肢から対象時間枠を探す
        option_text = None
        for sel in page.locator("select").all():
            for text in sel.locator("option").all_inner_texts():
                if text.strip().startswith(TARGET_TIME):
                    option_text = text.strip()
        if option_text is None:
            dump(page, "option_not_found")
            print(f"{TARGET_TIME} の選択肢が見つかりません", file=sys.stderr)
            return 1

        if DEBUG:
            dump(page, "debug")
            notify(f"【動作確認】11/{TARGET_DAY} の表示: {option_text}")

        print(f"読み取り結果: {option_text}")
        m = re.search(r"(\d+)\s*現在の残数", option_text)
        if m:
            remaining = m.group(1)
            if remaining != last:
                notify(f"11/{TARGET_DAY} {TARGET_TIME} 残り{remaining}枚です")
                STATE_FILE.write_text(remaining)
        else:
            # 残数表示なし(30以上) → 状態をリセット
            STATE_FILE.write_text("")

        browser.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        if "page" in HOLDER:
            try:
                dump(HOLDER["page"], "error")
            except Exception:
                pass
        raise
