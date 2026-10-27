"""Database schema and connection helpers.

All business tables carry category_id, created_by and created_at (DEC-014). Version and
ledger tables are append-only and guarded by triggers (AC-F10-01, DEC-007, RULE-07).
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import Connection, Engine

metadata = MetaData()


def _audit() -> list[Column]:
    return [
        Column("created_by", String(64), nullable=False, server_default="wen"),
        Column("created_at", String(32), nullable=False),
    ]


category = Table(
    "category", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(128), nullable=False, unique=True),
    Column("platform", String(32), nullable=False, server_default="amazon"),
    Column("site", String(16), nullable=False),
    Column("node", String(32), nullable=False),
    Column("owner", String(64), nullable=False),
    Column("is_draft", Integer, nullable=False, server_default="0"),
    *_audit(),
)

category_version = Table(
    "category_version", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, ForeignKey("category.id"), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("config_json", Text, nullable=False),
    Column("note", Text),
    *_audit(),
)

category_draft = Table(
    "category_draft", metadata,
    Column("category_id", Integer, primary_key=True),
    Column("config_json", Text, nullable=False),
    Column("base_version_no", Integer),
    Column("updated_at", String(32), nullable=False),
)

app_meta = Table(
    "app_meta", metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text),
)

package = Table(
    "package", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("label", String(16), nullable=False, unique=True),
    Column("kind", String(16)),  # history / cross / None when the manifest is unusable
    Column("manifest_json", Text),
    Column("source_name", Text),
    Column("months_from", String(7)),
    Column("months_to", String(7)),
    Column("conclusion", String(8), nullable=False),  # pass / warn / block
    Column("readonly_path", Text),
    Column("fingerprint", String(64)),  # combined fingerprint over file hashes
    Column("config_version_id", Integer),
    *_audit(),
)

package_file = Table(
    "package_file", metadata,
    Column("id", Integer, primary_key=True),
    Column("package_id", Integer, ForeignKey("package.id"), nullable=False),
    Column("file_code", String(4), nullable=False),
    Column("filename", Text, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("row_count", Integer),
    Column("optional", Integer, nullable=False, server_default="0"),
)

validation_item = Table(
    "validation_item", metadata,
    Column("id", Integer, primary_key=True),
    Column("package_id", Integer, ForeignKey("package.id"), nullable=False),
    Column("file_code", String(4)),
    Column("field", Text),
    Column("check_name", String(32), nullable=False),
    Column("result", String(8), nullable=False),  # pass / warn / block / na
    Column("affected_rows", Integer),
    Column("affected_note", Text),
    Column("sample_rows_json", Text),
    Column("excluded_rows_json", Text),
    Column("message", Text),
)

package_field = Table(
    "package_field", metadata,
    Column("id", Integer, primary_key=True),
    Column("package_id", Integer, ForeignKey("package.id"), nullable=False),
    Column("file_code", String(4), nullable=False),
    Column("field", Text, nullable=False),
    Column("dtype", String(16), nullable=False),
    Column("evidence_json", Text),
)

RAW_COMMON = lambda: [  # noqa: E731
    Column("package_id", Integer, nullable=False),
    Column("row_no", Integer, nullable=False),
    Column("extra_json", Text),
]

raw_c1 = Table(
    "raw_c1", metadata,
    *RAW_COMMON(),
    Column("file_code", String(4), nullable=False),
    Column("month", String(7)),
    Column("child", String(16)),
    Column("parent", String(16)),
    Column("brand", Text),
    Column("seller", Text),
    Column("title", Text),
    Column("launch_date", String(10)),
    Column("child_units", Float),
    Column("child_sales", Float),
    Column("parent_units", Float),
    Column("bsr", Float),
    Column("node", String(32)),
    Column("fulfillment", String(16)),
    Column("variant_count", Float),
    Column("first_review", String(10)),
    Column("spu_no", Text),
    Column("bought_label", Text),
    Column("price", Float),
    Column("rating", Float),
    Column("bullets", Text),
)
Index("ix_raw_c1_pkg_month", raw_c1.c.package_id, raw_c1.c.month)

raw_c2 = Table(
    "raw_c2", metadata,
    *RAW_COMMON(),
    Column("file_code", String(4), nullable=False),
    Column("child", String(16)),
    Column("parent", String(16)),
    Column("brand", Text),
    Column("title", Text),
    Column("launch_date", String(10)),
    Column("fulfillment", String(16)),
    Column("variant_count", Float),
    Column("first_review", String(10)),
    Column("spu_no", Text),
    Column("bullets", Text),
)
Index("ix_raw_c2_pkg", raw_c2.c.package_id)

raw_c3 = Table(
    "raw_c3", metadata,
    *RAW_COMMON(),
    Column("file_code", String(4), nullable=False),
    Column("month", String(7)),
    Column("child", String(16)),
    Column("child_units", Float),
    Column("child_sales", Float),
    Column("bsr", Float),
    Column("parent_units", Float),
)
Index("ix_raw_c3_pkg", raw_c3.c.package_id)

raw_c4 = Table(
    "raw_c4", metadata,
    *RAW_COMMON(),
    Column("child", String(16)),
    Column("dim", String(16)),
    Column("value", Text),
    Column("status", String(16)),
)
Index("ix_raw_c4_pkg", raw_c4.c.package_id)

raw_c5 = Table(
    "raw_c5", metadata,
    *RAW_COMMON(),
    Column("keyword", Text),
    Column("month", String(7)),
    Column("volume", Float),
    Column("tags", Text),
    Column("purchases", Float),
)
Index("ix_raw_c5_pkg", raw_c5.c.package_id)

raw_c6 = Table(
    "raw_c6", metadata,
    *RAW_COMMON(),
    Column("review_id", Text),
    Column("asin", String(16)),
    Column("level", String(8)),
    Column("review_date", String(10)),
    Column("stars", Float),
    Column("pain_code", Text),
    Column("structural", Integer),
    Column("label_version", Text),
)
Index("ix_raw_c6_pkg", raw_c6.c.package_id)

raw_c7 = Table(
    "raw_c7", metadata,
    *RAW_COMMON(),
    Column("name", Text),
    Column("project_date", String(10)),
    Column("segment_or_attr", Text),
    Column("launch_date", String(10)),
    Column("asin", Text),
)

contract_version = Table(
    "contract_version", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("package_id", Integer),
    Column("note", Text),
    *_audit(),
)

contract_item = Table(
    "contract_item", metadata,
    Column("id", Integer, primary_key=True),
    Column("version_id", Integer, ForeignKey("contract_version.id"), nullable=False),
    Column("file_code", String(4), nullable=False),
    Column("field", Text, nullable=False),
    Column("meaning", Text),
    Column("grain", String(16)),
    Column("timing", String(16)),
    Column("snapshot_date", String(10)),
    Column("nature", String(16)),
    Column("usage", String(16)),
    Column("rule_text", Text),
    Column("dtype", String(16)),
    Column("status", String(16), nullable=False),  # confirmed / pending
    Column("source", String(16)),  # 逐项 / 批量
    Column("confirmed_in", Integer),
    *_audit(),
)

contract_draft_item = Table(
    "contract_draft_item", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("file_code", String(4), nullable=False),
    Column("field", Text, nullable=False),
    Column("meaning", Text),
    Column("grain", String(16)),
    Column("timing", String(16)),
    Column("snapshot_date", String(10)),
    Column("nature", String(16)),
    Column("usage", String(16)),
    Column("rule_text", Text),
    Column("dtype", String(16)),
    Column("status", String(16), nullable=False),
    Column("source", String(16)),
    Column("confirmed_in", Integer),
    Column("change_kind", String(16)),  # 新增 / 类型改变 / 缺少 / None
    Column("package_id", Integer),
    Column("updated_at", String(32)),
)

change_log = Table(
    "change_log", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("object", String(32), nullable=False),
    Column("object_id", Text),
    Column("action", String(64), nullable=False),
    Column("item", Text),
    Column("before", Text),
    Column("after", Text),
    *_audit(),
)

health_result = Table(
    "health_result", metadata,
    Column("id", Integer, primary_key=True),
    Column("package_id", Integer, nullable=False),
    Column("config_version_id", Integer),
    Column("item", String(32), nullable=False),
    Column("value", Float),
    Column("numerator", Float),
    Column("denominator", Float),
    Column("detail_json", Text),
    Column("samples_json", Text),
    Column("created_at", String(32), nullable=False),
)

health_ack = Table(
    "health_ack", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("package_id", Integer, nullable=False),
    Column("item", String(32), nullable=False),
    Column("note", Text, nullable=False),
    *_audit(),
)

fingerprint_check = Table(
    "fingerprint_check", metadata,
    Column("id", Integer, primary_key=True),
    Column("package_id", Integer, nullable=False),
    Column("file_code", String(4), nullable=False),
    Column("sha_import", String(64)),
    Column("sha_now", String(64)),
    Column("ok", Integer),
    Column("created_at", String(32), nullable=False),
)

merge_suggestion = Table(
    "merge_suggestion", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("code", String(16), nullable=False),
    Column("brand", Text),
    Column("parents_json", Text, nullable=False),
    Column("child_count", Integer),
    Column("basis", String(32), nullable=False),
    Column("detail_json", Text),
    Column("status", String(16), nullable=False),  # pending / confirmed / rejected
    Column("source", String(16)),
    Column("decided_by", String(64)),
    Column("decided_at", String(32)),
    Column("package_id", Integer),
    *_audit(),
)

merge = Table(
    "merge", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("code", String(16), nullable=False),
    Column("suggestion_id", Integer),
    Column("parents_json", Text, nullable=False),
    Column("status", String(16), nullable=False),  # active / split / revised
    Column("source", String(16)),
    Column("note", Text),
    Column("ended_by", String(64)),
    Column("ended_at", String(32)),
    Column("superseded_by", Integer),
    *_audit(),
)

compute_run = Table(
    "compute_run", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("mode", String(8), nullable=False),  # history / cross
    Column("package_id", Integer, nullable=False),
    Column("contract_version_id", Integer),
    Column("config_version_id", Integer),
    Column("merge_hash", String(64)),
    Column("adjust_hash", String(64)),
    Column("excluded_fields_json", Text),
    Column("excluded_rows", Integer),
    Column("rows_used_json", Text),
    Column("latest_month", String(7)),
    Column("t_month", String(7)),
    Column("status", String(16), nullable=False),
    Column("error", Text),
    Column("started_at", String(32)),
    Column("ended_at", String(32)),
    *_audit(),
)

spu = Table(
    "spu", metadata,
    Column("run_id", Integer, nullable=False),
    Column("spu_key", String(64), nullable=False),
    Column("display_id", String(32)),
    Column("brand", Text),
    Column("title", Text),
    Column("source", String(16)),
    Column("merge_code", String(16)),
    Column("parents_json", Text),
    Column("launch_date", String(10)),
    Column("launch_child", String(16)),
    Column("same_day_count", Integer),
    Column("batch", String(7)),
    Column("is_new", Integer),
    Column("relaunch", Integer),
    Column("first_review_min", String(10)),
    Column("new_variant_count", Integer),
    Column("child_count", Integer),
    Column("rising", Integer),
    Column("segment_key", Text),
    Column("segment_name", Text),
    Column("launch_price", Float),
    Column("fulfillment", String(16)),
    Column("variant_count", Float),
    Column("brand_prior_hit", Integer),
    Column("is_old", Integer),
    Column("source_keys_json", Text),
)
Index("ix_spu_run", spu.c.run_id, spu.c.spu_key)

spu_child = Table(
    "spu_child", metadata,
    Column("run_id", Integer, nullable=False),
    Column("spu_key", String(64), nullable=False),
    Column("child", String(16), nullable=False),
    Column("parent", String(16)),
    Column("launch_date", String(10)),
    Column("first_review", String(10)),
    Column("new_variant", Integer),
    Column("color", Text),
    Column("size", Text),
    Column("attrs_json", Text),
)
Index("ix_spu_child_run", spu_child.c.run_id, spu_child.c.spu_key)

judgment = Table(
    "judgment", metadata,
    Column("run_id", Integer, nullable=False),
    Column("spu_key", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("basis", String(16)),
    Column("hit_month", String(7)),
    Column("hit_age", Integer),
    Column("hit_child", String(16)),
    Column("hit_bsr", Float),
    Column("hit_amount", Float),
    Column("missing_months_json", Text),
    Column("unobserved_ages_json", Text),
    Column("best_bsr", Float),
    Column("max_sales", Float),
    Column("remaining", Integer),
    Column("months_json", Text),
    Column("rising", Integer),
)
Index("ix_judgment_run", judgment.c.run_id, judgment.c.spu_key)

segment_info = Table(
    "segment_info", metadata,
    Column("run_id", Integer, nullable=False),
    Column("t_month", String(7), nullable=False),
    Column("segment_key", Text, nullable=False),
    Column("name", Text),
    Column("dims_json", Text),
    Column("child_count", Integer),
    Column("backfill_share", Float),
    Column("backfill_json", Text),
    Column("sample", Integer),
    Column("has_unknown", Integer),
)
Index("ix_segment_info_run", segment_info.c.run_id, segment_info.c.t_month)

signal_value = Table(
    "signal_value", metadata,
    Column("run_id", Integer, nullable=False),
    Column("t_month", String(7), nullable=False),
    Column("segment_key", Text, nullable=False),
    Column("signal", String(32), nullable=False),
    Column("value", Float),
    Column("num", Float),
    Column("den", Float),
    Column("cnt", Integer),
    Column("flag", String(32)),
    Column("extra_json", Text),
)
Index("ix_signal_run_t", signal_value.c.run_id, signal_value.c.t_month)

backtest_run = Table(
    "backtest_run", metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(16), nullable=False),
    Column("category_id", Integer, nullable=False),
    Column("mode", String(8), nullable=False),
    Column("compute_run_id", Integer),
    Column("package_id", Integer),
    Column("contract_version_id", Integer),
    Column("config_version_id", Integer),
    Column("merge_hash", String(64)),
    Column("seed", Integer),
    Column("status", String(16), nullable=False),
    Column("conclusion", String(32)),
    Column("reason_class", String(32)),
    Column("result_json", Text),
    Column("card_id", Integer),
    Column("error", Text),
    Column("started_at", String(32)),
    Column("ended_at", String(32)),
    *_audit(),
)

decision_card = Table(
    "decision_card", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("mode", String(8), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("label", String(16), nullable=False),
    Column("status", String(16), nullable=False),
    Column("backtest_id", Integer),
    Column("signals_json", Text),
    Column("basis_json", Text),
    *_audit(),
)

rule = Table(
    "rule", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("code", String(16), nullable=False),
    Column("origin", String(8), nullable=False),  # 人工 / 回测
    Column("cross_tag", Integer, nullable=False, server_default="0"),
    *_audit(),
)

rule_version = Table(
    "rule_version", metadata,
    Column("id", Integer, primary_key=True),
    Column("rule_id", Integer, ForeignKey("rule.id"), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("condition_json", Text, nullable=False),
    Column("action", String(16), nullable=False),
    Column("reason", Text),
    Column("status", String(16), nullable=False),
    Column("basis_json", Text),
    Column("change_note", Text),
    *_audit(),
)

snapshot = Table(
    "snapshot", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("month", String(7), nullable=False),
    Column("seq", Integer, nullable=False),
    Column("mode", String(8), nullable=False),
    Column("card_id", Integer),
    Column("card_label", String(16)),
    Column("card_status", String(16)),
    Column("backtest_id", Integer),
    Column("compute_run_id", Integer),
    Column("content_json", Text, nullable=False),
    Column("sha256", String(64), nullable=False),
    *_audit(),
)

snapshot_export = Table(
    "snapshot_export", metadata,
    Column("id", Integer, primary_key=True),
    Column("snapshot_id", Integer, nullable=False),
    Column("export_id", Integer, nullable=False),
    Column("created_at", String(32), nullable=False),
)

decision_record = Table(
    "decision_record", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("code", String(16), nullable=False),
    Column("kind", String(8), nullable=False),  # 记录 / 补录 / 更正
    Column("decision", String(8)),  # 立项 / 不立项
    Column("segment_key", Text),
    Column("segment_name", Text),
    Column("reason", Text),
    Column("snapshot_id", Integer),
    Column("project_name", Text),
    Column("project_date", String(10)),
    Column("basis_note", Text),
    Column("corrects_id", Integer),
    Column("source", String(16)),  # 手工 / 数据包
    *_audit(),
)

launch_data = Table(
    "launch_data", metadata,
    Column("id", Integer, primary_key=True),
    Column("decision_id", Integer, nullable=False),
    Column("launch_month", String(7), nullable=False),
    Column("asin", Text),
    Column("months_json", Text, nullable=False),
    Column("config_version_id", Integer),
    *_audit(),
)

reconciliation = Table(
    "reconciliation", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("snapshot_id", Integer, nullable=False),
    Column("recon_month", String(7), nullable=False),
    Column("batch", String(7), nullable=False),
    Column("mode", String(8), nullable=False),
    Column("detail_json", Text),
    Column("top_hits", Integer),
    Column("top_n", Integer),
    Column("all_hits", Integer),
    Column("all_n", Integer),
    Column("incomplete", Integer),
    Column("multiple", Float),
    Column("exp_lo", Float),
    Column("exp_hi", Float),
    Column("within", String(8)),
    *_audit(),
)

rule_reconciliation = Table(
    "rule_reconciliation", metadata,
    Column("id", Integer, primary_key=True),
    Column("reconciliation_id", Integer, nullable=False),
    Column("rule_id", Integer, nullable=False),
    Column("rule_version_no", Integer, nullable=False),
    Column("snapshot_id", Integer, nullable=False),
    Column("recon_month", String(7), nullable=False),
    Column("action", String(16), nullable=False),
    Column("segments_json", Text),
    Column("hits", Integer),
    Column("n", Integer),
    Column("batch_avg", Float),
    Column("multiple", Float),
    Column("condition_text", Text),
    Column("result", String(32), nullable=False),
    Column("new_version_no", Integer),
    *_audit(),
)

export_record = Table(
    "export_record", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("month", String(7), nullable=False),
    Column("snapshot_id", Integer, nullable=False),
    Column("xlsx_path", Text),
    Column("html_path", Text),
    Column("xlsx_size", Integer),
    Column("html_size", Integer),
    Column("backup_id", Integer),
    *_audit(),
)

backup_setting = Table(
    "backup_setting", metadata,
    Column("id", Integer, primary_key=True),
    Column("directory", Text),
    Column("writable", Integer),
    Column("checked_at", String(32)),
    Column("updated_by", String(64)),
    Column("updated_at", String(32)),
)

backup_record = Table(
    "backup_record", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer),
    Column("path", Text),
    Column("size", Integer),
    Column("trigger", String(16), nullable=False),
    Column("scope_json", Text),
    Column("package_fps_json", Text),
    Column("status", String(16), nullable=False),
    Column("error", Text),
    *_audit(),
)

restore_record = Table(
    "restore_record", metadata,
    Column("id", Integer, primary_key=True),
    Column("backup_path", Text, nullable=False),
    Column("backup_time", String(32)),
    Column("pre_backup_id", Integer),
    *_audit(),
)

job = Table(
    "job", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer),
    Column("kind", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("step", Text),
    Column("progress", Float),
    Column("error", Text),
    Column("result_json", Text),
    Column("started_at", String(32)),
    Column("ended_at", String(32)),
    *_audit(),
)

# Reviewed adjustments on top of an imported package (the package rows themselves never change). A proposal
# (from Codex through /api/v1, or typed in by hand) waits as 待审核 until a person confirms, edits or rejects it;
# only 已确认 rows are applied when the package is read for checks and computing.
data_adjustment = Table(
    "data_adjustment", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("package_id", Integer, nullable=False),
    Column("code", String(16), nullable=False, unique=True),
    Column("batch", String(16)),
    Column("file_code", String(4), nullable=False),
    Column("child", String(16), nullable=False),
    Column("month", String(7)),  # None on monthly files = every month of the child
    Column("field", String(32), nullable=False),
    Column("old_value", Text),
    Column("proposed_value", Text),
    Column("final_value", Text),
    Column("reason", Text),
    Column("source", String(32), nullable=False),
    Column("status", String(8), nullable=False),  # 待审核 / 已确认 / 已驳回 / 已撤回 / 已撤销
    Column("decided_by", String(64)),
    Column("decided_at", String(32)),
    Column("decision_note", Text),
    *_audit(),
)
Index("ix_data_adjustment_pkg", data_adjustment.c.package_id, data_adjustment.c.status)

# 变量关系 model results (PAGE-F16-01): one row per run, bound to the compute run it read.
model_run = Table(
    "model_run", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("mode", String(8), nullable=False),
    Column("compute_run_id", Integer, nullable=False),
    Column("package_id", Integer, nullable=False),
    Column("config_version_id", Integer),
    Column("adjust_hash", String(64)),
    Column("status", String(16), nullable=False),
    Column("verdict", String(32)),
    Column("result_json", Text),
    Column("started_at", String(32)),
    Column("ended_at", String(32)),
    *_audit(),
)
Index("ix_model_run_cat", model_run.c.category_id, model_run.c.mode)

run_step = Table(
    "run_step", metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("step", String(32), nullable=False),
    Column("month", String(7)),
    Column("started_at", String(32), nullable=False),
    Column("ended_at", String(32)),
    Column("result", Text),
    Column("link", Text),
    *_audit(),
)

# Tables whose rows may never be updated or deleted (RULE-07, DEC-014 只追加).
APPEND_ONLY = (
    "snapshot",
    "decision_record",
    "rule_version",
    "rule_reconciliation",
    "contract_version",
    "contract_item",
    "category_version",
    "decision_card",
    "reconciliation",
    "launch_data",
    "change_log",
)

# Content restored from a backup (REQ-F10-04): ledger, strategy library, field contract,
# category config, confirmation records, plus the cards/backtests the ledger refers to.
BACKUP_TABLES = (
    "category", "category_version", "category_draft",
    "contract_version", "contract_item", "contract_draft_item",
    "merge_suggestion", "merge", "health_ack", "change_log",
    "decision_card", "backtest_run", "rule", "rule_version",
    "snapshot", "snapshot_export", "decision_record", "launch_data",
    "reconciliation", "rule_reconciliation", "export_record", "run_step", "data_adjustment", "model_run",
)


def trigger_sql() -> list[str]:
    stmts = []
    for name in APPEND_ONLY:
        stmts.append(
            f"CREATE TRIGGER IF NOT EXISTS trg_{name}_no_update BEFORE UPDATE ON {name} "
            f"BEGIN SELECT RAISE(ABORT, '{name} 只追加，不允许修改'); END"
        )
        stmts.append(
            f"CREATE TRIGGER IF NOT EXISTS trg_{name}_no_delete BEFORE DELETE ON {name} "
            f"BEGIN SELECT RAISE(ABORT, '{name} 只追加，不允许删除'); END"
        )
    return stmts


def drop_trigger_sql() -> list[str]:
    out = []
    for name in APPEND_ONLY:
        out.append(f"DROP TRIGGER IF EXISTS trg_{name}_no_update")
        out.append(f"DROP TRIGGER IF EXISTS trg_{name}_no_delete")
    return out


_engines: dict[str, Engine] = {}


def _on_connect(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def get_engine(db_path: Path) -> Engine:
    key = str(db_path.resolve())
    eng = _engines.get(key)
    if eng is None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(f"sqlite:///{db_path}", future=True)
        event.listen(eng, "connect", _on_connect)
        _engines[key] = eng
    return eng


def dispose_all() -> None:
    for eng in _engines.values():
        eng.dispose()
    _engines.clear()


def init_db(engine: Engine) -> None:
    """Bring the database to the latest schema through the Alembic migration chain."""
    from oppo import migrations

    migrations.upgrade(engine)


@contextmanager
def tx(engine: Engine) -> Iterator[Connection]:
    with engine.begin() as conn:
        yield conn


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if not isinstance(value, (str, bytes)) or value == "":
        return default  # None, or NaN from pandas for SQL NULL
    return json.loads(value)


def get_meta(conn: Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute(text("SELECT value FROM app_meta WHERE key=:k"), {"k": key}).first()
    return row[0] if row else default


def set_meta(conn: Connection, key: str, value: str) -> None:
    conn.execute(
        text("INSERT INTO app_meta(key, value) VALUES(:k, :v) ON CONFLICT(key) DO UPDATE SET value=excluded.value"),
        {"k": key, "v": value},
    )
