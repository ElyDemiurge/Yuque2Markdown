#!/usr/bin/env python3
"""重新转换所有 lake 文件为 Markdown，覆盖原有 md 文件。"""

import sys
import json
import logging
import re
from pathlib import Path
from core_modules.lake.converter import render_doc_markdown

# 设置日志
log_dir = Path("output/公开知识库")
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "regenerate.log"

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] [%(message)s]",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def regenerate_all():
    """重新转换所有 lake 文件。"""
    doc_dirs = list(Path("output/公开知识库").glob("**/*.lake"))
    if not doc_dirs:
        logger.warning("未找到 lake 文件")
        return

    logger.info(f"找到 {len(doc_dirs)} 个 lake 文件，开始重新转换...")

    total = len(doc_dirs)
    converted = 0
    total_warnings = 0

    for i, lake_file in enumerate(doc_dirs, 1):
        try:
            doc_dir = lake_file.parent
            stem = lake_file.stem
            yuque_json = doc_dir / f"{stem}.yuque.json"

            if not yuque_json.exists():
                logger.warning(f"[{i}/{total}] 跳过（无 yuque.json）: {stem}")
                continue

            # 读取原始数据（API 返回格式：{"data": {...}}）
            with open(yuque_json, "r", encoding="utf-8") as f:
                raw = json.load(f)
            doc_data = raw.get("data", raw)

            # 重新转换
            result = render_doc_markdown(doc_data)
            final_md = result.markdown

            # 写入 md 文件（覆盖）
            md_file = doc_dir / f"{stem}.md"
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(final_md)

            converted += 1
            total_warnings += len(result.warnings)

            if result.warnings:
                logger.warning(f"[{i}/{total}] {doc_data.get('title', stem)} | 警告数: {len(result.warnings)}")
                for w in result.warnings[:3]:
                    logger.warning(f"  - {w}")
                if len(result.warnings) > 3:
                    logger.warning(f"  ... 还有 {len(result.warnings) - 3} 条警告")
            else:
                logger.info(f"[{i}/{total}] {doc_data.get('title', stem)} | 转换成功")

        except Exception as e:
            logger.error(f"[{i}/{total}] 转换失败: {lake_file.stem} | {e}")

    logger.info(f"转换完成 | 成功: {converted} | 失败: {total - converted} | 总警告: {total_warnings}")


if __name__ == "__main__":
    regenerate_all()