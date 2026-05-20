import datetime as dt
import json
import sys
import uuid
from pathlib import Path
from typing import Any


class RunLogger:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lines: list[str] = []
        self.context: dict[str, Any] = {"run_id": uuid.uuid4().hex[:12]}

    def bind(self, **context: Any) -> None:
        for key, value in context.items():
            if value in (None, "", [], {}):
                continue
            self.context[key] = value

    def info(self, message: str, **payload: Any) -> None:
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        suffix = ""
        merged = dict(self.context)
        merged.update(payload)
        if merged:
            suffix = " " + json.dumps(merged, ensure_ascii=False, default=str)
        self.lines.append(f"[{now}] {message}{suffix}")

    def save(self, filename: str = "run.log") -> Path:
        path = self.output_dir / filename
        path.write_text("\n".join(self.lines), encoding="utf-8")
        return path

    def dump_to_stdout(self) -> None:
        for line in self.lines:
            try:
                print(line)
            except UnicodeEncodeError:
                sys.stdout.buffer.write((line + "\n").encode("utf-8", errors="replace"))
