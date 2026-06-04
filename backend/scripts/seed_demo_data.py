#!/usr/bin/env python3
"""Create safe local demo data under backend/data.

The repository intentionally ignores backend/data because production uploads,
catalog databases, and workspaces can contain sensitive vehicle data. This
script recreates the small synthetic demo set referenced by the docs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = BACKEND_ROOT / "data"


TICKETS = [
    {
        "key": "FOTA-8765",
        "summary": "iCGM 升级过程中挂死，根因为 eMMC 写入超时",
        "description": "合成样例：高温环境下 iCGM 写入升级包超时，状态机反复重试。",
        "resolution": "增加写入超时阈值与温度保护，超阈值暂停升级。",
    },
    {
        "key": "FOTA-9123",
        "summary": "MPU 升级包校验失败导致循环重启",
        "description": "合成样例：下载完成后 verifyPackage 失败，缺少重试上限。",
        "resolution": "增加校验失败重试上限，超限后自动回退。",
    },
    {
        "key": "FOTA-7501",
        "summary": "ECU 刷写顺序依赖导致 IPK 刷写超时",
        "description": "合成样例：IPK 等待 iCGM FLASH_START 信号但协调者异常。",
        "resolution": "为 IPK 增加独立超时和回退机制。",
    },
]


DOCUMENTS = [
    {
        "title": "FOTA状态机流程及异常场景处理技术要点2023Q3.pdf",
        "excerpt": "状态转换：INIT → VERSION_CHECK → DOWNLOAD → VERIFY → INSTALL → REBOOT → COMPLETE。",
    },
    {
        "title": "ECU 刷写顺序与依赖关系规范 v2.0",
        "excerpt": "iCGM 作为升级协调者优先刷写，MCU/IPK 依赖 FLASH_START 协调信号。",
    },
]


DOC_INDEX = [
    {
        "title": "FOTA 升级包校验规范",
        "content": "升级包校验流程包括大小检查、SHA-256 哈希计算、签名比对和安装分区写入。",
        "excerpt": "校验失败最多重试 3 次，超限后标记 FAILED 并上报。",
    },
    {
        "title": "集中式升级刷写流程异常链路复盘",
        "content": "协调者异常可能导致下游 ECU 长时间等待。各 ECU 应具备独立超时和回退策略。",
        "excerpt": "iCGM 异常时 IPK/MCU 应独立退出等待状态。",
    },
]


LOGS = {
    "fota_upgrade_failure_20250911.log": [
        "2025-09-11T02:13:01Z iCGM FOTA INIT package=demo_v2.4.1",
        "2025-09-11T02:14:12Z iCGM VERIFY failed reason=SHA256_MISMATCH retry=1",
        "2025-09-11T02:17:43Z IPK WAIT_FLASH_START timeout_after=300s",
        "2025-09-11T02:18:10Z FOTA RESULT failed stage=VERIFY controller=iCGM",
    ],
    "icgm_emmc_timeout_20250915.log": [
        "2025-09-15T03:02:11Z iCGM INSTALL write_partition start",
        "2025-09-15T03:03:11Z iCGM ERROR eMMC_WRITE_TIMEOUT block=2048",
        "2025-09-15T03:03:42Z iCGM RETRY install retry=2",
    ],
    "network_interrupt_download_20251003.log": [
        "2025-10-03T09:21:00Z TBOX DOWNLOAD start",
        "2025-10-03T09:25:18Z TBOX WARN network_disconnect duration=42s",
        "2025-10-03T09:27:05Z FOTA DOWNLOAD failed reason=checksum_error",
    ],
    "ecu_dependency_chain_failure_20251120.log": [
        "2025-11-20T11:00:00Z iCGM INSTALL failed reason=coordinator_crash",
        "2025-11-20T11:05:01Z IPK WAIT_FLASH_START timeout_after=300s",
        "2025-11-20T11:05:05Z MCU WAIT_COORDINATOR timeout_after=300s",
    ],
    "battery_drain_abort_20251208.log": [
        "2025-12-08T18:30:00Z BMS battery_soc=18",
        "2025-12-08T18:30:10Z FOTA ABORT reason=LOW_BATTERY threshold=20",
        "2025-12-08T18:30:12Z FOTA RESULT failed stage=PRECHECK",
    ],
}


def write_json(path: Path, payload: object, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def write_text(path: Path, lines: list[str], overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed synthetic Velab demo data")
    parser.add_argument("--overwrite", action="store_true", help="replace existing demo files")
    args = parser.parse_args()

    created = 0
    created += write_json(DATA_ROOT / "jira_mock" / "tickets.json", TICKETS, args.overwrite)
    created += write_json(DATA_ROOT / "jira_mock" / "documents.json", DOCUMENTS, args.overwrite)
    created += write_json(DATA_ROOT / "docs" / "index.json", DOC_INDEX, args.overwrite)
    for name, lines in LOGS.items():
        created += write_text(DATA_ROOT / "logs" / name, lines, args.overwrite)

    print(f"Seed complete: {created} file(s) written under {DATA_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
