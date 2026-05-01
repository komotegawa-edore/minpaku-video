"""Streamlit WebアプリUI — 民泊動画制作パイプライン"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Streamlit Cloud 用: src/ をパスに追加してパッケージを参照可能にする
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import streamlit as st

from minpaku_video.config import CONFIG_FILE, get_settings, set_api_keys
from minpaku_video.generators.pdf_import import import_pdf
from minpaku_video.generators.script import load_provided_scripts
from minpaku_video.models.project import PipelineStage, TTSEngine
from minpaku_video.pipeline.orchestrator import PipelineOrchestrator
from minpaku_video.pipeline.state import StateManager

VOICE_PRESETS: dict[str, str] = {
    "George": "JBFqnCBsd6RMkjVDRZzb",
    "Bella": "hpp4J3VqNfWAUOO0d1Us",
}


def _load_saved_keys() -> tuple[str, str]:
    """保存済みAPIキーを読み込む。"""
    settings = get_settings()
    return settings.anthropic_api_key, settings.elevenlabs_api_key


def _has_streamlit_secrets() -> bool:
    """Streamlit Cloud の Secrets にAPIキーが設定済みか判定する。"""
    try:
        return bool(st.secrets.get("ANTHROPIC_API_KEY"))
    except Exception:
        return False


def _render_sidebar() -> None:
    """サイドバー: APIキー設定"""
    st.sidebar.header("API設定")

    if _has_streamlit_secrets():
        st.sidebar.success("APIキーは Secrets で設定済みです")
        return

    saved_anthropic, saved_elevenlabs = _load_saved_keys()

    anthropic_key = st.sidebar.text_input(
        "Anthropic APIキー",
        value=saved_anthropic,
        type="password",
        key="anthropic_key",
    )
    elevenlabs_key = st.sidebar.text_input(
        "ElevenLabs APIキー",
        value=saved_elevenlabs,
        type="password",
        key="elevenlabs_key",
    )

    if st.sidebar.button("キーを保存"):
        set_api_keys(anthropic_key, elevenlabs_key, persist=True)
        st.sidebar.success(f"保存しました ({CONFIG_FILE})")

    # 現在のセッションに反映
    if anthropic_key or elevenlabs_key:
        set_api_keys(anthropic_key, elevenlabs_key)


def _render_main() -> None:
    """メインエリア: 動画制作フォーム"""
    st.title("民泊動画メーカー")
    st.caption("スライドPDFからYouTube動画を自動生成")

    # --- 入力フォーム ---
    title = st.text_input(
        "動画タイトル",
        placeholder="【民泊】物件紹介スライド",
    )

    pdf_file = st.file_uploader("スライドPDF", type=["pdf"])
    if pdf_file:
        st.info(f"ファイル: {pdf_file.name} ({pdf_file.size / 1024:.0f} KB)")

    # ナレーション原稿
    script_mode = st.radio(
        "ナレーション原稿",
        ["自動生成（Claude）", "原稿ファイルをアップロード"],
        horizontal=True,
    )
    script_file = None
    if script_mode == "原稿ファイルをアップロード":
        script_file = st.file_uploader(
            "原稿テキストファイル（ページ区切り: ---）",
            type=["txt"],
            key="script_upload",
        )

    # TTS設定
    col1, col2 = st.columns(2)
    with col1:
        tts_engine = st.selectbox(
            "TTSエンジン",
            ["ElevenLabs", "VOICEVOX"],
        )
    with col2:
        if tts_engine == "ElevenLabs":
            voice_name = st.selectbox("声", list(VOICE_PRESETS.keys()))
        else:
            speaker_id = st.number_input(
                "VOICEVOX Speaker ID", min_value=0, value=3, step=1
            )

    # --- 実行ボタン ---
    st.divider()

    can_run = bool(title and pdf_file)
    if not can_run:
        st.warning("タイトルとPDFファイルを入力してください。")

    if st.button("動画を作成", type="primary", disabled=not can_run):
        _run_pipeline(
            title=title,
            pdf_file=pdf_file,
            script_file=script_file,
            tts_engine_name=tts_engine,
            voice_name=voice_name if tts_engine == "ElevenLabs" else None,
            speaker_id=speaker_id if tts_engine != "ElevenLabs" else 3,
        )

    # --- 結果表示 ---
    if "result_video" in st.session_state:
        _render_results()


def _run_pipeline(
    *,
    title: str,
    pdf_file,
    script_file,
    tts_engine_name: str,
    voice_name: str | None,
    speaker_id: int,
) -> None:
    """パイプラインを実行し、結果をsession_stateに保存する。"""
    settings = get_settings()

    # バリデーション
    if not settings.anthropic_api_key:
        st.error("Anthropic APIキーが設定されていません。サイドバーで入力してください。")
        return
    if tts_engine_name == "ElevenLabs" and not settings.elevenlabs_api_key:
        st.error("ElevenLabs APIキーが設定されていません。サイドバーで入力してください。")
        return

    # TTS設定解決
    tts_engine = (
        TTSEngine.ELEVENLABS if tts_engine_name == "ElevenLabs" else TTSEngine.VOICEVOX
    )
    voice_id = VOICE_PRESETS.get(voice_name, "") if voice_name else ""

    progress_bar = st.progress(0.0)
    status_container = st.status("パイプライン実行中...", expanded=True)

    def on_progress(message: str, progress: float) -> None:
        progress_bar.progress(min(progress, 1.0))
        status_container.write(f"▶ {message}")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # PDFを一時ディレクトリに保存
            pdf_path = tmpdir_path / pdf_file.name
            pdf_path.write_bytes(pdf_file.getvalue())

            # PDF → PNG 変換
            on_progress("PDFをインポート中...", 0.0)
            temp_pages_dir = tmpdir_path / "pages"
            temp_pages_dir.mkdir()
            pages = import_pdf(pdf_path, temp_pages_dir)
            status_container.write(f"  {len(pages)}ページを検出")

            # プロジェクト作成
            script_source = "provided" if script_file else "generated"
            sm = StateManager()
            state = sm.create_project(
                title=title,
                pdf_path=str(pdf_path),
                total_pages=len(pages),
                pages=pages,
                tts_engine=tts_engine,
                voice_id=voice_id,
                speaker_id=speaker_id,
                script_source=script_source,
            )

            # PNGファイルを正しいプロジェクトディレクトリに移動
            # shutil.move を使用（Windows でドライブをまたぐ場合にも対応）
            pages_dir = sm.pages_dir()
            for page in pages:
                src = temp_pages_dir / page.image_file
                dst = pages_dir / page.image_file
                shutil.move(str(src), str(dst))

            # 提供スクリプトの読み込み
            if script_file:
                script_tmp = tmpdir_path / "script.txt"
                script_tmp.write_bytes(script_file.getvalue())
                load_provided_scripts(script_tmp, state, sm)
                status_container.write("  スクリプト読み込み完了")

            # パイプライン実行
            orchestrator = PipelineOrchestrator(
                state,
                sm,
                auto_confirm=True,
                on_progress=on_progress,
            )
            asyncio.run(orchestrator.run())

        # 結果をsession_stateに保存
        video_path = sm.video_dir() / "output.mp4"
        metadata_path = sm.project_dir / "metadata.md"

        st.session_state["result_video"] = str(video_path)
        st.session_state["result_project_id"] = state.project_id
        st.session_state["result_cost"] = state.total_cost_usd()

        if metadata_path.exists():
            st.session_state["result_metadata"] = metadata_path.read_text(
                encoding="utf-8"
            )
        else:
            st.session_state["result_metadata"] = ""

        status_container.update(label="パイプライン完了!", state="complete")
        progress_bar.progress(1.0)

    except Exception as e:
        status_container.update(label="エラーが発生しました", state="error")
        st.error(f"パイプライン実行中にエラーが発生しました:\n\n{e}")


def _render_results() -> None:
    """完了後の結果表示。"""
    st.divider()
    st.subheader("生成結果")

    video_path = st.session_state.get("result_video", "")
    project_id = st.session_state.get("result_project_id", "")
    cost = st.session_state.get("result_cost", 0.0)
    metadata = st.session_state.get("result_metadata", "")

    st.caption(f"プロジェクトID: {project_id} | コスト: ${cost:.4f}")

    # 動画プレビュー
    if video_path and Path(video_path).exists():
        st.video(video_path)

        with open(video_path, "rb") as f:
            st.download_button(
                "MP4をダウンロード",
                data=f,
                file_name=f"minpaku_{project_id}.mp4",
                mime="video/mp4",
            )

    # メタデータ表示
    if metadata:
        st.subheader("YouTubeメタデータ")
        st.text_area(
            "コピーして使用",
            value=metadata,
            height=300,
            key="metadata_display",
        )


def main() -> None:
    """Streamlitアプリを起動するエントリーポイント。"""
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", __file__, "--server.headless=true"],
        check=True,
    )


def _is_streamlit_runtime() -> bool:
    """Streamlitランタイム内で実行されているか判定する。"""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


# streamlit run で実行された場合のみUIを描画
if _is_streamlit_runtime():
    st.set_page_config(
        page_title="民泊動画メーカー",
        page_icon="🎬",
        layout="centered",
    )
    _render_sidebar()
    _render_main()
