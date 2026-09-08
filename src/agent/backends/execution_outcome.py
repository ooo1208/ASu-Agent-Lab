"""Classify transport errors without assuming a timed-out command never ran."""

import httpx


def classify_execution_error(error: Exception) -> str:
    if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)):
        return "not_dispatched"
    return "outcome_unknown"


def execution_error_message(error: Exception) -> str:
    outcome = classify_execution_error(error)
    if outcome == "not_dispatched":
        return "[not_dispatched] 无法建立沙箱连接。先恢复连接后再决定是否重新提交。"
    return "[outcome_unknown] 命令可能已经执行，但未收到可靠结果。先检查文件、任务或业务记录，禁止盲目重放有副作用的操作。"
