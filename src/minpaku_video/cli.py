from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer
from rich.table import Table

from minpaku_video.config import get_settings
from minpaku_video.generators.pdf_import import import_pdf
from minpaku_video.generators.script import load_provided_scripts
from minpaku_video.models.project import PipelineStage, TTSEngine
from minpaku_video.pipeline.orchestrator import PipelineOrchestrator
from minpaku_video.pipeline.state import StateManager
from minpaku_video.utils.display import console, print_error, print_success

app = typer.Typer(
    name="minpaku-video",
    help="民泊経営チャンネル スライド動画制作パイプライン",
    no_args_is_help=True,
)

VOICE_PRESETS: dict[str, str] = {
    "george": "JBFqnCBsd6RMkjVDRZzb",
    "bella": "hpp4J3VqNfWAUOO0d1Us",
}

STAGE_MAP: dict[str, PipelineStage] = {
    "script": PipelineStage.PAGES_IMPORTED,
    "audio": PipelineStage.SCRIPTS_READY,
    "video": PipelineStage.AUDIO_GENERATED,
    "metadata": PipelineStage.VIDEO_GENERATED,
}


@app.command()
def new(
    pdf_path: Path = typer.Argument(..., help="スライドPDFファイルのパス"),
    title: str = typer.Option(..., "--title", "-t", help="動画タイトル"),
    script: Path | None = typer.Option(
        None, "--script", "-s",
        help="ナレーション原稿ファイル (---区切り)",
    ),
    voice: str = typer.Option(
        "elevenlabs", "--voice", "-v",
        help="TTSエンジン (elevenlabs / voicevox)",
    ),
    speaker: str = typer.Option(
        "george", "--speaker", "-S",
        help="声 (george / bella) or VOICEVOX speaker ID",
    ),
) -> None:
    """PDFからプロジェクトを新規作成"""
    # PDF存在チェック
    if not pdf_path.exists():
        print_error(f"PDFファイルが見つかりません: {pdf_path}")
        raise typer.Exit(1)

    # TTSエンジン解決
    try:
        tts_engine = TTSEngine(voice)
    except ValueError:
        print_error(f"無効なTTSエンジン: {voice} (elevenlabs / voicevox)")
        raise typer.Exit(1)

    # Voice/Speaker ID解決
    voice_id = ""
    speaker_id = 3
    if tts_engine == TTSEngine.ELEVENLABS:
        speaker_lower = speaker.lower()
        if speaker_lower in VOICE_PRESETS:
            voice_id = VOICE_PRESETS[speaker_lower]
        else:
            voice_id = speaker  # 直接ID指定
    else:
        try:
            speaker_id = int(speaker)
        except ValueError:
            settings = get_settings()
            speaker_id = settings.voicevox_default_speaker

    # StateManager初期化（まだproject_idなし）
    sm = StateManager()

    # PDF → PNG 変換
    console.print("[bold]PDFをインポート中...[/bold]")
    temp_output = get_settings().output_dir / "_temp_import"
    temp_output.mkdir(parents=True, exist_ok=True)

    pages = import_pdf(pdf_path, temp_output)
    console.print(f"  {len(pages)}ページを検出")

    # プロジェクト作成
    script_source = "provided" if script else "generated"
    state = sm.create_project(
        title=title,
        pdf_path=str(pdf_path.resolve()),
        total_pages=len(pages),
        pages=pages,
        tts_engine=tts_engine,
        voice_id=voice_id,
        speaker_id=speaker_id,
        script_source=script_source,
    )

    # PNGファイルを正しいプロジェクトディレクトリに移動
    pages_dir = sm.pages_dir()
    for page in pages:
        src = temp_output / page.image_file
        dst = pages_dir / page.image_file
        src.rename(dst)

    # temp_importディレクトリ削除
    temp_output.rmdir()

    # 提供スクリプトの読み込み
    if script:
        if not script.exists():
            print_error(f"スクリプトファイルが見つかりません: {script}")
            raise typer.Exit(1)
        load_provided_scripts(script, state, sm)
        console.print(f"  スクリプト読み込み完了")

    print_success("プロジェクトを作成しました")
    console.print(f"  ID: [bold]{state.project_id}[/bold]")
    console.print(f"  タイトル: {state.title}")
    console.print(f"  ページ数: {state.total_pages}")
    console.print(f"  TTS: {state.tts_engine.value}")
    console.print(f"  スクリプト: {state.script_source}")
    console.print(f"\n次のステップ:")
    console.print(f"  minpaku-video run {state.project_id}")


@app.command()
def run(
    project_id: str = typer.Argument(..., help="プロジェクトID"),
    from_stage: str | None = typer.Option(
        None, "--from-stage", "-f",
        help="開始ステージ (script / audio / video / metadata)",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="確認をスキップ",
    ),
    verbose: bool = typer.Option(
        False, "--verbose",
        help="詳細ログ出力",
    ),
) -> None:
    """パイプラインを実行"""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    sm = StateManager(project_id)
    if not sm.exists():
        print_error(f"プロジェクトが見つかりません: {project_id}")
        raise typer.Exit(1)

    state = sm.load()

    # from_stage の解決
    start_stage: PipelineStage | None = None
    if from_stage:
        if from_stage not in STAGE_MAP:
            print_error(
                f"無効なステージ: {from_stage}\n"
                f"有効な値: {', '.join(STAGE_MAP.keys())}"
            )
            raise typer.Exit(1)
        start_stage = STAGE_MAP[from_stage]

    console.print(f"[bold]プロジェクト: {state.title}[/bold]")
    console.print(f"  現在のステージ: {state.stage.value}")

    if not yes:
        typer.confirm("パイプラインを実行しますか？", abort=True)

    orchestrator = PipelineOrchestrator(
        state, sm,
        from_stage=start_stage,
        auto_confirm=yes,
    )
    asyncio.run(orchestrator.run())


@app.command(name="list")
def list_projects() -> None:
    """プロジェクト一覧を表示"""
    projects = StateManager.list_projects()
    if not projects:
        console.print("プロジェクトがありません")
        return

    table = Table(title="プロジェクト一覧")
    table.add_column("ID", style="bold")
    table.add_column("タイトル")
    table.add_column("ページ数", justify="right")
    table.add_column("ステージ")
    table.add_column("TTS")
    table.add_column("コスト", justify="right")

    for p in projects:
        table.add_row(
            p.project_id,
            p.title[:30],
            str(p.total_pages),
            p.stage.value,
            p.tts_engine.value,
            f"${p.total_cost_usd():.4f}",
        )

    console.print(table)


@app.command()
def status(
    project_id: str = typer.Argument(..., help="プロジェクトID"),
) -> None:
    """プロジェクトの詳細状態を表示"""
    sm = StateManager(project_id)
    if not sm.exists():
        print_error(f"プロジェクトが見つかりません: {project_id}")
        raise typer.Exit(1)

    state = sm.load()

    console.print(f"\n[bold]プロジェクト: {state.title}[/bold]")
    console.print(f"  ID: {state.project_id}")
    console.print(f"  PDF: {state.pdf_path}")
    console.print(f"  ページ数: {state.total_pages}")
    console.print(f"  ステージ: {state.stage.value}")
    console.print(f"  TTS: {state.tts_engine.value}")
    console.print(f"  スクリプト: {state.script_source}")
    console.print(f"  コスト合計: ${state.total_cost_usd():.4f}")
    console.print(f"  作成日時: {state.created_at}")

    # ページ状態
    console.print(f"\n[bold]ページ状態:[/bold]")
    table = Table()
    table.add_column("ページ", justify="right")
    table.add_column("画像")
    table.add_column("スクリプト")
    table.add_column("音声")
    table.add_column("秒数", justify="right")

    for page in state.pages:
        table.add_row(
            str(page.number),
            "✓" if (sm.pages_dir() / page.image_file).exists() else "✗",
            "✓" if page.script_ready else "✗",
            "✓" if page.audio_ready else "✗",
            f"{page.duration_seconds:.1f}" if page.duration_seconds else "-",
        )

    console.print(table)
