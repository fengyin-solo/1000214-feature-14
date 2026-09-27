"""安防巡视接口：维护安防记录，覆盖班次取样、逐项核对、确认交接等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.security import SecurityService

router = APIRouter(prefix="/api/security", tags=["安防巡视"])

service = SecurityService()

LIST_FIELDS = ["巡视编号", "巡视区域", "巡视人员", "巡视班次", "巡视时间", "异常描述", "处理情况", "交接事项", "核对状态"]
STATUSES = ["已排班", "巡视中", "正常完成", "发现异常"]


# 静态路径要放在 /{entry_id} 之前，否则 "shifts"、"export" 会被当成记录 id 解析。

@router.get("/shifts")
def list_shifts() -> dict[str, Any]:
    """按巡视班次汇总核对进度：记录数、待核对、待修正与交接状态。"""
    return {"items": service.list_shifts()}


@router.post("/shifts/{shift}/stage", response_model=ActionResult)
def stage_shift(shift: str) -> ActionResult:
    """班次取样：把本班记录放进取样核对区，等待逐项核对。"""
    summary, message = service.stage_shift(shift)
    if summary is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=summary)


@router.post("/shifts/{shift}/review", response_model=ActionResult)
def review_shift(shift: str) -> ActionResult:
    """逐项核对：按巡视区域和人员检查本班记录，重复巡视编号留在待修正清单。"""
    report, message = service.review_shift(shift)
    if report is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=report)


@router.get("/shifts/{shift}/corrections")
def list_corrections(shift: str) -> dict[str, Any]:
    """待修正清单：本班核对时发现重复巡视编号的记录。"""
    return {"items": service.list_corrections(shift)}


@router.post("/shifts/{shift}/confirm", response_model=ActionResult)
def confirm_shift(shift: str) -> ActionResult:
    """确认交接：核对无误后打包交接文件；本班无异常时同时生成说明文件。"""
    result, message = service.confirm_shift(shift)
    if result is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=result)


@router.get("/shifts/{shift}/files")
def list_shift_files(shift: str) -> dict[str, Any]:
    """查看本班已生成的交接文件与说明文件。"""
    files = service.list_files(shift)
    if files is None:
        raise HTTPException(status_code=404, detail=f"班次「{shift}」尚未取样，没有已生成的文件")
    return {"items": files}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出安防巡视清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "security", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按巡视编号检索"),
    status: str | None = Query(default=None, description="已排班、巡视中、正常完成、发现异常"),
    shift: str | None = Query(default=None, description="按巡视班次过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按巡视编号、状态与班次过滤安防巡视列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, shift=shift, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
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
    return ActionResult(ok=True, message="安防记录已登记，待班次取样核对", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条安防记录执行开始巡视、记录异常、完成巡视；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/correct", response_model=ActionResult)
def correct_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修正待修正记录：换上新的巡视编号后自动复核对，不再重复即回到已核对。"""
    entry, message = service.correct_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
