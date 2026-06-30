"""Create a local paste kit for publishing timestamps to YouTube."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Optional

from sidelinehd_extractor.exports import PROJECT_CREDIT, PROJECT_URL
from sidelinehd_extractor.naming import game_name_for_run, game_slug_for_run


@dataclass(frozen=True)
class PublishKitResult:
    """Summary of a generated publishing paste kit."""

    output_path: Path
    markdown_path: Path
    html_path: Optional[Path]
    game_name: str
    chapters_path: Path
    at_bats_path: Path


def default_publish_kit_path(
    run_path: Path,
    output_dir: Optional[Path] = None,
    game_name: Optional[str] = None,
) -> Path:
    """Return the default paste-kit path for a run/game."""

    slug = game_slug_for_run(run_path, explicit_name=game_name)
    base_dir = output_dir.expanduser() if output_dir else run_path.expanduser() / "exports"
    return base_dir / slug / "youtube_paste_kit.md"


def write_publish_kit(
    run_path: Path,
    chapters_path: Path,
    at_bats_path: Path,
    output_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    game_name: Optional[str] = None,
    generate_html: bool = True,
) -> PublishKitResult:
    """Write a Markdown paste kit and optional HTML copy helper."""

    resolved_game_name = game_name_for_run(run_path, explicit_name=game_name)
    destination = output_path.expanduser() if output_path else default_publish_kit_path(
        run_path,
        output_dir=output_dir,
        game_name=resolved_game_name,
    )
    chapters_source = chapters_path.expanduser()
    at_bats_source = at_bats_path.expanduser()

    chapters_text = _read_text(chapters_source)
    at_bats_text = _read_text(at_bats_source)
    kit_text = render_publish_kit(
        game_name=resolved_game_name,
        chapters_text=chapters_text,
        at_bats_text=at_bats_text,
        chapters_path=chapters_source,
        at_bats_path=at_bats_source,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(kit_text, encoding="utf-8")
    html_path = None
    if generate_html:
        html_path = destination.with_suffix(".html")
        html_text = render_publish_kit_html(
            game_name=resolved_game_name,
            chapters_text=chapters_text,
            at_bats_text=at_bats_text,
            chapters_path=chapters_source,
            at_bats_path=at_bats_source,
        )
        html_path.write_text(html_text, encoding="utf-8")
    return PublishKitResult(
        output_path=destination,
        markdown_path=destination,
        html_path=html_path,
        game_name=resolved_game_name,
        chapters_path=chapters_source,
        at_bats_path=at_bats_source,
    )


def render_publish_kit(
    game_name: str,
    chapters_text: str,
    at_bats_text: str,
    chapters_path: Optional[Path] = None,
    at_bats_path: Optional[Path] = None,
) -> str:
    """Render a Markdown paste kit."""

    chapters_source = f"\nSource: `{chapters_path}`\n" if chapters_path else ""
    at_bats_source = f"\nSource: `{at_bats_path}`\n" if at_bats_path else ""

    return (
        f"# YouTube Paste Kit: {game_name}\n\n"
        "## Description Chapters\n\n"
        "Paste this into the YouTube video description. YouTube chapters require a `0:00` line.\n"
        f"{chapters_source}\n"
        "```text\n"
        f"{chapters_text.rstrip()}\n"
        "```\n\n"
        "## Pinned Comment\n\n"
        "Paste this as a YouTube comment, then pin it.\n"
        f"{at_bats_source}\n"
        "```text\n"
        f"{at_bats_text.rstrip()}\n"
        "```\n\n"
        "## Checklist\n\n"
        "- [ ] Description saved\n"
        "- [ ] Chapters visible on the video progress bar\n"
        "- [ ] At-bat comment posted\n"
        "- [ ] At-bat comment pinned\n"
    )


def render_publish_kit_html(
    game_name: str,
    chapters_text: str,
    at_bats_text: str,
    chapters_path: Optional[Path] = None,
    at_bats_path: Optional[Path] = None,
) -> str:
    """Render a self-contained HTML paste kit."""

    title = f"YouTube Paste Kit: {game_name}"
    escaped_title = escape(title)
    escaped_chapters = escape(chapters_text)
    escaped_at_bats = escape(at_bats_text)
    escaped_credit = escape(PROJECT_CREDIT)
    escaped_project_url = escape(PROJECT_URL, quote=True)
    chapters_source = _html_source_line(chapters_path)
    at_bats_source = _html_source_line(at_bats_path)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #5d6d7e;
      --border: #cfd7df;
      --accent: #0969da;
      --accent-dark: #0756b3;
      --success: #1a7f37;
      --warning: #9a6700;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    main {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }}
    header {{ margin-bottom: 20px; }}
    h1 {{
      margin: 0 0 6px;
      font-size: clamp(1.5rem, 2vw, 2rem);
      line-height: 1.15;
    }}
    h2 {{
      margin: 0;
      font-size: 1.05rem;
    }}
    p {{ margin: 0; }}
    .muted {{
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .sections {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      align-items: start;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }}
    .panel-header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 10px;
    }}
    .source {{
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 0.85rem;
      overflow-wrap: anywhere;
    }}
    textarea {{
      width: 100%;
      min-height: 360px;
      resize: vertical;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      color: var(--text);
      background: #fbfcfd;
      font: 0.92rem/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre;
    }}
    button {{
      min-height: 40px;
      border: 0;
      border-radius: 6px;
      padding: 0 14px;
      background: var(--accent);
      color: #ffffff;
      font-weight: 700;
      cursor: pointer;
      white-space: nowrap;
    }}
    button:hover {{ background: var(--accent-dark); }}
    .status {{
      min-height: 1.3em;
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .status.success {{ color: var(--success); }}
    .status.warning {{ color: var(--warning); }}
    .checklist {{
      margin-top: 16px;
    }}
    .checklist ul {{
      list-style: none;
      padding: 0;
      margin: 12px 0 0;
      display: grid;
      gap: 8px;
    }}
    .checklist label {{
      display: flex;
      gap: 10px;
      align-items: center;
    }}
    .checklist input {{
      width: 18px;
      height: 18px;
    }}
    footer {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    footer a {{ color: var(--accent); }}
    @media (max-width: 760px) {{
      main {{ width: min(100% - 20px, 1120px); padding-top: 18px; }}
      .sections {{ grid-template-columns: 1fr; }}
      .panel {{ padding: 12px; }}
      .panel-header {{ align-items: flex-start; flex-direction: column; }}
      button {{ width: 100%; }}
      textarea {{ min-height: 300px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escaped_title}</h1>
      <p class="muted">Open this file locally, copy each section, and paste it into YouTube.</p>
    </header>
    <section class="sections" aria-label="YouTube timestamp copy sections">
      <article class="panel">
        <div class="panel-header">
          <h2>Description Chapters</h2>
          <button type="button" data-copy-target="chapters-text" data-status-target="chapters-status">Copy chapters</button>
        </div>
        {chapters_source}
        <textarea id="chapters-text" readonly spellcheck="false">{escaped_chapters}</textarea>
        <p class="status" id="chapters-status" role="status" aria-live="polite"></p>
      </article>
      <article class="panel">
        <div class="panel-header">
          <h2>Pinned Comment</h2>
          <button type="button" data-copy-target="at-bats-text" data-status-target="at-bats-status">Copy at-bats</button>
        </div>
        {at_bats_source}
        <textarea id="at-bats-text" readonly spellcheck="false">{escaped_at_bats}</textarea>
        <p class="status" id="at-bats-status" role="status" aria-live="polite"></p>
      </article>
    </section>
    <section class="panel checklist" aria-label="Posting checklist">
      <h2>Posting Checklist</h2>
      <ul>
        <li><label><input type="checkbox"> Description saved</label></li>
        <li><label><input type="checkbox"> Chapters visible on the video progress bar</label></li>
        <li><label><input type="checkbox"> At-bat comment posted</label></li>
        <li><label><input type="checkbox"> At-bat comment pinned</label></li>
      </ul>
    </section>
    <footer>
      <p>{escape("Generated for " + game_name)}.</p>
      <p>{escaped_credit}</p>
      <p><a href="{escaped_project_url}">{escaped_project_url}</a></p>
    </footer>
  </main>
  <script>
    async function copyText(textarea, status) {{
      const text = textarea.value;
      status.className = "status";
      status.textContent = "";
      try {{
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          await navigator.clipboard.writeText(text);
        }} else {{
          throw new Error("Clipboard API unavailable");
        }}
        status.className = "status success";
        status.textContent = "Copied!";
        return;
      }} catch (clipboardError) {{
        try {{
          textarea.focus();
          textarea.select();
          const copied = document.execCommand("copy");
          if (!copied) {{
            throw new Error("Copy command failed");
          }}
          status.className = "status success";
          status.textContent = "Copied!";
          return;
        }} catch (fallbackError) {{
          textarea.focus();
          textarea.select();
          status.className = "status warning";
          status.textContent = "Select the text and copy manually.";
        }}
      }}
    }}

    document.querySelectorAll("[data-copy-target]").forEach(function (button) {{
      button.addEventListener("click", function () {{
        const textarea = document.getElementById(button.dataset.copyTarget);
        const status = document.getElementById(button.dataset.statusTarget);
        copyText(textarea, status);
      }});
    }});
  </script>
</body>
</html>
"""


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def _html_source_line(path: Optional[Path]) -> str:
    if path is None:
        return ""
    return f'<p class="source">Source: <code>{escape(str(path))}</code></p>'
