"""安防巡视业务规则：状态流转、班次核对与交接文件生成都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "security"
REQUIRED_FIELDS = ["巡视编号", "巡视区域", "巡视人员", "巡视班次"]
STATUS_ORDER = ["已排班", "巡视中", "正常完成", "发现异常"]
ACTION_RULES = {"开始巡视": "巡视中", "记录异常": "发现异常", "完成巡视": "正常完成"}
NEGATIVE_ACTIONS = ["记录异常"]

# 班次核对流转：未取样 -> 待核对 -> 已核对 / 待修正，确认交接后写入正式记录
REVIEW_STAGES = ["未取样", "待核对", "已核对", "待修正"]
HANDOVER_FIELDS = ["巡视编号", "巡视区域", "巡视人员", "巡视时间", "异常描述", "处理情况", "交接事项"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SecurityService:
    def __init__(self) -> None:
        # 巡视班次 -> {"状态": 核对中/已交接, "取样时间": str, "文件": [...]}
        self._shifts: dict[str, dict[str, Any]] = {}

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
            rows = [row for row in rows if str(row.get("巡视班次") or "") == shift]
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
        entry.update({field: str(values.get(field)).strip() for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        # 新登记的记录先不进核对区，等班次取样时再统一放入
        entry["核对状态"] = REVIEW_STAGES[0]
        entry["正式记录"] = False
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

    # ---- 班次核对与交接 ----

    def list_shifts(self) -> list[dict[str, Any]]:
        """按巡视班次汇总核对进度，给班次选择列表用。"""
        summaries: dict[str, dict[str, Any]] = {}
        for row in store.rows(MODULE):
            shift = str(row.get("巡视班次") or "").strip()
            if not shift:
                continue
            summary = summaries.setdefault(shift, {
                "巡视班次": shift, "记录数": 0, "待核对": 0, "已核对": 0, "待修正": 0, "异常数": 0,
            })
            summary["记录数"] += 1
            stage = str(row.get("核对状态") or "")
            if stage in ("待核对", "已核对", "待修正"):
                summary[stage] += 1
            if self._is_abnormal(row):
                summary["异常数"] += 1
        for shift, summary in summaries.items():
            state = self._shifts.get(shift)
            summary["班次状态"] = state["状态"] if state else "未取样"
            summary["文件数"] = len(state["文件"]) if state else 0
        return [summaries[key] for key in sorted(summaries)]

    def stage_shift(self, shift: str) -> tuple[dict[str, Any] | None, str]:
        """班次取样：把本班记录放进取样核对区。"""
        rows = self._shift_rows(shift)
        if not rows:
            return None, f"班次「{shift}」没有安防记录，无法取样"
        if shift in self._shifts:
            return None, f"班次「{shift}」已在取样核对区，请勿重复取样"
        staged = [row for row in rows if row.get("核对状态") == "未取样"]
        if not staged:
            return None, f"班次「{shift}」没有待取样的记录"
        for row in staged:
            row["核对状态"] = "待核对"
        self._shifts[shift] = {"状态": "核对中", "取样时间": _now(), "文件": []}
        summary = {"巡视班次": shift, "取样条数": len(staged), "取样时间": self._shifts[shift]["取样时间"]}
        return summary, f"班次「{shift}」已取样 {len(staged)} 条记录，进入取样核对区"

    def review_shift(self, shift: str) -> tuple[dict[str, Any] | None, str]:
        """逐项核对：按巡视区域和人员检查本班记录，重复巡视编号留在待修正清单。"""
        state = self._shifts.get(shift)
        if state is None:
            return None, f"班次「{shift}」尚未取样，请先把本班记录放进取样核对区"
        pending = [row for row in self._shift_rows(shift) if row.get("核对状态") == "待核对"]
        if not pending:
            return None, f"班次「{shift}」没有待核对的记录"
        pending.sort(key=lambda row: (
            str(row.get("巡视区域") or ""), str(row.get("巡视人员") or ""), int(row.get("id", 0)),
        ))
        items = []
        for row in pending:
            problems = [
                f"{field}为空"
                for field in ("巡视区域", "巡视人员")
                if not str(row.get(field) or "").strip()
            ]
            code = str(row.get("巡视编号") or "").strip()
            if self._is_duplicate_code(shift, code):
                problems.append(f"巡视编号 {code} 在本班重复")
            row["核对状态"] = "待修正" if problems else "已核对"
            row["核对意见"] = "；".join(problems) if problems else "区域与人员核对一致"
            items.append({
                "id": row.get("id"),
                "巡视编号": row.get("巡视编号"),
                "巡视区域": row.get("巡视区域"),
                "巡视人员": row.get("巡视人员"),
                "核对结果": row["核对状态"],
                "核对意见": row["核对意见"],
            })
        corrections = sum(1 for item in items if item["核对结果"] == "待修正")
        report = {"巡视班次": shift, "核对时间": _now(), "核对项": items, "待修正数": corrections}
        if corrections:
            return report, f"班次「{shift}」逐项核对完成，{corrections} 条重复编号留在待修正清单"
        return report, f"班次「{shift}」逐项核对完成，{len(items)} 条记录全部通过"

    def list_corrections(self, shift: str) -> list[dict[str, Any]]:
        """待修正清单：本班核对时发现重复巡视编号的记录。"""
        return [row for row in self._shift_rows(shift) if row.get("核对状态") == "待修正"]

    def correct_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """修正待修正记录：换上新的巡视编号后自动复核对本班待修正清单。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"安防记录 {entry_id} 不存在或已归档"
        if entry.get("核对状态") != "待修正":
            return None, f"安防记录 {entry_id} 不在待修正清单里，无需修正"
        new_code = str(values.get("巡视编号") or "").strip()
        if not new_code:
            return None, "修正时必须给出新的巡视编号"
        shift = str(entry.get("巡视班次") or "")
        entry["巡视编号"] = new_code
        remaining = 0
        for row in self._shift_rows(shift):
            if row.get("核对状态") != "待修正":
                continue
            code = str(row.get("巡视编号") or "").strip()
            if self._is_duplicate_code(shift, code):
                row["核对意见"] = f"巡视编号 {code} 在本班重复"
                remaining += 1
            else:
                row["核对状态"] = "已核对"
                row["核对意见"] = "修正后核对通过"
        if remaining:
            return entry, f"已修正并复核对，班次「{shift}」待修正清单还剩 {remaining} 条"
        return entry, f"已修正并复核对，班次「{shift}」待修正清单已清空"

    def confirm_shift(self, shift: str) -> tuple[dict[str, Any] | None, str]:
        """确认交接：核对无误后打包交接文件；本班无异常时同时生成说明文件。"""
        state = self._shifts.get(shift)
        if state is None:
            return None, f"班次「{shift}」尚未取样，不能确认交接"
        if state["状态"] == "已交接":
            return None, f"班次「{shift}」已生成交接文件，请勿重复确认"
        rows = self._shift_rows(shift)
        unchecked = [row for row in rows if row.get("核对状态") in ("未取样", "待核对")]
        if unchecked:
            return None, f"班次「{shift}」还有 {len(unchecked)} 条记录未核对，未核对的内容不能进入正式记录"
        corrections = [row for row in rows if row.get("核对状态") == "待修正"]
        if corrections:
            return None, f"班次「{shift}」待修正清单还有 {len(corrections)} 条重复编号，修正后才能交接"
        verified = [row for row in rows if row.get("核对状态") == "已核对"]
        if not verified:
            return None, f"班次「{shift}」没有已核对的记录，无法生成交接文件"
        now = _now()
        abnormal_rows = [row for row in verified if self._is_abnormal(row)]
        for row in verified:
            row["正式记录"] = True
        files: list[dict[str, Any]] = [{
            "文件类型": "交接文件",
            "文件名": f"安防交接-{shift}.json",
            "生成时间": now,
            "巡视班次": shift,
            "记录数": len(verified),
            "异常数": len(abnormal_rows),
            "交接事项": [
                str(row.get("交接事项")).strip()
                for row in verified
                if str(row.get("交接事项") or "").strip()
            ],
            "记录": [
                {field: row.get(field) for field in ("id", *HANDOVER_FIELDS)}
                for row in verified
            ],
        }]
        if not abnormal_rows:
            files.append({
                "文件类型": "说明文件",
                "文件名": f"安防说明-{shift}.json",
                "生成时间": now,
                "巡视班次": shift,
                "说明": f"班次「{shift}」本班巡视无异常，{len(verified)} 条记录核对一致，准予交接。",
            })
        state["文件"].extend(files)
        state["状态"] = "已交接"
        state["交接时间"] = now
        result = {"巡视班次": shift, "交接时间": now, "文件": files}
        return result, f"班次「{shift}」已确认交接，生成 {len(files)} 个文件"

    def list_files(self, shift: str) -> list[dict[str, Any]] | None:
        """查看本班已生成的交接文件与说明文件；未取样的班次返回 None。"""
        state = self._shifts.get(shift)
        if state is None:
            return None
        return state["文件"]

    # ---- 内部小工具 ----

    def _shift_rows(self, shift: str) -> list[dict[str, Any]]:
        return [row for row in store.rows(MODULE) if str(row.get("巡视班次") or "") == shift]

    def _is_duplicate_code(self, shift: str, code: str) -> bool:
        if not code:
            return False
        return sum(
            1 for row in self._shift_rows(shift)
            if str(row.get("巡视编号") or "").strip() == code
        ) > 1

    @staticmethod
    def _is_abnormal(row: dict[str, Any]) -> bool:
        return bool(row.get("abnormal")) or row.get("status") == "发现异常"
