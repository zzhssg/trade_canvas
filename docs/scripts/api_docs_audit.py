from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")


@dataclass(frozen=True)
class Section:
    kind: str  # "http" | "ws"
    method: str
    path: str
    file: Path
    start_line: int
    body_lines: list[str]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_openapi(repo_root: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, "scripts/gen_openapi_json.py"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or "")
        raise RuntimeError(f"OpenAPI schema generation failed (exit={proc.returncode})")
    return json.loads(proc.stdout)


def extract_openapi_endpoints(schema: dict) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    expected: set[tuple[str, str]] = set()
    request_body: set[tuple[str, str]] = set()
    paths = schema.get("paths") or {}
    for path, methods in paths.items():
        if not isinstance(path, str) or not path.startswith("/api/"):
            continue
        if not isinstance(methods, dict):
            continue
        for m, spec in methods.items():
            if not isinstance(m, str):
                continue
            mm = m.upper()
            if mm not in HTTP_METHODS:
                continue
            expected.add((mm, path))
            if isinstance(spec, dict) and spec.get("requestBody") is not None:
                request_body.add((mm, path))
    return expected, request_body


def extract_ws_routes(repo_root: Path) -> set[str]:
    main_py = repo_root / "backend/app/main.py"
    text = main_py.read_text(encoding="utf-8")
    found = set(re.findall(r'@app\.websocket\("([^"]+)"\)', text))
    return {p for p in found if p.startswith("/ws/")}


def iter_md_files(repo_root: Path) -> list[Path]:
    base = repo_root / "docs/core/api/v1"
    if not base.exists():
        return []
    return sorted([p for p in base.glob("*.md") if p.is_file()])


def parse_sections(repo_root: Path) -> list[Section]:
    http_re = re.compile(r"^##\s+(GET|POST|PUT|DELETE|PATCH)\s+(/api/\S+)\s*$")
    ws_re = re.compile(r"^##\s+WS\s+(/ws/\S+)\s*$")

    sections: list[Section] = []
    for path in iter_md_files(repo_root):
        lines = path.read_text(encoding="utf-8").splitlines()
        starts: list[tuple[int, str, str, str]] = []
        for i, line in enumerate(lines, start=1):
            m = http_re.match(line.strip())
            if m:
                starts.append((i, "http", m.group(1), m.group(2)))
                continue
            m = ws_re.match(line.strip())
            if m:
                starts.append((i, "ws", "WS", m.group(1)))

        for idx, (start_line, kind, method, ep_path) in enumerate(starts):
            end_line = (starts[idx + 1][0] - 1) if idx + 1 < len(starts) else len(lines)
            body = lines[start_line:end_line]
            sections.append(
                Section(kind=kind, method=method, path=ep_path, file=path, start_line=start_line, body_lines=body)
            )
    return sections


def section_has_semantics(sec: Section) -> bool:
    sem_re = re.compile(r"^###\s+(语义|说明)\s*$")
    has_header = False
    has_text = False
    for line in sec.body_lines:
        s = line.rstrip()
        if sem_re.match(s.strip()):
            has_header = True
            continue
        if has_header:
            if s.strip().startswith("### "):
                break
            if s.strip():
                has_text = True
    return has_header and has_text


def extract_code_fences(sec: Section) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    in_fence = False
    lang = ""
    buf: list[str] = []
    for line in sec.body_lines:
        if line.startswith("```") and not in_fence:
            in_fence = True
            lang = line[3:].strip().lower()
            buf = []
            continue
        if line.startswith("```") and in_fence:
            in_fence = False
            blocks.append((lang, "\n".join(buf)))
            lang = ""
            buf = []
            continue
        if in_fence:
            buf.append(line)
    return blocks


def section_examples_ok(sec: Section, *, needs_request_body: bool) -> list[str]:
    errs: list[str] = []
    blocks = extract_code_fences(sec)
    bash_blocks = [b for (lang, b) in blocks if lang in ("bash", "sh", "shell")]
    json_blocks = [b for (lang, b) in blocks if lang == "json"]

    if not bash_blocks:
        errs.append("缺少 bash/sh/shell 代码块（示例命令）")
    else:
        if sec.kind == "http":
            if not any("curl" in b for b in bash_blocks):
                errs.append("bash 代码块中必须包含 curl 示例")
        else:
            if not any(("ws://" in b) or ("wss://" in b) for b in bash_blocks):
                errs.append("bash 代码块中必须包含 ws:// 或 wss:// 连接示例")

    if not json_blocks:
        errs.append("缺少 json 代码块（示例 payload）")
    elif needs_request_body and len(json_blocks) < 2:
        errs.append("该 endpoint 有 request body：至少需要 2 个 json 代码块（request + response）")

    return errs


def main() -> int:
    parser = argparse.ArgumentParser(description="trade_canvas API docs audit (v1 endpoints + examples)")
    parser.add_argument("--list", action="store_true", help="List expected endpoints and exit 0")
    args = parser.parse_args()

    repo_root = _repo_root()

    schema = load_openapi(repo_root)
    expected_http, http_needs_body = extract_openapi_endpoints(schema)
    expected_ws = extract_ws_routes(repo_root)

    sections = parse_sections(repo_root)

    docs_http: dict[tuple[str, str], Section] = {}
    docs_ws: dict[str, Section] = {}
    duplicate: list[str] = []
    for sec in sections:
        if sec.kind == "http":
            key = (sec.method, sec.path)
            if key in docs_http:
                duplicate.append(f"重复定义：{sec.method} {sec.path}（{sec.file}:{sec.start_line}）")
            docs_http[key] = sec
        else:
            key2 = sec.path
            if key2 in docs_ws:
                duplicate.append(f"重复定义：WS {sec.path}（{sec.file}:{sec.start_line}）")
            docs_ws[key2] = sec

    if args.list:
        print("# HTTP (/api/**)")
        for m, p in sorted(expected_http):
            suffix = " (requestBody)" if (m, p) in http_needs_body else ""
            print(f"- {m} {p}{suffix}")
        print("\n# WS (/ws/**)")
        for p in sorted(expected_ws):
            print(f"- WS {p}")
        return 0

    errors: list[str] = []
    errors.extend(duplicate)

    missing_http = sorted(expected_http - set(docs_http.keys()))
    extra_http = sorted(set(docs_http.keys()) - expected_http)
    missing_ws = sorted(expected_ws - set(docs_ws.keys()))
    extra_ws = sorted(set(docs_ws.keys()) - expected_ws)

    if missing_http:
        errors.append("缺少 HTTP endpoint 文档：")
        errors.extend([f"- {m} {p}" for (m, p) in missing_http])
    if extra_http:
        errors.append("文档中存在 OpenAPI 未定义的 HTTP endpoint（疑似漂移/拼写错误）：")
        errors.extend([f"- {m} {p}（{docs_http[(m, p)].file}:{docs_http[(m, p)].start_line}）" for (m, p) in extra_http])

    if missing_ws:
        errors.append("缺少 WS endpoint 文档：")
        errors.extend([f"- WS {p}" for p in missing_ws])
    if extra_ws:
        errors.append("文档中存在代码未定义的 WS endpoint（疑似漂移/拼写错误）：")
        errors.extend([f"- WS {p}（{docs_ws[p].file}:{docs_ws[p].start_line}）" for p in extra_ws])

    for key, sec in sorted(docs_http.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        needs_body = key in http_needs_body
        perr = []
        if not section_has_semantics(sec):
            perr.append("缺少 `### 语义`/`### 说明` 小节，或小节内没有说明文本")
        perr.extend(section_examples_ok(sec, needs_request_body=needs_body))
        if perr:
            errors.append(f"{sec.file}:{sec.start_line} {sec.method} {sec.path}")
            errors.extend([f"- {e}" for e in perr])

    for path, sec in sorted(docs_ws.items(), key=lambda kv: kv[0]):
        perr = []
        if not section_has_semantics(sec):
            perr.append("缺少 `### 语义`/`### 说明` 小节，或小节内没有说明文本")
        perr.extend(section_examples_ok(sec, needs_request_body=False))
        if perr:
            errors.append(f"{sec.file}:{sec.start_line} WS {path}")
            errors.extend([f"- {e}" for e in perr])

    if errors:
        print("[api_docs_audit] FAIL")
        for e in errors:
            print(e)
        return 1

    print("[api_docs_audit] OK")
    print(f"- HTTP endpoints documented: {len(docs_http)}/{len(expected_http)}")
    print(f"- WS endpoints documented: {len(docs_ws)}/{len(expected_ws)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

