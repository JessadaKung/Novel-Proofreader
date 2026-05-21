from __future__ import annotations

import json
import os
import re
import time
import base64
import urllib.error
import urllib.request
import socket
import shutil
import zipfile
import tempfile
from email import policy
from email.parser import BytesParser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
CHAPTERS_DIR = ROOT / "chapters"
SOURCE_DIR = CHAPTERS_DIR / "source"
REVIEWED_DIR = CHAPTERS_DIR / "reviewed"
REPORT_DIR = ROOT / "reports" / "proofreading"
GLOSSARY_DIR = ROOT / "glossary"
ENV_PATH = ROOT / ".env"
FILE_MANAGER_ROOTS = {
    "chapters": CHAPTERS_DIR,
    "glossary": GLOSSARY_DIR,
    "glossary_raw": ROOT / "glossary_raw",
    "reports": ROOT / "reports",
    "wiki": ROOT / "wiki",
}
EDITABLE_SUFFIXES = {".md", ".txt", ".json", ".yml", ".yaml", ".env", ".example"}

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8010"))


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for raw_line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env_values(updates: dict[str, str]) -> None:
    current = read_env_values()
    current.update({key: value for key, value in updates.items() if value is not None})
    ordered_keys = [
        "LLM_PROVIDER",
        "GOOGLE_API_KEY",
        "LLM_MODEL",
        "GOOGLE_FALLBACK_MODELS",
        "GOOGLE_RETRY_COUNT",
        "GOOGLE_RETRY_DELAY_SECONDS",
        "GOOGLE_TIMEOUT_SECONDS",
        "DISCORD_WEBHOOK_URL",
        "AUTH_USERNAME",
        "AUTH_PASSWORD",
    ]
    lines = ["# Google Gemini API"]
    for key in ordered_keys:
        if key in current:
            lines.append(f"{key}={current[key]}")
    extras = sorted(key for key in current if key not in ordered_keys)
    if extras:
        lines.extend(["", "# Other"])
        lines.extend(f"{key}={current[key]}" for key in extras)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key, value in current.items():
        os.environ[key] = value


def public_config() -> dict[str, str]:
    values = read_env_values()
    api_key = values.get("GOOGLE_API_KEY") or values.get("GEMINI_API_KEY") or values.get("LLM_API_KEY", "")
    return {
        "LLM_PROVIDER": values.get("LLM_PROVIDER", "google"),
        "GOOGLE_API_KEY_SET": "true" if api_key else "false",
        "GOOGLE_API_KEY_PREVIEW": f"...{api_key[-4:]}" if api_key else "",
        "LLM_MODEL": values.get("LLM_MODEL", "gemma-4-31b-it"),
        "GOOGLE_FALLBACK_MODELS": values.get("GOOGLE_FALLBACK_MODELS", ""),
        "GOOGLE_RETRY_COUNT": values.get("GOOGLE_RETRY_COUNT", "3"),
        "GOOGLE_RETRY_DELAY_SECONDS": values.get("GOOGLE_RETRY_DELAY_SECONDS", "4"),
        "GOOGLE_TIMEOUT_SECONDS": values.get("GOOGLE_TIMEOUT_SECONDS", "300"),
        "DISCORD_WEBHOOK_SET": "true" if values.get("DISCORD_WEBHOOK_URL", "") else "false",
        "DISCORD_WEBHOOK_PREVIEW": f"...{values.get('DISCORD_WEBHOOK_URL', '')[-8:]}" if values.get("DISCORD_WEBHOOK_URL", "") else "",
    }


def send_discord_notification(title: str, message: str, color: int = 0x47A3FF) -> bool:
    load_env()
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return False
    payload = {
        "embeds": [
            {
                "title": title[:256],
                "description": message[:4000],
                "color": color,
                "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
        ]
    }
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20):
            return True
    except Exception as exc:
        print(f"Discord webhook failed: {exc}")
        return False


def auth_enabled() -> bool:
    load_env()
    return bool(os.environ.get("AUTH_USERNAME") and os.environ.get("AUTH_PASSWORD"))


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def safe_upload_name(value: str) -> str:
    name = Path(value.replace("\\", "/")).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
    return name or "upload.md"


def safe_folder_name(value: str) -> str:
    value = value.replace("\\", "/").strip().strip("/")
    parts = []
    for part in value.split("/"):
        part = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", part).strip()
        if part and part not in {".", ".."}:
            parts.append(part)
    return "/".join(parts) or datetime.now().strftime("upload-%Y%m%d-%H%M%S")


def safe_relative_path(value: str, base: Path) -> Path:
    candidate = (base / value).resolve()
    if base.resolve() not in candidate.parents and candidate != base.resolve():
        raise ValueError("path is outside allowed directory")
    if not candidate.is_file():
        raise FileNotFoundError(value)
    return candidate


def safe_relative_dir(value: str, base: Path) -> Path:
    candidate = (base / value).resolve()
    if base.resolve() not in candidate.parents and candidate != base.resolve():
        raise ValueError("path is outside allowed directory")
    if not candidate.is_dir():
        raise FileNotFoundError(value)
    return candidate


def file_manager_path(root_name: str, rel_path: str = "") -> Path:
    if root_name not in FILE_MANAGER_ROOTS:
        raise ValueError("unknown file root")
    base = FILE_MANAGER_ROOTS[root_name].resolve()
    candidate = (base / rel_path).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError("path is outside allowed root")
    return candidate


def list_files(root_name: str, rel_path: str = "") -> dict:
    base = FILE_MANAGER_ROOTS[root_name].resolve()
    current = file_manager_path(root_name, rel_path)
    if not current.exists():
        raise FileNotFoundError(rel_path)
    if not current.is_dir():
        raise ValueError("path is not a directory")
    items = []
    for path in sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if path.name.startswith("__pycache__"):
            continue
        rel = path.relative_to(base).as_posix()
        items.append({
            "name": path.name,
            "path": rel,
            "type": "dir" if path.is_dir() else "file",
            "size": path.stat().st_size if path.is_file() else 0,
            "editable": path.is_file() and is_editable_file(path),
        })
    parent = current.parent.relative_to(base).as_posix() if current != base else ""
    return {"root": root_name, "path": current.relative_to(base).as_posix() if current != base else "", "parent": parent, "items": items}


def is_editable_file(path: Path) -> bool:
    if path.name == ".env":
        return True
    return path.suffix.lower() in EDITABLE_SUFFIXES


def read_managed_file(root_name: str, rel_path: str) -> dict:
    path = file_manager_path(root_name, rel_path)
    if not path.is_file():
        raise FileNotFoundError(rel_path)
    if not is_editable_file(path):
        raise ValueError("file type is not editable")
    return {"root": root_name, "path": rel_path, "text": read_text(path)}


def write_managed_file(root_name: str, rel_path: str, text: str) -> dict:
    path = file_manager_path(root_name, rel_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    if not is_editable_file(path):
        raise ValueError("file type is not editable")
    path.write_text(text, encoding="utf-8")
    return {"root": root_name, "path": rel_path, "size": path.stat().st_size}


def delete_managed_path(root_name: str, rel_path: str) -> dict:
    path = file_manager_path(root_name, rel_path)
    if path == FILE_MANAGER_ROOTS[root_name].resolve():
        raise ValueError("refusing to delete root")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.is_file():
        path.unlink()
    else:
        raise FileNotFoundError(rel_path)
    return {"deleted": rel_path}


def list_chapters() -> list[dict[str, str]]:
    files = []
    for path in SOURCE_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            rel = path.relative_to(SOURCE_DIR).as_posix()
            files.append({"path": rel, "name": rel})
    return sorted(files, key=lambda item: item["path"])


def list_chapter_folders() -> list[dict[str, str]]:
    folders = [{"path": "", "name": "chapters/source ทั้งหมด"}]
    for path in SOURCE_DIR.rglob("*"):
        if path.is_dir():
            rel = path.relative_to(SOURCE_DIR).as_posix()
            folders.append({"path": rel, "name": rel})
    return sorted(folders, key=lambda item: item["path"])


def chapters_in_folder(folder: str) -> list[dict[str, str]]:
    base = safe_relative_dir(folder, SOURCE_DIR) if folder else SOURCE_DIR
    files = []
    for path in base.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            rel = path.relative_to(SOURCE_DIR).as_posix()
            reviewed_path = REVIEWED_DIR / Path(rel).name
            files.append({
                "path": rel,
                "name": rel,
                "reviewed": reviewed_path.exists(),
                "reviewed_path": reviewed_path.relative_to(ROOT).as_posix() if reviewed_path.exists() else "",
            })
    return sorted(files, key=lambda item: item["path"])


def chapter_status(chapter_path: str) -> dict[str, str | bool]:
    source_path = safe_relative_path(chapter_path, SOURCE_DIR)
    reviewed_path = REVIEWED_DIR / source_path.name
    return {
        "path": chapter_path,
        "reviewed": reviewed_path.exists(),
        "reviewed_path": reviewed_path.relative_to(ROOT).as_posix() if reviewed_path.exists() else "",
    }


def create_source_folder(folder: str) -> dict[str, str]:
    safe_folder = safe_folder_name(folder)
    path = (SOURCE_DIR / safe_folder).resolve()
    if SOURCE_DIR.resolve() not in path.parents and path != SOURCE_DIR.resolve():
        raise ValueError("folder is outside chapters/source")
    path.mkdir(parents=True, exist_ok=True)
    return {"folder": safe_folder}


def delete_source_folder(folder: str) -> dict[str, str]:
    safe_folder = safe_folder_name(folder)
    path = safe_relative_dir(safe_folder, SOURCE_DIR)
    if path == SOURCE_DIR.resolve():
        raise ValueError("refusing to delete chapters/source root")
    shutil.rmtree(path)
    return {"deleted": safe_folder}


def build_download_zip(kind: str, folder: str = "") -> tuple[Path, str]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    temp_path = Path(tempfile.gettempdir()) / f"novel-proofreader-{kind}-{stamp}.zip"
    folder_prefix = safe_folder_name(folder) if folder else ""

    if kind == "reviewed":
        source = REVIEWED_DIR
        filename = f"reviewed-{stamp}.zip"
    elif kind == "reports":
        source = REPORT_DIR
        filename = f"proofreading-reports-{stamp}.zip"
    elif kind == "all":
        source = ROOT
        filename = f"proofreading-output-{stamp}.zip"
    else:
        raise ValueError("unknown download kind")

    with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
        if kind in {"reviewed", "reports"}:
            if source.exists():
                for path in source.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(source).as_posix())
        else:
            for base in [REVIEWED_DIR, REPORT_DIR]:
                if not base.exists():
                    continue
                for path in base.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(ROOT).as_posix())

    return temp_path, filename


def safe_extract_zip(zip_path: Path, target_dir: Path) -> list[str]:
    extracted: list[str] = []
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix not in {".md", ".txt"}:
                continue
            parts = [
                safe_upload_name(part)
                for part in info.filename.replace("\\", "/").split("/")
                if part and part not in {".", ".."}
            ]
            if not parts:
                continue
            destination = (target_dir / Path(*parts)).resolve()
            if target_root not in destination.parents and destination != target_root:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(destination.relative_to(SOURCE_DIR).as_posix())
    return extracted


def parse_multipart_form(content_type: str, body: bytes) -> tuple[str, list[tuple[str, bytes]]]:
    folder = ""
    files: list[tuple[str, bytes]] = []
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + body
    )
    if not message.is_multipart():
        raise ValueError("request is not multipart form data")

    for part in message.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if field_name == "folder":
            folder = payload.decode("utf-8", errors="replace")
        elif field_name == "files" and filename:
            files.append((filename, payload))
    return folder, files


def save_uploaded_files(target_dir: Path, files: list[tuple[str, bytes]], zip_base: Path | None = None) -> list[str]:
    target_dir = target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for original_filename, content in files:
        filename = safe_upload_name(original_filename)
        suffix = Path(filename).suffix.lower()
        if suffix not in {".md", ".txt", ".zip", ".json", ".yml", ".yaml"}:
            continue
        destination = (target_dir / filename).resolve()
        if target_dir not in destination.parents and destination != target_dir:
            continue
        destination.write_bytes(content)
        if suffix == ".zip":
            extracted = safe_extract_zip(destination, target_dir)
            saved.extend(extracted if zip_base is None else extracted)
            destination.unlink(missing_ok=True)
        else:
            base = zip_base or target_dir
            try:
                saved.append(destination.relative_to(base).as_posix())
            except ValueError:
                saved.append(destination.name)
    return sorted(saved)


def load_glossary_snippet(limit: int = 140) -> str:
    rows: list[str] = []
    files = [
        "characters.md",
        "pokemon.md",
        "moves.md",
        "abilities.md",
        "items.md",
        "locations.md",
        "terms.md",
    ]
    for filename in files:
        path = GLOSSARY_DIR / filename
        if not path.exists():
            continue
        for line in read_text(path).splitlines():
            if not line.startswith("|") or "---" in line or "source_text" in line:
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 10:
                continue
            source_text, zh, ja, en, th, category, status = (
                cells[1],
                cells[2],
                cells[3],
                cells[4],
                cells[5],
                cells[6],
                cells[8],
            )
            if th:
                rows.append(
                    f"- {category}: source={source_text or zh or ja or en}; th={th}; status={status}"
                )
            if len(rows) >= limit:
                return "\n".join(rows)
    return "\n".join(rows) if rows else "- No active glossary entries yet."


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("Model did not return JSON.")


def call_llm(text: str, source_file: str = "") -> dict:
    load_env()
    provider = os.environ.get("LLM_PROVIDER", "google").strip().lower()
    model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")

    glossary = load_glossary_snippet()
    system_prompt = (
        "You are a Thai novel proofreading editor. Correct spelling, punctuation, spacing, "
        "and awkward Thai prose while preserving meaning, tone, paragraph structure, names, "
        "events, and all factual details. Do not add new events. Use glossary terms as canonical. "
        "Return only valid JSON."
    )
    user_prompt = f"""
Source file: {source_file or "pasted text"}

Active glossary excerpt:
{glossary}

Proofread this text. If the text is not Thai, report that it may need translation/review rather than pretending it is proofread.

Return this JSON shape:
{{
  "revised": "full revised text",
  "changes": [
    {{"type": "spelling|style|punctuation|glossary|note", "before": "...", "after": "...", "reason": "..."}}
  ],
  "needs_review": ["..."],
  "summary": "short Thai summary"
}}

Text:
<<<
{text}
>>>
""".strip()

    if provider == "google":
        return call_google_llm(system_prompt, user_prompt, text)

    return call_openai_compatible_llm(model, system_prompt, user_prompt)


def google_models_to_try() -> list[str]:
    values = [
        os.environ.get("LLM_MODEL", "gemini-2.5-flash"),
        os.environ.get("GOOGLE_FALLBACK_MODELS", ""),
    ]
    models: list[str] = []
    for value in values:
        for model in value.split(","):
            model = model.strip()
            if model and model not in models:
                models.append(model)
    return models


def blocked_result(original_text: str, model_name: str, reason: str, message: str) -> dict:
    return {
        "revised": original_text,
        "changes": [
            {
                "type": "note",
                "before": "",
                "after": "",
                "reason": f"Google blocked model output from {model_name}: {reason}. {message}",
            }
        ],
        "needs_review": [
            f"Google API blocked this chapter with finishReason={reason}. Review manually or try another model/provider."
        ],
        "summary": "Google API ไม่คืนผลตรวจเพราะระบบ safety block จึงคงข้อความเดิมไว้และทำเครื่องหมาย needs review",
    }


def call_google_llm(system_prompt: str, user_prompt: str, original_text: str) -> dict:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("Set GOOGLE_API_KEY in .env first.")
    retry_count = int(os.environ.get("GOOGLE_RETRY_COUNT", "3"))
    retry_delay = float(os.environ.get("GOOGLE_RETRY_DELAY_SECONDS", "4"))
    timeout_seconds = float(os.environ.get("GOOGLE_TIMEOUT_SECONDS", "300"))

    payload = {
        "systemInstruction": {
            "parts": [{"text": system_prompt}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    errors: list[str] = []
    data = None
    last_model_name = ""
    for model_name in google_models_to_try():
        last_model_name = model_name
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model_name}:generateContent?key={api_key}"
        )
        for attempt in range(retry_count + 1):
            request = urllib.request.Request(
                endpoint,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                retryable = exc.code in {429, 500, 502, 503, 504}
                errors.append(f"{model_name} attempt {attempt + 1}: HTTP {exc.code}: {body[:300]}")
                if not retryable or attempt >= retry_count:
                    break
                time.sleep(retry_delay * (attempt + 1))
            except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
                errors.append(f"{model_name} attempt {attempt + 1}: timeout/network error: {exc}")
                if attempt >= retry_count:
                    break
                time.sleep(retry_delay * (attempt + 1))
        if data is not None:
            break

    if data is None:
        joined = "\n".join(errors[-8:])
        raise RuntimeError(
            "Google API failed after retries/fallbacks. "
            "Try a lighter model, a smaller chapter, or increase GOOGLE_TIMEOUT_SECONDS.\n"
            f"{joined}"
        )

    candidate = data.get("candidates", [{}])[0]
    finish_reason = candidate.get("finishReason", "")
    finish_message = candidate.get("finishMessage", "")
    if finish_reason == "PROHIBITED_CONTENT":
        return blocked_result(original_text, last_model_name, finish_reason, finish_message)

    parts = candidate.get("content", {}).get("parts", [])
    content = "\n".join(part.get("text", "") for part in parts if part.get("text"))
    if not content:
        return {
            "revised": original_text,
            "changes": [
                {
                    "type": "note",
                    "before": "",
                    "after": "",
                    "reason": f"Google API returned no text from {last_model_name}: {json.dumps(data, ensure_ascii=False)[:500]}",
                }
            ],
            "needs_review": ["Google API returned no text. Review this chapter manually."],
            "summary": "Google API ไม่คืนข้อความ จึงคงต้นฉบับเดิมไว้และทำเครื่องหมาย needs review",
        }
    result = extract_json(content)
    result.setdefault("revised", "")
    result.setdefault("changes", [])
    result.setdefault("needs_review", [])
    result.setdefault("summary", "")
    return result


def call_openai_compatible_llm(model: str, system_prompt: str, user_prompt: str) -> dict:
    base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY", "")
    if not base_url or not api_key:
        raise RuntimeError("Set LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL in .env first.")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API error {exc.code}: {body}") from exc

    content = data["choices"][0]["message"]["content"]
    result = extract_json(content)
    result.setdefault("revised", "")
    result.setdefault("changes", [])
    result.setdefault("needs_review", [])
    result.setdefault("summary", "")
    return result


def list_google_models() -> list[dict[str, str]]:
    load_env()
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("Set GOOGLE_API_KEY in .env first.")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    request = urllib.request.Request(endpoint, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google model list error {exc.code}: {body}") from exc

    models = []
    for item in data.get("models", []):
        methods = item.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        name = item.get("name", "").replace("models/", "")
        models.append({
            "name": name,
            "display_name": item.get("displayName", name),
            "methods": ", ".join(methods),
        })
    return sorted(
        models,
        key=lambda model: (
            0 if model["name"].startswith(("gemma", "gemini")) else 1,
            model["name"],
        ),
    )


def update_config_from_body(body: dict) -> dict[str, str]:
    updates = {
        "LLM_PROVIDER": "google",
        "LLM_MODEL": body.get("LLM_MODEL", "").strip(),
        "GOOGLE_FALLBACK_MODELS": body.get("GOOGLE_FALLBACK_MODELS", "").strip(),
        "GOOGLE_RETRY_COUNT": body.get("GOOGLE_RETRY_COUNT", "3").strip() or "3",
        "GOOGLE_RETRY_DELAY_SECONDS": body.get("GOOGLE_RETRY_DELAY_SECONDS", "4").strip() or "4",
        "GOOGLE_TIMEOUT_SECONDS": body.get("GOOGLE_TIMEOUT_SECONDS", "300").strip() or "300",
        "DISCORD_WEBHOOK_URL": body.get("DISCORD_WEBHOOK_URL", "").strip(),
    }
    api_key = body.get("GOOGLE_API_KEY", "").strip()
    if api_key:
        updates["GOOGLE_API_KEY"] = api_key
    if not updates["DISCORD_WEBHOOK_URL"]:
        updates.pop("DISCORD_WEBHOOK_URL")
    if not updates["LLM_MODEL"]:
        updates["LLM_MODEL"] = "gemma-4-31b-it"
    write_env_values(updates)
    return public_config()


def notify_from_body(body: dict) -> dict[str, bool]:
    level = body.get("level", "info")
    colors = {
        "info": 0x47A3FF,
        "success": 0x3CCF91,
        "warning": 0xD8AD4C,
        "error": 0xE06161,
    }
    sent = send_discord_notification(
        body.get("title", "Novel Proofreader"),
        body.get("message", ""),
        colors.get(level, colors["info"]),
    )
    return {"sent": sent}


def save_review(source_file: str, original: str, result: dict) -> dict[str, str]:
    REVIEWED_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    base_name = Path(source_file).name if source_file else f"pasted-{stamp}.md"
    reviewed_path = REVIEWED_DIR / base_name
    report_path = REPORT_DIR / f"{Path(base_name).stem}-{stamp}.md"

    revised = result.get("revised", "")
    reviewed_path.write_text(revised, encoding="utf-8")

    changes = result.get("changes", [])
    needs_review = result.get("needs_review", [])
    report_lines = [
        "# Proofreading Report",
        "",
        f"- date/time: {datetime.now().isoformat(timespec='seconds')}",
        f"- source chapter or file: {source_file or 'pasted text'}",
        f"- reviewed output: {reviewed_path.relative_to(ROOT).as_posix()}",
        "",
        "## Summary",
        "",
        result.get("summary") or "-",
        "",
        "## Changes",
        "",
    ]
    if changes:
        for item in changes:
            report_lines.append(
                f"- {item.get('type', 'note')}: {item.get('before', '')} -> {item.get('after', '')}; {item.get('reason', '')}"
            )
    else:
        report_lines.append("- No detailed changes returned.")
    report_lines.extend(["", "## Needs Review", ""])
    if needs_review:
        report_lines.extend(f"- {item}" for item in needs_review)
    else:
        report_lines.append("- None")
    report_lines.extend(["", "## Original Length", "", f"- {len(original)} characters"])
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    return {
        "reviewed_path": reviewed_path.relative_to(ROOT).as_posix(),
        "report_path": report_path.relative_to(ROOT).as_posix(),
    }


def auto_review_chapter(chapter_path: str) -> dict:
    path = safe_relative_path(chapter_path, SOURCE_DIR)
    original = read_text(path)
    result = call_llm(original, chapter_path)
    saved = save_review(chapter_path, original, result)
    return {
        "source_file": chapter_path,
        "summary": result.get("summary", ""),
        "changes_count": len(result.get("changes", [])),
        "needs_review": result.get("needs_review", []),
        **saved,
    }


INDEX_HTML = r"""<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Novel Proofreader</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0d10;
      --panel: #151922;
      --panel-2: #10141b;
      --ink: #eef2f7;
      --muted: #9aa4b2;
      --line: #2a3240;
      --accent: #47a3ff;
      --accent-2: #3ccf91;
      --danger: #e06161;
      --warning: #d8ad4c;
      --field: #0f131a;
      --field-2: #0c1016;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      padding: 16px 20px;
      border-bottom: 1px solid var(--line);
      background: #0f131a;
      position: sticky;
      top: 0;
      z-index: 2;
    }
    h1 { margin: 0 0 4px; font-size: 22px; letter-spacing: 0; }
    .sub { color: var(--muted); font-size: 14px; }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      color: var(--muted);
      background: var(--panel-2);
      font-size: 13px;
      white-space: nowrap;
    }
    main {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      gap: 16px;
      padding: 16px;
      min-height: calc(100vh - 69px);
    }
    aside, section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    aside {
      padding: 14px;
      overflow: auto;
      align-self: start;
      position: sticky;
      top: 85px;
      max-height: calc(100vh - 102px);
    }
    section { padding: 12px; min-width: 0; }
    label { display: block; color: var(--muted); font-size: 13px; margin: 0 0 6px; }
    select, input, textarea, button {
      font: inherit;
      border-radius: 6px;
      border: 1px solid var(--line);
    }
    select, input {
      width: 100%;
      padding: 8px;
      background: var(--field);
      color: var(--ink);
    }
    input[type="checkbox"] {
      width: auto;
      accent-color: var(--accent);
    }
    select:focus, input:focus, textarea:focus { outline: 2px solid rgba(71, 163, 255, .35); outline-offset: 1px; }
    button {
      cursor: pointer;
      padding: 8px 12px;
      background: var(--accent);
      border-color: var(--accent);
      color: #06111f;
      font-weight: 600;
    }
    button.secondary { background: var(--field); color: var(--ink); border-color: var(--line); }
    button.success { background: var(--accent-2); border-color: var(--accent-2); color: #06160f; }
    button.danger { background: var(--danger); border-color: var(--danger); color: #240707; }
    button:disabled { opacity: .55; cursor: wait; }
    .stack { display: grid; gap: 12px; }
    .panel-title {
      font-size: 12px;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .04em;
      margin-top: 4px;
    }
    .side-group {
      display: grid;
      gap: 8px;
      padding: 10px;
      background: var(--panel-2);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .nav-button.active {
      background: var(--accent);
      border-color: var(--accent);
      color: #06111f;
    }
    .page[hidden] { display: none; }
    .button-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .check-row {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: end;
      margin-bottom: 12px;
    }
    .toolbar > div { min-width: 220px; flex: 1; }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      min-height: 0;
    }
    textarea {
      width: 100%;
      height: 56vh;
      resize: vertical;
      padding: 12px;
      line-height: 1.65;
      background: var(--field-2);
      color: var(--ink);
      caret-color: var(--accent);
    }
    .result {
      white-space: pre-wrap;
      min-height: 160px;
      max-height: 30vh;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: var(--field-2);
      line-height: 1.55;
    }
    .status {
      color: var(--muted);
      font-size: 14px;
      margin-left: auto;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      background: var(--panel-2);
    }
    .error { color: var(--danger); }
    .queue {
      min-height: 90px;
      max-height: 220px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      font-size: 13px;
      line-height: 1.45;
      background: var(--field);
    }
    .progress {
      display: grid;
      gap: 6px;
    }
    .progress-bar {
      height: 10px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--field);
    }
    .progress-fill {
      width: 0%;
      height: 100%;
      background: var(--accent-2);
      transition: width .2s ease;
    }
    .progress-meta {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .chapter-status {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .chapter-name {
      color: var(--ink);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dashboard {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--panel-2);
    }
    .metric-value {
      font-size: 26px;
      font-weight: 700;
      color: var(--ink);
      line-height: 1.1;
    }
    .metric-label {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }
    .work-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-2);
      padding: 12px;
      margin-bottom: 12px;
    }
    details.single-review {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-2);
      padding: 10px;
    }
    details.single-review > summary {
      cursor: pointer;
      color: var(--muted);
      font-weight: 700;
      margin-bottom: 10px;
    }
    .file-manager-layout {
      display: grid;
      grid-template-columns: 360px minmax(0, 1fr);
      gap: 12px;
    }
    .file-list {
      min-height: 520px;
      max-height: 70vh;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--field-2);
    }
    .file-row {
      display: grid;
      grid-template-columns: 26px minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      cursor: pointer;
    }
    .file-row:hover { background: #18202b; }
    .file-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .file-size { color: var(--muted); font-size: 12px; }
    .editor-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }
    #fileEditor {
      min-height: 520px;
      height: 70vh;
    }
    code { color: #b9dcff; }
    ul { margin-top: 8px; padding-left: 20px; }
    li { margin-bottom: 6px; }
    @media (max-width: 900px) {
      main, .grid { grid-template-columns: 1fr; }
      .file-manager-layout { grid-template-columns: 1fr; }
      .dashboard { grid-template-columns: 1fr 1fr; }
      header { align-items: flex-start; flex-direction: column; }
      aside { position: static; max-height: none; }
      textarea { height: 42vh; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Novel Proofreader</h1>
      <div class="sub">ตรวจคำผิด เกลาสำนวน และเช็กคำเฉพาะด้วย glossary ในเครื่อง</div>
    </div>
    <div class="pill">localhost :8010</div>
  </header>
  <main>
    <aside class="stack">
      <div class="panel-title">Tools</div>
      <div class="side-group">
        <button class="secondary nav-button active" id="navProofreader">หน้าแปล / ตรวจ</button>
        <button class="secondary nav-button" id="navFiles">File Manager</button>
      </div>

      <div id="proofreaderTools" class="stack">
      <div class="panel-title">ตรวจไฟล์เดี่ยว</div>
      <div class="side-group">
        <div>
          <label for="chapter">ไฟล์บท</label>
          <select id="chapter"></select>
        </div>
        <div class="button-row">
          <button class="secondary" id="load">โหลดบท</button>
          <button class="secondary" id="clear">ล้าง</button>
        </div>
      </div>

      <div class="panel-title">ตรวจทั้งโฟลเดอร์</div>
      <div class="side-group">
        <div>
          <label for="folder">โฟลเดอร์บท</label>
          <select id="folder"></select>
        </div>
        <button class="secondary" id="loadFolder">โหลดโฟลเดอร์เป็นคิว</button>
        <label class="check-row">
          <input type="checkbox" id="skipReviewed" checked>
          <span>ข้ามไฟล์ที่ตรวจแล้ว</span>
        </label>
        <div class="button-row">
          <button id="autoReview">ตรวจอัตโนมัติ</button>
          <button class="danger" id="stopAuto" disabled>หยุด</button>
        </div>
        <div>
          <label>คิวตรวจ</label>
          <div class="queue" id="queue">ยังไม่มีคิว</div>
        </div>
        <div class="progress">
          <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
          <div class="progress-meta">
            <span id="progressText">0%</span>
            <span id="progressCounts">0/0</span>
          </div>
        </div>
        <div>
          <label>บันทึกการทำงาน</label>
          <div class="queue" id="runLog">ยังไม่ได้เริ่ม</div>
        </div>
      </div>

      <div class="panel-title">อัปโหลดบท</div>
      <div class="side-group">
        <div>
          <label for="uploadFolder">ปลายทางใน chapters/source</label>
          <input id="uploadFolder" placeholder="เช่น story-001 หรือ 1-100">
        </div>
        <div class="button-row">
          <button class="secondary" id="createFolder">สร้างโฟลเดอร์</button>
          <button class="danger" id="deleteFolder">ลบโฟลเดอร์</button>
        </div>
        <div>
          <label for="uploadFiles">ไฟล์ .md/.txt หรือ .zip</label>
          <input type="file" id="uploadFiles" multiple accept=".md,.txt,.zip">
        </div>
        <button class="secondary" id="uploadButton">อัปโหลดเข้า source</button>
      </div>

      <div class="panel-title">ดาวน์โหลด</div>
      <div class="side-group">
        <button class="secondary" id="downloadReviewed">โหลดไฟล์ที่ตรวจแล้ว</button>
        <button class="secondary" id="downloadReports">โหลด reports</button>
        <button class="secondary" id="downloadAll">โหลดทั้งหมด</button>
      </div>
      </div>

      <div class="panel-title">ตั้งค่า</div>
      <div class="side-group">
        <div>
          <label for="googleApiKey">Google API key</label>
          <input id="googleApiKey" type="password" placeholder="เว้นว่างไว้ถ้าไม่เปลี่ยน">
          <div class="sub" id="apiKeyPreview">ยังไม่ได้โหลดค่า</div>
        </div>
        <div>
          <label for="modelSelect">โมเดลหลัก</label>
          <select id="modelSelect"></select>
        </div>
        <div>
          <label for="fallbackModels">Fallback models</label>
          <input id="fallbackModels" placeholder="model1,model2">
        </div>
        <div class="button-row">
          <div>
            <label for="retryCount">Retry</label>
            <input id="retryCount" type="number" min="0" max="10">
          </div>
          <div>
            <label for="timeoutSeconds">Timeout</label>
            <input id="timeoutSeconds" type="number" min="30" step="30">
          </div>
        </div>
        <div>
          <label for="discordWebhook">Discord webhook</label>
          <input id="discordWebhook" type="password" placeholder="เว้นว่างไว้ถ้าไม่เปลี่ยน">
          <div class="sub" id="discordPreview">ยังไม่ได้โหลดค่า</div>
        </div>
        <button class="success" id="saveConfig">บันทึกค่า API</button>
        <button class="secondary" id="testDiscord">ทดสอบ Discord</button>
        <button class="secondary" id="checkModels">เช็กโมเดล Google</button>
        <div class="queue" id="models">ยังไม่ได้เช็ก</div>
      </div>
    </aside>
    <section id="proofreaderPage" class="page">
      <div class="toolbar">
        <div>
          <label for="sourceFile">source file</label>
          <input id="sourceFile" placeholder="pasted text">
        </div>
        <span class="status" id="status">พร้อม</span>
      </div>

      <div class="dashboard">
        <div class="metric">
          <div class="metric-value" id="metricTotal">0</div>
          <div class="metric-label">ไฟล์ในคิว</div>
        </div>
        <div class="metric">
          <div class="metric-value" id="metricDone">0</div>
          <div class="metric-label">ตรวจเสร็จ</div>
        </div>
        <div class="metric">
          <div class="metric-value" id="metricSkipped">0</div>
          <div class="metric-label">ข้าม</div>
        </div>
        <div class="metric">
          <div class="metric-value" id="metricFailed">0</div>
          <div class="metric-label">พลาด</div>
        </div>
      </div>

      <div class="work-panel">
        <label>สถานะทั้งคิว</label>
        <div class="progress">
          <div class="progress-bar"><div class="progress-fill" id="mainProgressFill"></div></div>
          <div class="progress-meta">
            <span id="mainProgressText">0%</span>
            <span id="mainProgressCounts">0/0</span>
          </div>
        </div>
      </div>

      <div class="work-panel">
        <label>สถานะตอนที่กำลังตรวจ</label>
        <div class="chapter-status">
          <span class="chapter-name" id="chapterProgressName">ยังไม่ได้เริ่ม</span>
          <span id="chapterProgressStage">0%</span>
        </div>
        <div class="progress">
          <div class="progress-bar"><div class="progress-fill" id="chapterProgressFill"></div></div>
          <div class="progress-meta">
            <span id="chapterProgressText">รอเริ่ม</span>
            <span id="chapterProgressTime">00:00</span>
          </div>
        </div>
      </div>

      <div class="grid" style="margin-bottom:12px">
        <div>
          <label>ไฟล์ล่าสุด / สรุป</label>
          <div class="result" id="summary" style="min-height:220px;max-height:38vh"></div>
        </div>
        <div>
          <label>รายการแก้ / report ล่าสุด</label>
          <div class="result" id="changes" style="min-height:220px;max-height:38vh"></div>
        </div>
      </div>

      <details class="single-review">
        <summary>ตรวจไฟล์เดี่ยว / วางข้อความเอง</summary>
        <div class="toolbar">
          <button id="review">ตรวจด้วย LLM</button>
          <button class="success" id="save" disabled>บันทึกผล + report</button>
        </div>
        <div class="grid">
          <div>
            <label for="original">ต้นฉบับ</label>
            <textarea id="original" spellcheck="false"></textarea>
          </div>
          <div>
            <label for="revised">ฉบับแก้</label>
            <textarea id="revised" spellcheck="false"></textarea>
          </div>
        </div>
      </details>
    </section>
    <section id="fileManagerPage" class="page" hidden>
      <div class="toolbar">
        <div>
          <label for="fileRoot">root</label>
          <select id="fileRoot">
            <option value="chapters">chapters</option>
            <option value="glossary">glossary</option>
            <option value="glossary_raw">glossary_raw</option>
            <option value="reports">reports</option>
            <option value="wiki">wiki</option>
          </select>
        </div>
        <div>
          <label for="filePath">path</label>
          <input id="filePath" placeholder="">
        </div>
        <button class="secondary" id="fileUp">ขึ้น</button>
        <button class="secondary" id="fileRefresh">รีเฟรช</button>
        <div>
          <label for="fileUploadInput">upload</label>
          <input type="file" id="fileUploadInput" multiple accept=".md,.txt,.zip,.json,.yml,.yaml">
        </div>
        <button class="secondary" id="fileUploadButton">อัปโหลด</button>
        <span class="status" id="fileStatus">พร้อม</span>
      </div>
      <div class="file-manager-layout">
        <div>
          <label>ไฟล์</label>
          <div class="file-list" id="fileList"></div>
        </div>
        <div>
          <div class="editor-actions">
            <button class="success" id="fileSave" disabled>บันทึก</button>
            <button class="secondary" id="fileDownload" disabled>ดาวน์โหลด</button>
            <button class="danger" id="fileDelete" disabled>ลบ</button>
          </div>
          <label id="fileEditorLabel">ยังไม่ได้เลือกไฟล์</label>
          <textarea id="fileEditor" spellcheck="false" disabled></textarea>
        </div>
      </div>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    let lastResult = null;
    let queue = [];
    let stopRequested = false;
    let runStats = {done: 0, skipped: 0, failed: 0, total: 0};
    let runLog = [];
    let chapterTimer = null;
    let chapterStartedAt = null;
    let chapterEstimatedPercent = 0;
    let selectedFile = null;

    function showPage(page) {
      const files = page === "files";
      $("proofreaderPage").hidden = files;
      $("fileManagerPage").hidden = !files;
      $("proofreaderTools").hidden = files;
      $("navProofreader").classList.toggle("active", !files);
      $("navFiles").classList.toggle("active", files);
      if (files) loadFileList().catch(err => setFileStatus(err.message, true));
    }

    function appendLog(text) {
      const time = new Date().toLocaleTimeString("th-TH", {hour12: false});
      runLog.push(`[${time}] ${text}`);
      if (runLog.length > 120) runLog = runLog.slice(-120);
      $("runLog").textContent = runLog.join("\n");
      $("runLog").scrollTop = $("runLog").scrollHeight;
    }

    function setProgress(done, total) {
      const percent = total ? Math.round((done / total) * 100) : 0;
      $("progressFill").style.width = `${percent}%`;
      $("progressText").textContent = `${percent}%`;
      $("progressCounts").textContent = `${done}/${total} เสร็จ ${runStats.done} ข้าม ${runStats.skipped} พลาด ${runStats.failed}`;
      $("mainProgressFill").style.width = `${percent}%`;
      $("mainProgressText").textContent = `${percent}%`;
      $("mainProgressCounts").textContent = `${done}/${total} เสร็จ ${runStats.done} ข้าม ${runStats.skipped} พลาด ${runStats.failed}`;
      $("metricTotal").textContent = total;
      $("metricDone").textContent = runStats.done;
      $("metricSkipped").textContent = runStats.skipped;
      $("metricFailed").textContent = runStats.failed;
    }

    function formatElapsed(ms) {
      const total = Math.max(0, Math.floor(ms / 1000));
      const min = String(Math.floor(total / 60)).padStart(2, "0");
      const sec = String(total % 60).padStart(2, "0");
      return `${min}:${sec}`;
    }

    function setChapterProgress(percent, stage, file="") {
      chapterEstimatedPercent = Math.max(chapterEstimatedPercent, percent);
      $("chapterProgressFill").style.width = `${chapterEstimatedPercent}%`;
      $("chapterProgressStage").textContent = `${chapterEstimatedPercent}%`;
      $("chapterProgressText").textContent = stage;
      if (file) $("chapterProgressName").textContent = file;
    }

    function startChapterProgress(file) {
      clearInterval(chapterTimer);
      chapterStartedAt = Date.now();
      chapterEstimatedPercent = 0;
      setChapterProgress(8, "อ่านไฟล์และเตรียม prompt", file);
      $("chapterProgressTime").textContent = "00:00";
      chapterTimer = setInterval(() => {
        if (!chapterStartedAt) return;
        const elapsed = Date.now() - chapterStartedAt;
        $("chapterProgressTime").textContent = formatElapsed(elapsed);
        if (chapterEstimatedPercent < 90) {
          const next = Math.min(90, 25 + Math.floor(elapsed / 4000) * 3);
          setChapterProgress(next, "รอโมเดลตรวจและคืนผล");
        }
      }, 1000);
    }

    function finishChapterProgress(stage) {
      clearInterval(chapterTimer);
      chapterTimer = null;
      setChapterProgress(100, stage);
      if (chapterStartedAt) {
        $("chapterProgressTime").textContent = formatElapsed(Date.now() - chapterStartedAt);
      }
    }

    function resetChapterProgress() {
      clearInterval(chapterTimer);
      chapterTimer = null;
      chapterStartedAt = null;
      chapterEstimatedPercent = 0;
      $("chapterProgressFill").style.width = "0%";
      $("chapterProgressStage").textContent = "0%";
      $("chapterProgressText").textContent = "รอเริ่ม";
      $("chapterProgressTime").textContent = "00:00";
      $("chapterProgressName").textContent = "ยังไม่ได้เริ่ม";
    }

    function queueMarker(item, index, activeIndex, done) {
      if (done[item.path]) return done[item.path];
      if (index === activeIndex) return "กำลังตรวจ";
      if (item.reviewed) return "เสร็จแล้ว";
      return "รอ";
    }

    function renderQueue(activeIndex=-1, done={}) {
      if (!queue.length) {
        $("queue").textContent = "ยังไม่มีคิว";
        return;
      }
      $("queue").textContent = queue.map((item, index) => {
        const marker = queueMarker(item, index, activeIndex, done);
        return `${index + 1}. [${marker}] ${item.path}`;
      }).join("\n");
    }

    function setStatus(text, isError=false) {
      $("status").textContent = text;
      $("status").className = isError ? "status error" : "status";
    }

    function setFileStatus(text, isError=false) {
      $("fileStatus").textContent = text;
      $("fileStatus").className = isError ? "status error" : "status";
    }

    async function api(path, options={}) {
      const res = await fetch(path, {
        headers: {"Content-Type": "application/json"},
        ...options
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "request failed");
      return data;
    }

    async function notifyDiscord(title, message, level="info") {
      try {
        await api("/api/notify", {
          method: "POST",
          body: JSON.stringify({title, message, level})
        });
      } catch (err) {
        appendLog(`Discord notify failed: ${err.message}`);
      }
    }

    async function loadChapters() {
      const data = await api("/api/chapters");
      $("chapter").innerHTML = data.chapters.map(c => `<option value="${c.path}">${c.name}</option>`).join("");
    }

    async function loadFolders() {
      const data = await api("/api/folders");
      $("folder").innerHTML = data.folders.map(c => `<option value="${c.path}">${c.name}</option>`).join("");
    }

    async function loadConfig() {
      const data = await api("/api/config");
      $("apiKeyPreview").textContent = data.GOOGLE_API_KEY_SET === "true" ? `ตั้งค่าแล้ว ${data.GOOGLE_API_KEY_PREVIEW}` : "ยังไม่มี API key";
      $("fallbackModels").value = data.GOOGLE_FALLBACK_MODELS || "";
      $("retryCount").value = data.GOOGLE_RETRY_COUNT || "3";
      $("timeoutSeconds").value = data.GOOGLE_TIMEOUT_SECONDS || "300";
      $("discordPreview").textContent = data.DISCORD_WEBHOOK_SET === "true" ? `ตั้งค่าแล้ว ${data.DISCORD_WEBHOOK_PREVIEW}` : "ยังไม่มี webhook";
      const currentModel = data.LLM_MODEL || "gemma-4-31b-it";
      $("modelSelect").innerHTML = `<option value="${currentModel}">${currentModel}</option>`;
      $("modelSelect").value = currentModel;
    }

    function fileIcon(item) {
      return item.type === "dir" ? "DIR" : "TXT";
    }

    function formatSize(size) {
      if (!size) return "";
      if (size < 1024) return `${size} B`;
      if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
      return `${(size / 1024 / 1024).toFixed(1)} MB`;
    }

    async function loadFileList() {
      const root = $("fileRoot").value;
      const path = $("filePath").value.trim();
      const data = await api(`/api/files?root=${encodeURIComponent(root)}&path=${encodeURIComponent(path)}`);
      $("filePath").value = data.path || "";
      $("fileList").innerHTML = data.items.map(item => `
        <div class="file-row" data-type="${item.type}" data-path="${item.path}" data-editable="${item.editable}">
          <div class="file-size">${fileIcon(item)}</div>
          <div class="file-name" title="${item.path}">${item.name}</div>
          <div class="file-size">${item.type === "file" ? formatSize(item.size) : ""}</div>
        </div>
      `).join("") || `<div class="file-row"><div></div><div class="file-name">ว่าง</div><div></div></div>`;
      selectedFile = null;
      $("fileEditor").value = "";
      $("fileEditor").disabled = true;
      $("fileEditorLabel").textContent = "ยังไม่ได้เลือกไฟล์";
      $("fileSave").disabled = true;
      $("fileDownload").disabled = true;
      $("fileDelete").disabled = true;
      setFileStatus("โหลดรายการแล้ว");
    }

    async function openFileItem(row) {
      const type = row.dataset.type;
      const path = row.dataset.path;
      if (type === "dir") {
        $("filePath").value = path;
        await loadFileList();
        return;
      }
      selectedFile = {root: $("fileRoot").value, path};
      $("fileEditorLabel").textContent = `${selectedFile.root}/${selectedFile.path}`;
      $("fileDownload").disabled = false;
      $("fileDelete").disabled = false;
      if (row.dataset.editable !== "true") {
        $("fileEditor").value = "ไฟล์ชนิดนี้เปิดแก้ในเว็บไม่ได้ แต่ดาวน์โหลดหรือลบได้";
        $("fileEditor").disabled = true;
        $("fileSave").disabled = true;
        setFileStatus("เลือกไฟล์แล้ว");
        return;
      }
      const data = await api(`/api/file?root=${encodeURIComponent(selectedFile.root)}&path=${encodeURIComponent(selectedFile.path)}`);
      $("fileEditor").value = data.text;
      $("fileEditor").disabled = false;
      $("fileSave").disabled = false;
      setFileStatus("เปิดไฟล์แล้ว");
    }

    $("load").onclick = async () => {
      try {
        const file = $("chapter").value;
        const data = await api(`/api/chapter?path=${encodeURIComponent(file)}`);
        $("original").value = data.text;
        $("sourceFile").value = file;
        setStatus("โหลดบทแล้ว");
      } catch (err) {
        setStatus(err.message, true);
      }
    };

    $("loadFolder").onclick = async () => {
      try {
        const folder = $("folder").value;
        const data = await api(`/api/folder?path=${encodeURIComponent(folder)}`);
        queue = data.chapters;
        runStats = {done: 0, skipped: 0, failed: 0, total: queue.length};
        runLog = [];
        renderQueue();
        const reviewedCount = queue.filter(item => item.reviewed).length;
        setProgress(0, queue.length);
        resetChapterProgress();
        appendLog(`โหลดคิว ${queue.length} ไฟล์ จากโฟลเดอร์ ${folder || "ทั้งหมด"} ตรวจแล้ว ${reviewedCount} ไฟล์`);
        setStatus(`โหลดคิว ${queue.length} ไฟล์แล้ว ตรวจแล้ว ${reviewedCount} ไฟล์`);
      } catch (err) {
        setStatus(err.message, true);
      }
    };

    $("uploadButton").onclick = async () => {
      const files = $("uploadFiles").files;
      if (!files.length) return setStatus("ยังไม่ได้เลือกไฟล์อัปโหลด", true);
      const form = new FormData();
      form.append("folder", $("uploadFolder").value.trim());
      for (const file of files) form.append("files", file);
      $("uploadButton").disabled = true;
      setStatus("กำลังอัปโหลด...");
      try {
        const res = await fetch("/api/upload", {method: "POST", body: form});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "upload failed");
        if (!data.count) throw new Error("อัปโหลดไม่สำเร็จ: รองรับเฉพาะ .md, .txt, .zip, .json, .yml, .yaml");
        appendLog(`อัปโหลด ${data.files.length} ไฟล์ ไปที่ ${data.folder}`);
        setStatus(`อัปโหลดแล้ว ${data.files.length} ไฟล์`);
        await Promise.all([loadChapters(), loadFolders()]);
        $("folder").value = data.folder;
        $("loadFolder").click();
      } catch (err) {
        setStatus(err.message, true);
      } finally {
        $("uploadButton").disabled = false;
      }
    };

    $("createFolder").onclick = async () => {
      const folder = $("uploadFolder").value.trim();
      if (!folder) return setStatus("ใส่ชื่อโฟลเดอร์ก่อน", true);
      try {
        const data = await api("/api/source-folder", {
          method: "POST",
          body: JSON.stringify({action: "create", folder})
        });
        await loadFolders();
        $("folder").value = data.folder;
        setStatus(`สร้างโฟลเดอร์ ${data.folder} แล้ว`);
      } catch (err) {
        setStatus(err.message, true);
      }
    };

    $("deleteFolder").onclick = async () => {
      const folder = $("folder").value || $("uploadFolder").value.trim();
      if (!folder) return setStatus("ไม่อนุญาตให้ลบ root source", true);
      if (!confirm(`ลบ chapters/source/${folder} ? ไฟล์ต้นฉบับในโฟลเดอร์นี้จะหาย`)) return;
      try {
        const data = await api("/api/source-folder", {
          method: "POST",
          body: JSON.stringify({action: "delete", folder})
        });
        queue = [];
        renderQueue();
        await Promise.all([loadChapters(), loadFolders()]);
        setStatus(`ลบโฟลเดอร์ ${data.deleted} แล้ว`);
      } catch (err) {
        setStatus(err.message, true);
      }
    };

    function download(kind) {
      window.location.href = `/api/download?kind=${encodeURIComponent(kind)}`;
    }

    $("downloadReviewed").onclick = () => download("reviewed");
    $("downloadReports").onclick = () => download("reports");
    $("downloadAll").onclick = () => download("all");


    $("clear").onclick = () => {
      $("original").value = "";
      $("revised").value = "";
      $("summary").textContent = "";
      $("changes").textContent = "";
      $("sourceFile").value = "";
      $("save").disabled = true;
      lastResult = null;
      setStatus("ล้างแล้ว");
    };

    $("autoReview").onclick = async () => {
      if (!queue.length) return setStatus("ยังไม่มีคิว ให้โหลดโฟลเดอร์ก่อน", true);
      stopRequested = false;
      const done = {};
      runStats = {done: 0, skipped: 0, failed: 0, total: queue.length};
      setProgress(0, queue.length);
      appendLog("เริ่มตรวจอัตโนมัติ");
      notifyDiscord("Novel Proofreader: เริ่มตรวจคิว", `เริ่มตรวจ ${queue.length} ไฟล์`, "info");
      $("autoReview").disabled = true;
      $("stopAuto").disabled = false;
      $("review").disabled = true;
      $("save").disabled = true;
      try {
        for (let i = 0; i < queue.length; i++) {
          if (stopRequested) break;
          const item = queue[i];
          if ($("skipReviewed").checked && item.reviewed) {
            done[item.path] = "ข้าม/เสร็จแล้ว";
            runStats.skipped += 1;
            setProgress(runStats.done + runStats.skipped + runStats.failed, queue.length);
            appendLog(`ข้าม ${item.path} เพราะมีผลตรวจแล้ว`);
            renderQueue(-1, done);
            continue;
          }
          renderQueue(i, done);
          appendLog(`เริ่มตรวจ ${item.path}`);
          startChapterProgress(item.path);
          setChapterProgress(18, "ส่งคำขอไป Google API");
          setStatus(`กำลังตรวจ ${i + 1}/${queue.length}: ${item.path}`);
          try {
            const data = await api("/api/auto-review", {
              method: "POST",
              body: JSON.stringify({path: item.path})
            });
            setChapterProgress(94, "ได้รับผลแล้ว กำลังบันทึก report");
            done[item.path] = data.needs_review && data.needs_review.length ? "เสร็จ/ต้องทวน" : "เสร็จ";
            item.reviewed = true;
            item.reviewed_path = data.reviewed_path;
            runStats.done += 1;
            $("sourceFile").value = item.path;
            $("summary").textContent = data.summary || "";
            $("changes").textContent = `บันทึก: ${data.reviewed_path}\nรายงาน: ${data.report_path}\nchanges: ${data.changes_count}`;
            appendLog(`เสร็จ ${item.path} changes=${data.changes_count}${data.needs_review && data.needs_review.length ? " needs_review" : ""}`);
            finishChapterProgress(data.needs_review && data.needs_review.length ? "เสร็จ แต่ต้องทวน" : "เสร็จ");
          } catch (err) {
            done[item.path] = "ผิดพลาด";
            runStats.failed += 1;
            appendLog(`ผิดพลาด ${item.path}: ${err.message}`);
            notifyDiscord("Novel Proofreader: ตรวจไฟล์ผิดพลาด", `${item.path}\n${err.message}`, "error");
            finishChapterProgress("ผิดพลาด");
          }
          setProgress(runStats.done + runStats.skipped + runStats.failed, queue.length);
          renderQueue(-1, done);
        }
        const finalMessage = `ทั้งหมด ${queue.length} | เสร็จ ${runStats.done} | ข้าม ${runStats.skipped} | พลาด ${runStats.failed}`;
        appendLog(stopRequested ? "หยุดแล้วหลังไฟล์ล่าสุด" : "ตรวจคิวครบแล้ว");
        notifyDiscord(
          stopRequested ? "Novel Proofreader: หยุดตรวจคิว" : "Novel Proofreader: ตรวจคิวเสร็จ",
          finalMessage,
          runStats.failed ? "warning" : "success"
        );
        setStatus(stopRequested ? "หยุดแล้วหลังไฟล์ล่าสุด" : "ตรวจคิวครบแล้ว");
      } catch (err) {
        setStatus(err.message, true);
        notifyDiscord("Novel Proofreader: Batch error", err.message, "error");
      } finally {
        $("autoReview").disabled = false;
        $("stopAuto").disabled = true;
        $("review").disabled = false;
      }
    };

    $("stopAuto").onclick = () => {
      stopRequested = true;
      setStatus("รับคำสั่งหยุดแล้ว จะหยุดหลังไฟล์ปัจจุบันเสร็จ");
    };

    $("checkModels").onclick = async () => {
      $("checkModels").disabled = true;
      setStatus("กำลังเช็กโมเดลจาก Google...");
      try {
        const data = await api("/api/google-models");
        $("models").textContent = data.models.map(m => `- ${m.name}`).join("\n") || "ไม่พบโมเดล generateContent";
        const current = $("modelSelect").value;
        $("modelSelect").innerHTML = data.models.map(m => `<option value="${m.name}">${m.name}</option>`).join("");
        if ([...$("modelSelect").options].some(option => option.value === current)) {
          $("modelSelect").value = current;
        }
        setStatus(`พบ ${data.models.length} โมเดลที่ใช้ generateContent ได้`);
      } catch (err) {
        setStatus(err.message, true);
      } finally {
        $("checkModels").disabled = false;
      }
    };

    $("review").onclick = async () => {
      const text = $("original").value.trim();
      if (!text) return setStatus("ยังไม่มีข้อความให้ตรวจ", true);
      $("review").disabled = true;
      $("save").disabled = true;
      setStatus("กำลังส่งให้ LLM ตรวจ...");
      try {
        const data = await api("/api/review", {
          method: "POST",
          body: JSON.stringify({text, source_file: $("sourceFile").value.trim()})
        });
        lastResult = data.result;
        $("revised").value = lastResult.revised || "";
        $("summary").textContent = lastResult.summary || "";
        const changes = (lastResult.changes || []).map(item =>
          `- [${item.type || "note"}] ${item.before || ""} -> ${item.after || ""}\n  ${item.reason || ""}`
        ).join("\n");
        const needs = (lastResult.needs_review || []).map(item => `- needs review: ${item}`).join("\n");
        $("changes").textContent = [changes, needs].filter(Boolean).join("\n\n") || "-";
        $("save").disabled = false;
        setStatus("ตรวจเสร็จแล้ว");
      } catch (err) {
        setStatus(err.message, true);
      } finally {
        $("review").disabled = false;
      }
    };

    $("save").onclick = async () => {
      if (!lastResult) return;
      setStatus("กำลังบันทึก...");
      try {
        lastResult.revised = $("revised").value;
        const data = await api("/api/save", {
          method: "POST",
          body: JSON.stringify({
            source_file: $("sourceFile").value.trim(),
            original: $("original").value,
            result: lastResult
          })
        });
        setStatus(`บันทึกแล้ว: ${data.reviewed_path}, ${data.report_path}`);
      } catch (err) {
        setStatus(err.message, true);
      }
    };

    $("saveConfig").onclick = async () => {
      $("saveConfig").disabled = true;
      setStatus("กำลังบันทึกค่า API...");
      try {
        const payload = {
          GOOGLE_API_KEY: $("googleApiKey").value.trim(),
          LLM_MODEL: $("modelSelect").value.trim(),
          GOOGLE_FALLBACK_MODELS: $("fallbackModels").value.trim(),
          GOOGLE_RETRY_COUNT: $("retryCount").value.trim(),
          GOOGLE_TIMEOUT_SECONDS: $("timeoutSeconds").value.trim(),
          DISCORD_WEBHOOK_URL: $("discordWebhook").value.trim()
        };
        const data = await api("/api/config", {method: "POST", body: JSON.stringify(payload)});
        $("googleApiKey").value = "";
        $("discordWebhook").value = "";
        $("apiKeyPreview").textContent = data.GOOGLE_API_KEY_SET === "true" ? `ตั้งค่าแล้ว ${data.GOOGLE_API_KEY_PREVIEW}` : "ยังไม่มี API key";
        $("discordPreview").textContent = data.DISCORD_WEBHOOK_SET === "true" ? `ตั้งค่าแล้ว ${data.DISCORD_WEBHOOK_PREVIEW}` : "ยังไม่มี webhook";
        setStatus("บันทึกค่า API แล้ว");
      } catch (err) {
        setStatus(err.message, true);
      } finally {
        $("saveConfig").disabled = false;
      }
    };

    $("testDiscord").onclick = async () => {
      $("testDiscord").disabled = true;
      setStatus("กำลังส่งทดสอบ Discord...");
      try {
        const data = await api("/api/notify", {
          method: "POST",
          body: JSON.stringify({title: "Novel Proofreader", message: "Discord webhook test สำเร็จ", level: "info"})
        });
        setStatus(data.sent ? "ส่ง Discord แล้ว" : "ยังไม่ได้ตั้งค่า Discord webhook");
      } catch (err) {
        setStatus(err.message, true);
      } finally {
        $("testDiscord").disabled = false;
      }
    };

    $("navProofreader").onclick = () => showPage("proofreader");
    $("navFiles").onclick = () => showPage("files");

    $("fileRoot").onchange = () => {
      $("filePath").value = "";
      loadFileList().catch(err => setFileStatus(err.message, true));
    };
    $("fileRefresh").onclick = () => loadFileList().catch(err => setFileStatus(err.message, true));
    $("fileUp").onclick = async () => {
      const parts = $("filePath").value.split("/").filter(Boolean);
      parts.pop();
      $("filePath").value = parts.join("/");
      await loadFileList().catch(err => setFileStatus(err.message, true));
    };
    $("fileList").onclick = (event) => {
      const row = event.target.closest(".file-row");
      if (!row || !row.dataset.path) return;
      openFileItem(row).catch(err => setFileStatus(err.message, true));
    };
    $("fileSave").onclick = async () => {
      if (!selectedFile) return;
      $("fileSave").disabled = true;
      try {
        await api("/api/file", {
          method: "POST",
          body: JSON.stringify({...selectedFile, text: $("fileEditor").value})
        });
        setFileStatus("บันทึกแล้ว");
      } catch (err) {
        setFileStatus(err.message, true);
      } finally {
        $("fileSave").disabled = false;
      }
    };
    $("fileDownload").onclick = () => {
      if (!selectedFile) return;
      window.location.href = `/api/file-download?root=${encodeURIComponent(selectedFile.root)}&path=${encodeURIComponent(selectedFile.path)}`;
    };
    $("fileDelete").onclick = async () => {
      if (!selectedFile) return;
      if (!confirm(`ลบ ${selectedFile.root}/${selectedFile.path}?`)) return;
      try {
        await api("/api/file-delete", {method: "POST", body: JSON.stringify(selectedFile)});
        selectedFile = null;
        await loadFileList();
        setFileStatus("ลบแล้ว");
      } catch (err) {
        setFileStatus(err.message, true);
      }
    };
    $("fileUploadButton").onclick = async () => {
      const files = $("fileUploadInput").files;
      if (!files.length) return setFileStatus("ยังไม่ได้เลือกไฟล์", true);
      const form = new FormData();
      form.append("folder", $("filePath").value.trim());
      for (const file of files) form.append("files", file);
      $("fileUploadButton").disabled = true;
      setFileStatus("กำลังอัปโหลด...");
      try {
        const res = await fetch("/api/file-upload", {
          method: "POST",
          headers: {"X-File-Root": $("fileRoot").value},
          body: form
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "upload failed");
        if (!data.count) throw new Error("อัปโหลดไม่สำเร็จ: รองรับเฉพาะ .md, .txt, .zip, .json, .yml, .yaml");
        $("fileUploadInput").value = "";
        await loadFileList();
        setFileStatus(`อัปโหลดแล้ว ${data.count} ไฟล์`);
      } catch (err) {
        setFileStatus(err.message, true);
      } finally {
        $("fileUploadButton").disabled = false;
      }
    };

    Promise.all([loadChapters(), loadFolders(), loadConfig()]).catch(err => setStatus(err.message, true));
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def is_authorized(self) -> bool:
        if not auth_enabled():
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        except Exception:
            return False
        username, separator, password = decoded.partition(":")
        return (
            separator == ":"
            and username == os.environ.get("AUTH_USERNAME")
            and password == os.environ.get("AUTH_PASSWORD")
        )

    def require_auth(self) -> bool:
        if self.is_authorized():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Novel Proofreader"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Authentication required".encode("utf-8"))
        return False

    def send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, filename: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        path.unlink(missing_ok=True)

    def send_existing_file(self, path: Path, filename: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def handle_upload(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        folder_value, files = parse_multipart_form(self.headers.get("Content-Type", ""), body)
        folder = safe_folder_name(folder_value)
        target_dir = (SOURCE_DIR / folder).resolve()
        if SOURCE_DIR.resolve() not in target_dir.parents and target_dir != SOURCE_DIR.resolve():
            raise ValueError("upload folder is outside chapters/source")
        target_dir.mkdir(parents=True, exist_ok=True)

        saved = save_uploaded_files(target_dir, files, SOURCE_DIR)

        self.send_json({"folder": folder, "files": sorted(saved), "count": len(saved)})

    def handle_file_upload(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        rel_path, files = parse_multipart_form(self.headers.get("Content-Type", ""), body)
        root_name = self.headers.get("X-File-Root", "chapters")
        target_dir = file_manager_path(root_name, rel_path)
        if target_dir.exists() and not target_dir.is_dir():
            target_dir = target_dir.parent
        saved = save_uploaded_files(target_dir, files, FILE_MANAGER_ROOTS[root_name].resolve())
        self.send_json({"root": root_name, "path": rel_path, "files": saved, "count": len(saved)})

    def do_GET(self) -> None:
        if not self.require_auth():
            return
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_html(INDEX_HTML)
            elif parsed.path == "/api/config":
                self.send_json(public_config())
            elif parsed.path == "/api/chapters":
                self.send_json({"chapters": list_chapters()})
            elif parsed.path == "/api/folders":
                self.send_json({"folders": list_chapter_folders()})
            elif parsed.path == "/api/folder":
                query = parse_qs(parsed.query)
                folder_path = query.get("path", [""])[0]
                self.send_json({"path": folder_path, "chapters": chapters_in_folder(folder_path)})
            elif parsed.path == "/api/chapter-status":
                query = parse_qs(parsed.query)
                chapter_path = query.get("path", [""])[0]
                self.send_json(chapter_status(chapter_path))
            elif parsed.path == "/api/download":
                query = parse_qs(parsed.query)
                kind = query.get("kind", ["all"])[0]
                folder = query.get("folder", [""])[0]
                zip_path, filename = build_download_zip(kind, folder)
                self.send_file(zip_path, filename)
            elif parsed.path == "/api/files":
                query = parse_qs(parsed.query)
                root = query.get("root", ["chapters"])[0]
                path = query.get("path", [""])[0]
                self.send_json(list_files(root, path))
            elif parsed.path == "/api/file":
                query = parse_qs(parsed.query)
                root = query.get("root", ["chapters"])[0]
                path = query.get("path", [""])[0]
                self.send_json(read_managed_file(root, path))
            elif parsed.path == "/api/file-download":
                query = parse_qs(parsed.query)
                root = query.get("root", ["chapters"])[0]
                rel_path = query.get("path", [""])[0]
                path = file_manager_path(root, rel_path)
                if not path.is_file():
                    raise FileNotFoundError(rel_path)
                self.send_existing_file(path, path.name)
            elif parsed.path == "/api/google-models":
                self.send_json({"models": list_google_models()})
            elif parsed.path == "/api/chapter":
                query = parse_qs(parsed.query)
                chapter_path = query.get("path", [""])[0]
                path = safe_relative_path(chapter_path, SOURCE_DIR)
                self.send_json({"path": chapter_path, "text": read_text(path)})
            else:
                self.send_json({"error": "not found"}, 404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        if not self.require_auth():
            return
        try:
            if self.path == "/api/review":
                body = self.read_json_body()
                result = call_llm(body.get("text", ""), body.get("source_file", ""))
                self.send_json({"result": result})
            elif self.path == "/api/config":
                body = self.read_json_body()
                self.send_json(update_config_from_body(body))
            elif self.path == "/api/notify":
                body = self.read_json_body()
                self.send_json(notify_from_body(body))
            elif self.path == "/api/auto-review":
                body = self.read_json_body()
                result = auto_review_chapter(body.get("path", ""))
                self.send_json(result)
            elif self.path == "/api/upload":
                self.handle_upload()
            elif self.path == "/api/file-upload":
                self.handle_file_upload()
            elif self.path == "/api/source-folder":
                body = self.read_json_body()
                action = body.get("action", "create")
                folder = body.get("folder", "")
                if action == "delete":
                    self.send_json(delete_source_folder(folder))
                else:
                    self.send_json(create_source_folder(folder))
            elif self.path == "/api/file":
                body = self.read_json_body()
                self.send_json(write_managed_file(body.get("root", "chapters"), body.get("path", ""), body.get("text", "")))
            elif self.path == "/api/file-delete":
                body = self.read_json_body()
                self.send_json(delete_managed_path(body.get("root", "chapters"), body.get("path", "")))
            elif self.path == "/api/save":
                body = self.read_json_body()
                paths = save_review(
                    body.get("source_file", ""),
                    body.get("original", ""),
                    body.get("result", {}),
                )
                self.send_json(paths)
            else:
                self.send_json({"error": "not found"}, 404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def log_message(self, format: str, *args) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}")


def main() -> None:
    load_env()
    REVIEWED_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Novel Proofreader running at http://{HOST}:{PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
