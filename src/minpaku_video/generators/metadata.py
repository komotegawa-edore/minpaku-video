from __future__ import annotations

import logging
from pathlib import Path

from minpaku_video.clients.claude import ClaudeClient
from minpaku_video.models.project import ProjectState
from minpaku_video.pipeline.state import StateManager
from minpaku_video.utils.filesystem import atomic_write_text

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
あなたはYouTubeチャンネル運営のプロです。
民泊経営に関する動画のメタデータ（タイトル、説明文、タグ）を作成してください。

ルール:
- タイトルは30文字以内で、検索されやすいキーワードを含める
- 説明文は動画の内容を要約し、関連キーワードを自然に含める
- タグは10〜15個、関連性の高い順に並べる
- チャプター（タイムスタンプ）は各ページの開始時点を記載する
- すべて日本語で記述する

出力フォーマット:
---
# タイトル
(タイトルテキスト)

# 説明文
(説明文テキスト)

# タグ
tag1, tag2, tag3, ...

# チャプター
00:00 (最初のページの内容)
MM:SS (次のページの内容)
...
---
"""


async def generate_metadata(
    state: ProjectState,
    state_manager: StateManager,
    claude: ClaudeClient,
) -> Path:
    """動画のYouTubeメタデータを生成する。"""
    # 全ページの原稿を結合
    all_scripts: list[str] = []
    cumulative_seconds = 0.0
    timestamps: list[str] = []

    for page in state.pages:
        minutes = int(cumulative_seconds // 60)
        seconds = int(cumulative_seconds % 60)
        timestamps.append(f"{minutes:02d}:{seconds:02d}")

        if page.script:
            all_scripts.append(f"[ページ{page.number}]\n{page.script}")
        cumulative_seconds += page.duration_seconds

    scripts_text = "\n\n".join(all_scripts)

    user_message = (
        f"動画タイトル案: {state.title}\n\n"
        f"以下は動画の各ページのナレーション原稿です:\n\n"
        f"{scripts_text}\n\n"
        f"各ページの開始タイムスタンプ:\n"
        + "\n".join(
            f"ページ{i+1}: {ts}" for i, ts in enumerate(timestamps)
        )
    )

    metadata_text, cost_entry = await claude.generate(
        system=SYSTEM_PROMPT,
        user_message=user_message,
    )

    cost_entry.stage = "metadata"
    state_manager.add_cost(state, cost_entry)

    # メタデータを保存
    output_path = state_manager.project_dir / "metadata.md"
    atomic_write_text(output_path, metadata_text)

    logger.info("メタデータ生成完了")
    return output_path
