"""拼图最佳用时持久化测试。"""

from __future__ import annotations

from deltaforcebox.core.records import format_time, load_best_times, save_best_time


def test_best_times_roundtrip(tmp_path):
    path = tmp_path / "best_times.json"
    save_best_time("a.png", 65.5, path=path)
    save_best_time("b.png", 12.0, path=path)
    assert load_best_times(path=path) == {"a.png": 65.5, "b.png": 12.0}


def test_only_faster_time_updates(tmp_path):
    path = tmp_path / "best_times.json"
    assert save_best_time("a.png", 100.0, path=path) == 100.0
    assert save_best_time("a.png", 90.0, path=path) == 90.0
    assert save_best_time("a.png", 95.0, path=path) == 90.0  # 更慢不覆盖
    assert load_best_times(path=path) == {"a.png": 90.0}


def test_corrupted_file_falls_back_empty(tmp_path):
    path = tmp_path / "best_times.json"
    path.write_text("not json{{{", encoding="utf-8")
    assert load_best_times(path=path) == {}
    # 损坏后仍可正常写入
    save_best_time("a.png", 5.0, path=path)
    assert load_best_times(path=path) == {"a.png": 5.0}


def test_format_time():
    assert format_time(0.0) == "0:00.0"
    assert format_time(8.4) == "0:08.4"
    assert format_time(92.5) == "1:32.5"
    assert format_time(312.7) == "5:12.7"
