"""迁移链路共用的固定错误投影，排除底层原文和私有路径。"""
from __future__ import annotations

import errno


_REASONS = {
    'busy': ('源环境仍有实际工作或维护待收口', '等待原工作完成后继续原迁移'),
    'disk_space': ('迁移暂存磁盘空间不足', '释放对应节点空间后继续原迁移'),
    'connection': ('迁移节点连接中断', '检查节点连接后继续原迁移'),
    'identity': ('迁移资料身份或归属校验失败', '核对原账号、节点与迁移回执后继续'),
    'source_changed': ('源环境资料在导出期间发生变化', '确认源环境停止并收口写入后继续原迁移'),
    'incomplete': ('原迁移包或回执尚未完整核对', '保留原操作资料并核对完整回执'),
    'unconfirmed': ('本阶段执行结果尚未确认', '检查节点状态后继续原操作核对'),
    'system_profile': ('目标运行环境的系统画像校验失败', '核对节点组件版本与保存的系统画像后继续原迁移'),
    'component_version': ('目标节点运行组件正在同步', '等待后台同步完成后继续原迁移'),
    'node_configuration': ('迁移节点的数据位置或主机身份已变化', '恢复原节点位置或核对原操作后继续迁移'),
    'runtime_preparation': ('目标容器或运行组件准备失败', '检查节点Docker状态、镜像和资源后继续原迁移'),
}
_STAGES = {'draining', 'fence', 'export', 'transfer', 'verify-import', 'prepare-import',
    'commit', 'activate-import', 'revoke-import', 'restore-source', 'context', 'preflight'}


class MigrationFailure(ValueError):
    """仅携带共用白名单中的迁移原因和执行阶段。

    :param code: 固定原因。
    :param stage: 固定执行阶段。
    """

    def __init__(self, code: str, stage: str) -> None:
        """核对固定原因和阶段。:param code: 固定原因。:param stage: 固定阶段。:return: None。"""
        if code not in _REASONS or stage not in _STAGES:
            raise ValueError('迁移错误协议无效')
        self.code, self.stage = code, stage
        super().__init__(_REASONS[code][0])

    def public(self) -> dict:
        """返回固定公开字段。:return: 原因、阶段、说明及动作。"""
        message, action = _REASONS[self.code]
        return {'code': self.code, 'stage': self.stage, 'message': message, 'action': action}


def migration_failure(error: Exception, stage: str) -> dict:
    """将实际异常映射为固定显示原因。

    :param error: 实际异常；正文只用于匹配完全已知的固定说明。
    :param stage: 当前执行步骤。
    :return: 受控公开投影；不改变原恢复权限。
    """
    if isinstance(error, MigrationFailure):
        return error.public()
    code = 'unconfirmed'
    if type(error).__name__ == 'RuntimeBusy':
        code = 'busy'
    elif isinstance(error, OSError) and error.errno in (errno.ENOSPC, errno.EDQUOT):
        code = 'disk_space'
    elif getattr(error, 'reason', None) in ('timeout', 'connection_failed', 'remote_command_failed'):
        code = 'connection'
    elif str(error) in ('目标节点迁移暂存空间不足',):
        code = 'disk_space'
    elif str(error) in ('迁移期间源文件被替换', '迁移期间源文件内容发生变化', '迁移期间源环境发生变化',
            '盘点期间文件被替换', '盘点期间文件内容发生变化'):
        code = 'source_changed'
    elif str(error) in ('原导出回执或文件已变化', '目标暂存包含不完整上传，请使用新的上传尝试',
            '迁移包尚未上传完成'):
        code = 'incomplete'
    elif str(error) in ('系统画像与实际 CPU 代际冲突，需要核对迁移',
            '系统画像尚无当前 CPU 代际的兼容模板，请保留环境并补充核验',
            '计算机画像尚无兼容模板，请保留已有身份', '系统画像模板或内容损坏，禁止重新随机',
            '系统画像CPU字段损坏，禁止重新随机', '计算机画像内容或 CPU 兼容性无效，禁止重新随机',
            '系统画像格式或版本无效，禁止重新随机', '计算机画像格式或版本无效，禁止重新随机',
            '计算机画像模板或字段损坏，禁止重新随机', '计算机画像 UUID 无效，禁止重新随机'):
        code = 'system_profile'
    elif str(error) in ('目标原准备仍有实际角色或未知归属，请先核对', '目标原准备仍有实际作业，请先核对'):
        code = 'busy'
    elif str(error) in ('目标暂存的CLI设备或登录账号与源收据不一致', '目标准备后的CLI身份与源回执不一致',
            '目标发布与源账号、分配、身份或代次不一致', '目标恢复缺少原迁移发布证明'):
        code = 'identity'
    elif str(error) == '迁移目标需要先准备同批执行组件':
        code = 'component_version'
    elif str(error) == '迁移原节点配置版本已变化，请核对原操作':
        code = 'node_configuration'
    elif (type(error).__name__ in ('APIError', 'DockerException', 'ImageNotFound', 'ContainerError')
            or str(error) in ('账号隔离网络未就绪，业务未启动', '账号环境需要先对账，拒绝自动放行')):
        code = 'runtime_preparation'
    return MigrationFailure(code, stage if stage in _STAGES else 'context').public()


def public_failure(value: object) -> dict | None:
    """重新生成公开投影，拒绝透传记录中的任意正文。:param value: 历史字段。:return: 固定投影或空。"""
    if (not isinstance(value, dict) or value.get('code') not in _REASONS
            or value.get('stage') not in _STAGES):
        return None
    return MigrationFailure(value['code'], value['stage']).public()
