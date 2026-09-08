"""Convert a benchmark JSON file into a concise Markdown report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", type=Path)
    args = parser.parse_args()
    data = json.loads(args.json_file.read_text(encoding="utf-8"))
    http = data.get("http_read_benchmark", {})
    lines = [
        "# procurepilot 自动化验收报告",
        "",
        f"生成时间：{data.get('generated_at', '-')}",
        "",
        "## 服务健康",
        "",
        "| 服务 | 状态 | 耗时（秒） |",
        "|---|---:|---:|",
    ]
    for name, item in data.get("services", {}).items():
        lines.append(f"| {name} | {item.get('status', '-')} | {item.get('seconds', '-')} |")
    lines += [
        "",
        "## 只读并发基准",
        "",
        f"- 接口：`{http.get('endpoint', '-')}`",
        f"- 样本：{http.get('samples', 0)}，成功：{http.get('successes', 0)}，失败：{http.get('failures', 0)}",
        f"- 平均耗时：{http.get('avg_seconds', '-')} 秒",
        f"- P50：{http.get('p50_seconds', '-')} 秒",
        f"- P95：{http.get('p95_seconds', '-')} 秒",
        f"- 最大耗时：{http.get('max_seconds', '-')} 秒",
        "",
    ]
    sse = data.get("sse_benchmark")
    if sse:
        lines += [
            "## SSE 流式对话基准",
            "",
            f"- 样本：{sse.get('samples', 0)}，成功：{sse.get('successes', 0)}，失败：{sse.get('failures', 0)}",
            f"- 平均完整响应耗时：{sse.get('avg_total_seconds', '-')} 秒",
            f"- P50：{sse.get('p50_total_seconds', '-')} 秒",
            f"- P95：{sse.get('p95_total_seconds', '-')} 秒",
            "",
        ]
    lines += [
        "## 说明",
        "",
    ]
    lines.extend(f"- {note}" for note in data.get("notes", []))
    output = args.json_file.with_suffix(".md")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
