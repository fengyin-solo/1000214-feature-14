"""安防巡视业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "security"
FILE_MODULE = "security_file"
REQUIRED_FIELDS = ["巡视编号", "巡视区域", "巡视人员"]
OPTIONAL_FIELDS = ["巡视班次", "巡视时间", "异常描述", "处理情况", "交接事项"]
STATUS_ORDER = ["已排班", "巡视中", "正常完成", "发现异常"]
ACTION_RULES = {"开始巡视": "巡视中", "记录异常": "发现异常", "完成巡视": "正常完成"}
NEGATIVE_ACTIONS = []

# 班次核对流程：待取样 -> 未核对 -> 已核对 / 待修正 -> 已交接
REVIEW_PENDING = "待取样"
REVIEW_STAGED = "未核对"
REVIEW_VERIFIED = "已核对"
REVIEW_FIX = "待修正"
REVIEW_HANDED_OVER = "已交接"
CORRECTABLE_FIELDS = ["巡视编号", "巡视区域", "巡视人员", "巡视班次"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _shift_rows(shift: str) -> list[dict[str, Any]]:
    return [row for row in store.rows(MODULE) if str(row.get("巡视班次") or "").strip() == shift]


class SecurityService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        shift: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("巡视编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if shift:
            rows = [row for row in rows if str(row.get("巡视班次") or "").strip() == shift]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            if str(values.get(field) or "").strip():
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["核对状态"] = REVIEW_PENDING
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"安防记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于安防巡视可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"安防记录已{action}"

    def collect_shift(self, shift: str) -> tuple[list[dict[str, Any]], str]:
        """把本班记录放进取样核对区；已在核对流程中的记录保持原状态。"""
        rows = _shift_rows(shift)
        if not rows:
            return [], f"班次「{shift}」下没有安防记录，无法取样"
        for row in rows:
            if str(row.get("核对状态") or REVIEW_PENDING) == REVIEW_PENDING:
                row["核对状态"] = REVIEW_STAGED
        staged = [row for row in rows if row.get("核对状态") == REVIEW_STAGED]
        return staged, f"班次「{shift}」共 {len(rows)} 条记录，{len(staged)} 条在取样核对区"

    def review_shift(self, shift: str) -> tuple[dict[str, Any] | None, str]:
        """按巡视区域、巡视人员逐项检查核对区记录；重复巡视编号留在待修正清单。"""
        rows = _shift_rows(shift)
        staged = [row for row in rows if row.get("核对状态") == REVIEW_STAGED]
        if not staged:
            return None, f"班次「{shift}」核对区没有未核对记录，请先取样入区"
        counts = Counter(
            str(row.get("巡视编号") or "").strip()
            for row in rows
            if row.get("核对状态") != REVIEW_FIX
        )
        verified: list[dict[str, Any]] = []
        fixing: list[dict[str, Any]] = []
        for row in staged:
            number = str(row.get("巡视编号") or "").strip()
            missing = [field for field in ("巡视区域", "巡视人员") if not str(row.get(field) or "").strip()]
            if missing:
                row["核对状态"] = REVIEW_FIX
                row["修正原因"] = f"缺少{'、'.join(missing)}"
                fixing.append(row)
            elif counts[number] > 1:
                row["核对状态"] = REVIEW_FIX
                row["修正原因"] = f"巡视编号 {number} 重复"
                fixing.append(row)
            else:
                row["核对状态"] = REVIEW_VERIFIED
                row.pop("修正原因", None)
                verified.append(row)
        summary = {
            "巡视班次": shift,
            "已核对": len(verified),
            "待修正": len(fixing),
            "修正原因": [
                {"id": row["id"], "巡视编号": row.get("巡视编号"), "修正原因": row.get("修正原因")}
                for row in fixing
            ],
        }
        return summary, f"班次「{shift}」核对完成：{len(verified)} 条通过，{len(fixing)} 条待修正"

    def confirm_shift(self, shift: str) -> tuple[dict[str, Any] | None, str]:
        """确认核对结果：已核对记录打包成交接文件进入正式记录；无异常的班次同时生成说明文件。"""
        rows = _shift_rows(shift)
        if not rows:
            return None, f"班次「{shift}」下没有安防记录，无法生成交接文件"
        staged = [row for row in rows if row.get("核对状态") == REVIEW_STAGED]
        if staged:
            return None, f"班次「{shift}」还有 {len(staged)} 条未核对，未核对的内容不能进入正式记录"
        verified = [row for row in rows if row.get("核对状态") == REVIEW_VERIFIED]
        if not verified:
            return None, f"班次「{shift}」没有已核对记录，请先完成逐项核对"
        abnormal = [row for row in verified if row.get("abnormal") or row.get("status") == "发现异常"]
        fixing = [row for row in rows if row.get("核对状态") == REVIEW_FIX]
        for row in verified:
            row["核对状态"] = REVIEW_HANDED_OVER
        files = store.rows(FILE_MODULE)
        handover = {
            "id": max((int(item.get("id", 0)) for item in files), default=0) + 1,
            "文件编号": self._next_file_no("SEC-HO"),
            "文件类型": "交接文件",
            "巡视班次": shift,
            "生成时间": _now(),
            "记录数": len(verified),
            "异常数": len(abnormal),
            "待修正数": len(fixing),
            "交接事项": [str(row.get("交接事项")) for row in verified if str(row.get("交接事项") or "").strip()],
            "记录明细": [dict(row) for row in verified],
        }
        files.append(handover)
        generated = [handover]
        message = f"班次「{shift}」交接文件 {handover['文件编号']} 已生成，{len(verified)} 条记录进入正式记录"
        if not abnormal:
            note = {
                "id": max((int(item.get("id", 0)) for item in files), default=0) + 1,
                "文件编号": self._next_file_no("SEC-NOTE"),
                "文件类型": "说明文件",
                "巡视班次": shift,
                "生成时间": _now(),
                "记录数": len(verified),
                "异常数": 0,
                "待修正数": len(fixing),
                "内容": f"班次「{shift}」本班巡视无异常，{len(verified)} 条记录已核对并进入正式记录。",
                "记录明细": [dict(row) for row in verified],
            }
            files.append(note)
            generated.append(note)
            message += f"；本班无异常，说明文件 {note['文件编号']} 已一并生成"
        if fixing:
            message += f"；{len(fixing)} 条记录留在待修正清单"
        return {"文件": generated}, message

    def correct_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """修正待修正清单里的记录：更新编号、区域或人员后放回核对区重新核对。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"安防记录 {entry_id} 不存在或已归档"
        if entry.get("核对状态") != REVIEW_FIX:
            return None, "只有待修正的记录可以修正后重新核对"
        changed = False
        for field in CORRECTABLE_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip():
                entry[field] = value
                changed = True
        if not changed:
            return None, "没有提交需要修正的字段"
        entry["核对状态"] = REVIEW_STAGED
        entry.pop("修正原因", None)
        return entry, "记录已修正并放回核对区，等待重新逐项核对"

    def list_review(self, shift: str | None = None) -> list[dict[str, Any]]:
        """取样核对区现状：未核对与已核对的记录；未给班次时为空。"""
        if not shift:
            return []
        return [row for row in _shift_rows(shift) if row.get("核对状态") in (REVIEW_STAGED, REVIEW_VERIFIED)]

    def list_corrections(self, shift: str | None = None) -> list[dict[str, Any]]:
        """待修正清单：重复巡视编号或缺区域、人员的记录留在里面。"""
        rows = [row for row in store.rows(MODULE) if row.get("核对状态") == REVIEW_FIX]
        if shift:
            rows = [row for row in rows if str(row.get("巡视班次") or "").strip() == shift]
        return rows

    def list_files(self, shift: str | None = None) -> list[dict[str, Any]]:
        """结果文件列表：交接文件与无异常班次的说明文件，最新在前。"""
        files = store.rows(FILE_MODULE)
        if shift:
            files = [item for item in files if str(item.get("巡视班次") or "") == shift]
        return list(reversed(files))

    @staticmethod
    def _next_file_no(prefix: str) -> str:
        files = store.rows(FILE_MODULE)
        seq = sum(1 for item in files if str(item.get("文件编号", "")).startswith(prefix)) + 1
        return f"{prefix}-{seq:04d}"
