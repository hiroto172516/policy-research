"""共通ユーティリティ（名簿・評価軸の読み込み、パス解決）。"""
from __future__ import annotations
import csv
import os
from pathlib import Path

try:
    import yaml
except ImportError:  # pyyaml 未導入時のヒント
    raise SystemExit("pyyaml が必要です: pip3 install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"
SPEECHES = DATA / "speeches"
CLASSIFICATIONS = DATA / "classifications"


def get_jina_key() -> str | None:
    """Jina APIキーを取得。優先: 環境変数 JINA_API_KEY → config/jina.key（gitignore）。
    キーはチャットに出さず・コミットしない運用（config/jina.key は .gitignore 済み）。"""
    v = os.environ.get("JINA_API_KEY")
    if v and v.strip():
        return v.strip()
    kf = CONFIG / "jina.key"
    if kf.exists():
        t = kf.read_text(encoding="utf-8").strip()
        if t:
            return t
    return None


def load_roster(path: Path | None = None) -> list[dict]:
    """roster.csv を読み込む。'#' で始まるコメント行は無視する。"""
    path = path or (DATA / "roster.csv")
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    for r in reader:
        if not r.get("member_id"):
            continue
        # セミコロン区切りの複数値をリスト化
        r["committees_list"] = _split(r.get("committees"))
        r["party_divisions_list"] = _split(r.get("party_divisions"))
        rows.append(r)
    return rows


def _split(v: str | None) -> list[str]:
    if not v:
        return []
    return [x.strip() for x in v.split(";") if x.strip()]


def load_axes(path: Path | None = None) -> dict:
    path = path or (CONFIG / "axes.yml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs() -> None:
    for d in (SPEECHES, CLASSIFICATIONS, OUTPUT):
        d.mkdir(parents=True, exist_ok=True)
