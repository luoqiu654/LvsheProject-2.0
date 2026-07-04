"""
安全命令执行模块。

功能：
- 仅允许预定义的安全命令
- 所有文件操作通过封装的安全函数
- 确认流程控制

允许的安全命令：
1. 列出 output 目录内容
2. 生成下载链接
3. 清理超过 24 小时的临时文件
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from backend.config import PROJECT_ROOT
from backend.core.contract_annotator import contract_annotator


class CommandType(str, Enum):
    """允许的命令类型。"""
    LIST_FILES = "list_files"
    GET_DOWNLOAD_PATH = "get_download_path"
    CLEANUP_EXPIRED = "cleanup_expired"
    GENERATE_ANNOTATED = "generate_annotated"


class ConfirmationStatus(str, Enum):
    """确认状态。"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXECUTED = "executed"


@dataclass
class SafeCommand:
    """
    安全命令对象。
    """
    command_id: str
    command_type: CommandType
    params: dict[str, Any]
    status: ConfirmationStatus
    user_id: str
    description: str  # 给用户看的描述
    result: Optional[dict[str, Any]] = None


@dataclass
class CommandResult:
    """
    命令执行结果。
    """
    success: bool
    message: str
    data: dict[str, Any]


class SafeCommandExecutor:
    """
    安全命令执行器。

    设计原则：
    1. 白名单机制：只允许预定义的安全命令
    2. 确认流程：危险操作需要用户确认
    3. 审计日志：记录所有命令执行
    4. 最小权限：每个命令只能访问它需要的资源
    """

    def __init__(self) -> None:
        self._pending_commands: dict[str, SafeCommand] = {}
        self._command_handlers: dict[CommandType, Callable] = {
            CommandType.LIST_FILES: self._handle_list_files,
            CommandType.GET_DOWNLOAD_PATH: self._handle_get_download_path,
            CommandType.CLEANUP_EXPIRED: self._handle_cleanup_expired,
            CommandType.GENERATE_ANNOTATED: self._handle_generate_annotated,
        }
        # 需要确认的命令
        self._requires_confirmation = {
            CommandType.CLEANUP_EXPIRED,
            CommandType.GENERATE_ANNOTATED,
        }

    def create_command(
        self,
        command_type: CommandType,
        params: dict[str, Any],
        user_id: str,
        description: str,
    ) -> SafeCommand:
        """
        创建一个命令（但不执行）。

        如果命令需要确认，状态为 pending。
        如果命令不需要确认，直接执行。
        """
        import uuid
        command_id = str(uuid.uuid4())[:12]

        command = SafeCommand(
            command_id=command_id,
            command_type=command_type,
            params=params,
            status=ConfirmationStatus.PENDING,
            user_id=user_id,
            description=description,
        )

        # 检查是否需要确认
        if command_type in self._requires_confirmation:
            self._pending_commands[command_id] = command
            return command
        else:
            # 不需要确认，直接执行
            return self.execute_command(command_id, user_id)

    def confirm_command(self, command_id: str, user_id: str) -> SafeCommand:
        """
        用户确认执行命令。
        """
        command = self._get_command(command_id, user_id)
        if command.status != ConfirmationStatus.PENDING:
            raise ValueError(f"命令状态异常：{command.status}")

        command.status = ConfirmationStatus.CONFIRMED
        return self.execute_command(command_id, user_id)

    def reject_command(self, command_id: str, user_id: str) -> SafeCommand:
        """
        用户拒绝执行命令。
        """
        command = self._get_command(command_id, user_id)
        command.status = ConfirmationStatus.REJECTED
        return command

    def execute_command(self, command_id: str, user_id: str) -> SafeCommand:
        """
        执行命令。
        """
        command = self._get_command(command_id, user_id)

        if command.command_type not in self._command_handlers:
            raise ValueError(f"未知命令类型：{command.command_type}")

        handler = self._command_handlers[command.command_type]

        try:
            result = handler(command.params, user_id)
            command.result = {
                "success": result.success,
                "message": result.message,
                "data": result.data,
            }
            command.status = ConfirmationStatus.EXECUTED
        except Exception as exc:
            command.result = {
                "success": False,
                "message": str(exc),
                "data": {},
            }
            command.status = ConfirmationStatus.EXECUTED

        # 清理已完成的命令（保留一段时间）
        # 简化实现：执行后从 pending 中移除
        if command_id in self._pending_commands:
            del self._pending_commands[command_id]

        return command

    def get_pending_commands(self, user_id: str) -> list[SafeCommand]:
        """
        获取用户的待确认命令列表。
        """
        return [
            cmd for cmd in self._pending_commands.values()
            if cmd.user_id == user_id and cmd.status == ConfirmationStatus.PENDING
        ]

    def _get_command(self, command_id: str, user_id: str) -> SafeCommand:
        """
        获取命令（安全检查）。
        """
        command = self._pending_commands.get(command_id)
        if not command:
            raise ValueError(f"命令不存在：{command_id}")

        if command.user_id != user_id:
            raise ValueError("无权访问此命令")

        return command

    # ========== 命令处理函数 ==========

    def _handle_list_files(
        self,
        params: dict[str, Any],
        user_id: str,
    ) -> CommandResult:
        """
        列出用户文件。
        """
        files = contract_annotator.list_user_files(user_id)
        return CommandResult(
            success=True,
            message=f"找到 {len(files)} 个文件",
            data={"files": files},
        )

    def _handle_get_download_path(
        self,
        params: dict[str, Any],
        user_id: str,
    ) -> CommandResult:
        """
        获取下载路径。
        """
        filename = params.get("filename", "")
        file_path = contract_annotator.get_file_path(filename, user_id)

        if not file_path:
            return CommandResult(
                success=False,
                message=f"文件不存在或无权访问：{filename}",
                data={},
            )

        return CommandResult(
            success=True,
            message="获取成功",
            data={"file_path": file_path, "filename": filename},
        )

    def _handle_cleanup_expired(
        self,
        params: dict[str, Any],
        user_id: str,
    ) -> CommandResult:
        """
        清理过期文件。
        """
        cleaned = contract_annotator.cleanup_expired_files(user_id)
        return CommandResult(
            success=True,
            message=f"已清理 {cleaned} 个过期文件",
            data={"cleaned_count": cleaned},
        )

    def _handle_generate_annotated(
        self,
        params: dict[str, Any],
        user_id: str,
    ) -> CommandResult:
        """
        生成带标注的合同文件。

        这是一个需要确认的命令。
        """
        original_path = params.get("original_path", "")
        risk_points = params.get("risk_points", [])

        if not original_path:
            return CommandResult(
                success=False,
                message="缺少原始文件路径",
                data={},
            )

        result = contract_annotator.annotate_contract(
            original_path=original_path,
            risk_points=risk_points,
            user_id=user_id,
        )

        return CommandResult(
            success=result.success,
            message=result.error_message or "标注完成",
            data={
                "annotated_path": result.annotated_path,
                "annotated_filename": result.annotated_filename,
                "risk_count": result.risk_count,
                "high_risk_count": result.high_risk_count,
                "medium_risk_count": result.medium_risk_count,
                "low_risk_count": result.low_risk_count,
            },
        )


# 全局实例
safe_command_executor = SafeCommandExecutor()
