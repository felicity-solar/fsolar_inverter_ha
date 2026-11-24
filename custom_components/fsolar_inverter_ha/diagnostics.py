"""可下载的脱敏诊断信息。

是什么：一个「配置 + 最近快照」的字典，敏感字段被替换成 **REDACTED**。
什么时候：只有用户点集成卡片上的「下载诊断」时 HA 才调用
async_get_config_entry_diagnostics，正常轮询时不会调用。
被谁调用：HA 按模块名 + 函数名约定发现它。本文件只读 entry 和协调器，不改任何东西。
"""
from __future__ import annotations

from dataclasses import asdict

from homeassistant.components.diagnostics import async_redact_data

# 绝不能离开用户机器的字段。用户会把诊断文件直接贴到公开的 GitHub issue，
# 所以密码、token、各类标识与精确位置都要加进来。
TO_REDACT = {"host", "serial", "serial_number"}


# 用户点「下载诊断」时由 HA 调用；返回的字典会变成 JSON 文件。
async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "identity": async_redact_data(asdict(coordinator.identity), TO_REDACT),
        "data": asdict(coordinator.data),
    }