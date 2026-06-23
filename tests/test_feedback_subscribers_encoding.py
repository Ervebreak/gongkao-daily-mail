from __future__ import annotations

from pathlib import Path

import feedback


def test_write_subscribers_text_local_uses_utf8_bom(tmp_path: Path) -> None:
    target = tmp_path / "subscribers.csv"
    meta = feedback._write_subscribers_text("email,nickname\nuser@example.com,中文昵称\n", str(target))

    assert meta["storage"] == "local"
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "中文昵称" in target.read_text(encoding="utf-8-sig")
