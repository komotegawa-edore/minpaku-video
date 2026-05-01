from __future__ import annotations

import base64
import logging
from pathlib import Path

from minpaku_video.clients.claude import ClaudeClient
from minpaku_video.models.project import CostEntry, PageInfo, ProjectState
from minpaku_video.pipeline.state import StateManager
from minpaku_video.utils.filesystem import atomic_write_text

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
あなたはYouTube動画のナレーション原稿を作成するプロのライターです。
スライド画像を見て、そのページの内容を視聴者に分かりやすく説明するナレーション原稿を書いてください。

ルール:
- 話し言葉で自然に読み上げられる文章にする
- スライドの図表やグラフがある場合は、その内容も言葉で説明する
- 1ページあたり200〜400文字程度を目安にする
- 「このスライドでは」などメタ的な表現は避け、内容を直接説明する
- 民泊経営に関する専門用語は適切に使いつつ、初心者にも分かる説明を心がける
"""


async def generate_scripts(
    state: ProjectState,
    state_manager: StateManager,
    claude: ClaudeClient,
) -> None:
    """Claude Visionを使って各ページのナレーション原稿を生成する。"""
    pages_dir = state_manager.pages_dir()
    scripts_dir = state_manager.scripts_dir()

    for page in state.pages:
        if page.script_ready:
            logger.info(f"ページ {page.number}: スクリプト生成済み、スキップ")
            continue

        image_path = pages_dir / page.image_file
        if not image_path.exists():
            raise FileNotFoundError(f"画像が見つかりません: {image_path}")

        # 画像をbase64エンコード
        image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")

        user_message = (
            f"以下はプレゼンテーションの{page.number}ページ目のスライド画像です。"
            f"このページの内容について、ナレーション原稿を作成してください。"
        )

        script_text, cost_entry = await claude.generate_with_image(
            system=SYSTEM_PROMPT,
            user_message=user_message,
            image_data=image_data,
            image_media_type="image/png",
        )

        cost_entry.stage = "script"
        state_manager.add_cost(state, cost_entry)

        # スクリプトを保存
        script_path = scripts_dir / f"page_{page.number:02d}.txt"
        atomic_write_text(script_path, script_text)

        page.script = script_text
        page.script_ready = True
        state_manager.save(state)

        logger.info(
            f"ページ {page.number}: スクリプト生成完了 ({len(script_text)}文字)"
        )


def load_provided_scripts(
    script_path: Path,
    state: ProjectState,
    state_manager: StateManager,
) -> None:
    """ユーザー提供のスクリプトファイルを読み込んでページに割り当てる。"""
    text = script_path.read_text(encoding="utf-8")
    sections = [s.strip() for s in text.split("---") if s.strip()]

    scripts_dir = state_manager.scripts_dir()

    for i, section in enumerate(sections):
        if i >= len(state.pages):
            logger.warning(
                f"スクリプトのセクション数({len(sections)})が"
                f"ページ数({len(state.pages)})を超えています"
            )
            break

        page = state.pages[i]
        page.script = section
        page.script_ready = True

        out_path = scripts_dir / f"page_{page.number:02d}.txt"
        atomic_write_text(out_path, section)

    # ページ数よりセクションが少ない場合の警告
    if len(sections) < len(state.pages):
        logger.warning(
            f"スクリプトのセクション数({len(sections)})が"
            f"ページ数({len(state.pages)})より少ないです。"
            f"残りのページは自動生成が必要です。"
        )

    state.script_source = "provided"
    state_manager.save(state)
