"""安防巡视接口：维护安防记录，覆盖开始巡视、记录异常、完成巡视等动作。

班次结果文件流程：取样入核对区 -> 逐项核对 -> 确认生成交接文件；
重复巡视编号留在待修正清单，无异常的班次同时生成说明文件。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.security import SecurityService

router = APIRouter(prefix="/api/security", tags=["安防巡视"])

service = SecurityService()

LIST_FIELDS = ["巡视编号", "巡视区域", "巡视人员", "巡视班次", "巡视时间", "异常描述", "处理情况", "交接事项", "巡视状态"]
STATUSES = ["已排班", "巡视中", "正常完成", "发现异常"]


def _shift_of(payload: EntryPayload) -> str:
    return str(payload.values.get("巡视班次") or "").strip()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按巡视编号检索"),
    status: str | None = Query(default=None, description="已排班、巡视中、正常完成、发现异常"),
    shift: str | None = Query(default=None, description="按巡视班次过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按巡视编号与状态过滤安防巡视列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, shift=shift, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/review")
def review_area(shift: str | None = Query(default=None, description="巡视班次")) -> dict[str, Any]:
    """取样核对区现状：本班未核对与已核对的记录；未给班次时返回空区。"""
    items = service.list_review(shift)
    return {"shift": shift, "total": len(items), "items": items}


@router.get("/corrections")
def correction_list(shift: str | None = Query(default=None, description="巡视班次")) -> dict[str, Any]:
    """待修正清单：重复巡视编号或缺区域、人员的记录留在里面，不进入正式记录。"""
    items = service.list_corrections(shift)
    return {"total": len(items), "items": items}


@router.get("/files")
def result_files(shift: str | None = Query(default=None, description="巡视班次")) -> dict[str, Any]:
    """结果文件列表：交接文件与无异常班次的说明文件，最新在前。"""
    items = service.list_files(shift)
    return {"total": len(items), "items": items}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出安防巡视清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "security", "total": total, "items": items}


@router.get("/{entry_id:int}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条安防记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"安防记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条安防记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="安防记录已登记", entry=entry)


@router.post("/shifts/collect", response_model=ActionResult)
def collect_shift(payload: EntryPayload) -> ActionResult:
    """把本班记录放进取样核对区，等待逐项核对。"""
    shift = _shift_of(payload)
    if not shift:
        return ActionResult(ok=False, message="请先填写巡视班次再取样")
    staged, message = service.collect_shift(shift)
    return ActionResult(ok=bool(staged), message=message, entry={"items": staged} if staged else None)


@router.post("/shifts/review", response_model=ActionResult)
def review_shift(payload: EntryPayload) -> ActionResult:
    """按巡视区域、巡视人员逐项检查核对区记录；重复巡视编号留在待修正清单。"""
    shift = _shift_of(payload)
    if not shift:
        return ActionResult(ok=False, message="请先填写巡视班次再核对")
    summary, message = service.review_shift(shift)
    if summary is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=summary)


@router.post("/shifts/confirm", response_model=ActionResult)
def confirm_shift(payload: EntryPayload) -> ActionResult:
    """确认核对结果并打包交接文件；未核对的内容不能进入正式记录。"""
    shift = _shift_of(payload)
    if not shift:
        return ActionResult(ok=False, message="请先填写巡视班次再确认")
    result, message = service.confirm_shift(shift)
    if result is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=result)


@router.post("/{entry_id:int}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条安防记录执行开始巡视、记录异常、完成巡视；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id:int}/correct", response_model=ActionResult)
def correct_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修正待修正清单里的记录：更新编号、区域或人员后放回核对区重新核对。"""
    entry, message = service.correct_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
