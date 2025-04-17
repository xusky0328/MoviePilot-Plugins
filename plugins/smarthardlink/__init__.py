import datetime
import hashlib
import os
import re
import threading
import traceback
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Set

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import schemas
from app.core.config import settings
from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.system import SystemUtils

lock = threading.Lock()


class SmartHardLink(_PluginBase):
    # 插件名称
    plugin_name = "智能硬链接"
    # 插件描述
    plugin_desc = "通过计算文件SHA1，将指定目录中相同SHA1的文件只保留一个，其他的用硬链接替换，用来清理重复占用的磁盘空间。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/madrays/MoviePilot-Plugins/main/icons/hardlink.png"
    # 插件版本
    plugin_version = "1.0.2"
    # 插件作者
    plugin_author = "madrays"
    # 作者主页
    author_url = "https://github.com/madrays/MoviePilot-Plugins"
    # 插件配置项ID前缀
    plugin_config_prefix = "smarthardlink_"
    # 加载顺序
    plugin_order = 11
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _scheduler = None
    _enabled = False
    _onlyonce = False
    _cron = None
    _scan_dirs = ""
    _min_size = 1024  # 默认最小文件大小，单位KB
    _exclude_dirs = ""
    _exclude_extensions = ""
    _exclude_keywords = ""
    _hash_buffer_size = 65536  # 计算哈希时的缓冲区大小，默认64KB
    _dry_run = True  # 默认为试运行模式，不实际创建硬链接
    _hash_cache = {}  # 保存文件哈希值的缓存
    _process_count = 0  # 处理的文件计数
    _hardlink_count = 0  # 创建的硬链接计数
    _saved_space = 0  # 节省的空间统计，单位字节

    # 退出事件
    _event = threading.Event()

    def init_plugin(self, config: dict = None):
        """
        插件初始化
        """
        # 读取配置
        if config:
            self._enabled = config.get("enabled")
            self._onlyonce = config.get("onlyonce")
            self._cron = config.get("cron")
            self._scan_dirs = config.get("scan_dirs") or ""
            self._min_size = int(config.get("min_size") or 1024)
            self._exclude_dirs = config.get("exclude_dirs") or ""
            self._exclude_extensions = config.get("exclude_extensions") or ""
            self._exclude_keywords = config.get("exclude_keywords") or ""
            self._hash_buffer_size = int(config.get("hash_buffer_size") or 65536)
            self._dry_run = bool(config.get("dry_run"))

        # 停止现有任务
        self.stop_service()

        if self._enabled or self._onlyonce:
            # 定时服务管理器
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)

            # 运行一次定时服务
            if self._onlyonce:
                logger.info("智能硬链接服务启动，立即运行一次")
                self._scheduler.add_job(
                    name="智能硬链接",
                    func=self.scan_and_process,
                    trigger="date",
                    run_date=datetime.datetime.now(tz=pytz.timezone(settings.TZ))
                    + datetime.timedelta(seconds=3),
                )
                # 关闭一次性开关
                self._onlyonce = False
                # 保存配置
                self.__update_config()

            # 启动定时服务
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

    def __update_config(self):
        """
        更新配置
        """
        self.update_config(
            {
                "enabled": self._enabled,
                "onlyonce": self._onlyonce,
                "cron": self._cron,
                "scan_dirs": self._scan_dirs,
                "min_size": self._min_size,
                "exclude_dirs": self._exclude_dirs,
                "exclude_extensions": self._exclude_extensions,
                "exclude_keywords": self._exclude_keywords,
                "hash_buffer_size": self._hash_buffer_size,
                "dry_run": self._dry_run,
            }
        )

    @eventmanager.register(EventType.PluginAction)
    def remote_scan(self, event: Event):
        """
        远程扫描处理
        """
        if event:
            event_data = event.event_data
            if not event_data or event_data.get("action") != "hardlink_scan":
                return
            self.post_message(
                channel=event.event_data.get("channel"),
                title="开始扫描目录并处理重复文件 ...",
                userid=event.event_data.get("user"),
            )
        
        # 记录开始时间
        start_time = datetime.now()
        
        # 执行扫描和处理
        self.scan_and_process()
        
        # 计算耗时
        elapsed_time = datetime.now() - start_time
        elapsed_seconds = elapsed_time.total_seconds()
        elapsed_formatted = self._format_time(elapsed_seconds)
        
        if event:
            # 发送美观的通知
            title = "【✅ 智能硬链接处理完成】"
            text = (
                f"📢 执行结果\n"
                f"━━━━━━━━━━\n"
                f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"⏱️ 耗时：{elapsed_formatted}\n"
                f"📁 文件数：{self._process_count} 个\n"
                f"🔗 硬链接：{self._hardlink_count} 个\n"
                f"💾 节省空间：{self._format_size(self._saved_space)}\n"
                f"📊 处理模式：{'试运行' if self._dry_run else '实际运行'}\n"
                f"━━━━━━━━━━"
            )
            
            self.post_message(
                channel=event.event_data.get("channel"),
                mtype=NotificationType.SiteMessage,
                title=title,
                text=text,
                userid=event.event_data.get("user"),
            )

    @staticmethod
    def _format_time(seconds):
        """
        格式化时间显示
        """
        if seconds < 60:
            return f"{seconds:.1f} 秒"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{int(minutes)} 分 {int(remaining_seconds)} 秒"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{int(hours)} 小时 {int(minutes)} 分"

    @staticmethod
    def _format_size(size_bytes):
        """
        格式化文件大小显示
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def calculate_file_hash(self, file_path):
        """
        计算文件的SHA1哈希值
        """
        # 检查缓存
        if file_path in self._hash_cache:
            return self._hash_cache[file_path]

        try:
            hash_sha1 = hashlib.sha1()
            with open(file_path, "rb") as f:
                while True:
                    data = f.read(self._hash_buffer_size)
                    if not data:
                        break
                    hash_sha1.update(data)
            
            file_hash = hash_sha1.hexdigest()
            # 保存到缓存
            self._hash_cache[file_path] = file_hash
            return file_hash
        except Exception as e:
            logger.error(f"计算文件 {file_path} 哈希值失败: {str(e)}")
            return None

    def is_excluded(self, file_path: str) -> bool:
        """
        检查文件是否应该被排除
        """
        # 检查排除目录
        if self._exclude_dirs:
            for exclude_dir in self._exclude_dirs.split("\n"):
                if exclude_dir and file_path.startswith(exclude_dir):
                    return True

        # 检查排除文件扩展名
        if self._exclude_extensions:
            file_ext = os.path.splitext(file_path)[1].lower()
            extensions = [f".{ext.strip().lower()}" for ext in self._exclude_extensions.split(",")]
            if file_ext in extensions:
                return True

        # 检查排除关键词
        if self._exclude_keywords:
            for keyword in self._exclude_keywords.split("\n"):
                if keyword and re.findall(keyword, file_path):
                    return True

        return False

    def scan_and_process(self):
        """
        扫描目录并处理重复文件
        """
        try:
            # 重置计数器
            self._process_count = 0
            self._hardlink_count = 0
            self._saved_space = 0
            self._hash_cache = {}
            
            logger.info("开始扫描目录并处理重复文件 ...")
            logger.warning("提醒：本插件仍处于开发试验阶段，请确保数据安全")
            
            if not self._scan_dirs:
                logger.error("未配置扫描目录，无法执行")
                return
            
            scan_dirs = self._scan_dirs.split("\n")
            
            # 第一步：收集所有文件并计算哈希值
            file_hashes = {}  # {hash: [(file_path, file_size), ...]}
            all_files = []  # 存储所有符合条件的文件路径和大小
            
            # 首先收集所有文件信息，避免在遍历时计算哈希
            for scan_dir in scan_dirs:
                if not scan_dir or not os.path.exists(scan_dir):
                    logger.warning(f"扫描目录不存在: {scan_dir}")
                    continue
                    
                logger.info(f"扫描目录: {scan_dir}")
                file_count = 0
                
                try:
                    for root, dirs, files in os.walk(scan_dir):
                        # 定期报告进度
                        if file_count > 0 and file_count % 1000 == 0:
                            logger.info(f"目录 {scan_dir} 已发现 {file_count} 个文件")
                            
                        for file_name in files:
                            file_count += 1
                            file_path = os.path.join(root, file_name)
                            
                            # 跳过符号链接
                            if os.path.islink(file_path):
                                continue
                                
                            # 检查排除条件
                            if self.is_excluded(file_path):
                                continue
                                
                            try:
                                # 检查文件大小
                                file_size = os.path.getsize(file_path)
                                if file_size < self._min_size * 1024:  # 转换为字节
                                    continue
                                    
                                # 添加到待处理文件列表
                                all_files.append((file_path, file_size))
                                
                            except Exception as e:
                                logger.error(f"获取文件信息失败 {file_path}: {str(e)}")
                    
                    logger.info(f"目录 {scan_dir} 扫描完成，共发现 {file_count} 个文件")
                except Exception as e:
                    logger.error(f"扫描目录 {scan_dir} 时出错: {str(e)}")
            
            # 报告收集到的文件总数
            total_files = len(all_files)
            logger.info(f"符合条件的文件总数: {total_files}")
            
            # 根据文件大小排序，优先处理大文件，可以更快发现重复文件节省空间
            all_files.sort(key=lambda x: x[1], reverse=True)
            
            # 处理文件并计算哈希值
            for idx, (file_path, file_size) in enumerate(all_files):
                # 定期报告进度
                if idx > 0 and (idx % 100 == 0 or idx == total_files - 1):
                    logger.info(f"已处理 {idx}/{total_files} 个文件 ({(idx/total_files*100):.1f}%)")
                
                try:
                    # 计算哈希值
                    file_hash = self.calculate_file_hash(file_path)
                    if not file_hash:
                        continue
                        
                    # 记录文件信息
                    if file_hash not in file_hashes:
                        file_hashes[file_hash] = []
                    file_hashes[file_hash].append((file_path, file_size))
                    
                    self._process_count += 1
                except Exception as e:
                    logger.error(f"处理文件 {file_path} 时出错: {str(e)}")
            
            # 找出重复文件的数量
            duplicate_count = sum(len(files) - 1 for files in file_hashes.values() if len(files) > 1)
            logger.info(f"发现 {duplicate_count} 个重复文件")
            
            # 没有重复文件时发送通知
            if duplicate_count == 0:
                logger.info("没有发现重复文件")
                self._send_notify_message(
                    title="【✅ 智能硬链接扫描完成】",
                    text=(
                        f"📢 执行结果\n"
                        f"━━━━━━━━━━\n"
                        f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"📁 已扫描：{self._process_count} 个文件\n"
                        f"🔍 结果：未发现重复文件\n"
                        f"━━━━━━━━━━"
                    )
                )
                return
            
            # 第二步：处理重复文件
            processed_count = 0
            for file_hash, files in file_hashes.items():
                if len(files) <= 1:
                    continue  # 没有重复
                
                processed_count += len(files) - 1
                if processed_count % 10 == 0 or processed_count == duplicate_count:
                    logger.info(f"已处理 {processed_count}/{duplicate_count} 个重复文件 ({(processed_count/duplicate_count*100):.1f}%)")
                    
                # 按文件路径排序，保持第一个文件作为源文件
                files.sort(key=lambda x: x[0])
                source_file, source_size = files[0]
                
                logger.info(f"发现重复文件组 (SHA1: {file_hash}):")
                logger.info(f"  保留源文件: {source_file}")
                
                # 处理重复文件
                for dup_file, dup_size in files[1:]:
                    logger.info(f"  重复文件: {dup_file}")
                    
                    if self._dry_run:
                        logger.info(f"  试运行模式：将创建从 {source_file} 到 {dup_file} 的硬链接")
                        self._hardlink_count += 1
                        self._saved_space += dup_size
                    else:
                        try:
                            # 创建临时备份文件名
                            temp_file = f"{dup_file}.temp_{int(time.time())}"
                            
                            # 重命名原文件为临时文件
                            os.rename(dup_file, temp_file)
                            
                            # 创建硬链接（保持原文件名）
                            os.link(source_file, dup_file)
                            
                            # 删除临时文件
                            os.remove(temp_file)
                            
                            logger.info(f"  已创建硬链接: {dup_file} -> {source_file}")
                            self._hardlink_count += 1
                            self._saved_space += dup_size
                        except Exception as e:
                            # 如果出错，尝试恢复原文件
                            if 'temp_file' in locals() and os.path.exists(temp_file):
                                try:
                                    if os.path.exists(dup_file):
                                        os.remove(dup_file)
                                    os.rename(temp_file, dup_file)
                                    logger.error(f"  创建硬链接失败，已恢复原文件: {str(e)}")
                                except Exception as recover_err:
                                    logger.error(f"  创建硬链接失败且恢复原文件也失败: {str(recover_err)}，原文件位于: {temp_file}")
                            else:
                                logger.error(f"  创建硬链接失败: {str(e)}")
            
            mode_str = "试运行模式" if self._dry_run else "实际运行模式"
            logger.info(f"处理完成！({mode_str}) 共处理文件 {self._process_count} 个，创建硬链接 {self._hardlink_count} 个，节省空间 {self._format_size(self._saved_space)}")
            
            # 发送通知
            self._send_completion_notification()
            
        except Exception as e:
            logger.error(f"扫描处理失败: {str(e)}\n{traceback.format_exc()}")
            
            # 发送错误通知
            self._send_notify_message(
                title="【❌ 智能硬链接处理失败】",
                text=(
                    f"📢 执行结果\n"
                    f"━━━━━━━━━━\n"
                    f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"❌ 错误：{str(e)}\n"
                    f"━━━━━━━━━━\n"
                    f"💡 可能的解决方法\n"
                    f"• 检查目录权限\n"
                    f"• 确认磁盘空间充足\n"
                    f"• 查看日志获取详细错误信息"
                )
            )

    def _send_completion_notification(self):
        """
        发送任务完成通知
        """
        # 构建通知内容
        if self._dry_run:
            title = "【✅ 智能硬链接扫描完成】"
            text = (
                f"📢 执行结果（试运行模式）\n"
                f"━━━━━━━━━━\n"
                f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📁 扫描文件：{self._process_count} 个\n"
                f"🔍 重复文件：{self._hardlink_count} 个\n"
                f"💾 可节省空间：{self._format_size(self._saved_space)}\n"
                f"━━━━━━━━━━\n"
                f"⚠️ 这是试运行模式，没有创建实际硬链接\n"
                f"💡 在设置中关闭试运行模式可实际执行硬链接操作\n"
                f"⚠️ 注意：本插件仍处于开发试验阶段，请注意数据安全"
            )
        else:
            title = "【✅ 智能硬链接处理完成】"
            text = (
                f"📢 执行结果\n"
                f"━━━━━━━━━━\n"
                f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📁 扫描文件：{self._process_count} 个\n"
                f"🔗 已创建硬链接：{self._hardlink_count} 个\n"
                f"💾 已节省空间：{self._format_size(self._saved_space)}\n"
                f"━━━━━━━━━━\n"
                f"⚠️ 注意：本插件仍处于开发试验阶段，请注意数据安全"
            )
        
        self._send_notify_message(title, text)

    def _send_notify_message(self, title, text):
        """
        发送通知消息
        """
        try:
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=title,
                text=text
            )
        except Exception as e:
            logger.error(f"发送通知失败: {str(e)}")

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [
            {
                "cmd": "/hardlink_scan",
                "event": EventType.PluginAction,
                "desc": "智能硬链接扫描",
                "category": "",
                "data": {"action": "hardlink_scan"},
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/hardlink_scan",
                "endpoint": self.api_scan,
                "methods": ["GET"],
                "summary": "智能硬链接扫描",
                "description": "扫描目录并处理重复文件",
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
        if self._enabled and self._cron:
            return [
                {
                    "id": "SmartHardLink",
                    "name": "智能硬链接定时扫描服务",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.scan_and_process,
                    "kwargs": {},
                }
            ]
        return []

    def api_scan(self) -> schemas.Response:
        """
        API调用扫描处理
        """
        self.scan_and_process()
        return schemas.Response(success=True, data={
            "processed": self._process_count,
            "hardlinked": self._hardlink_count,
            "saved_space": self._saved_space,
            "saved_space_formatted": self._format_size(self._saved_space)
        })

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                },
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "warning",
                                            "variant": "tonal",
                                            "text": "⚠️ 免责声明：本插件仍处于开发试验阶段，不排除与其他监控类、硬链接类插件冲突，使用前请务必考虑好数据安全，如有损失，本插件概不负责。强烈建议先在不重要的目录进行测试。",
                                            "class": "mb-4",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "立即运行一次",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "dry_run",
                                            "label": "试运行模式",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VCronField",
                                        "props": {
                                            "model": "cron",
                                            "label": "定时扫描周期",
                                            "placeholder": "5位cron表达式，留空关闭",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "min_size",
                                            "label": "最小文件大小（KB）",
                                            "placeholder": "1024",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "scan_dirs",
                                            "label": "扫描目录",
                                            "rows": 5,
                                            "placeholder": "每行一个目录路径",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "exclude_dirs",
                                            "label": "排除目录",
                                            "rows": 3,
                                            "placeholder": "每行一个目录路径",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "exclude_extensions",
                                            "label": "排除文件类型",
                                            "placeholder": "jpg,png,gif",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "hash_buffer_size",
                                            "label": "哈希缓冲区大小（字节）",
                                            "placeholder": "65536",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                },
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "exclude_keywords",
                                            "label": "排除关键词",
                                            "rows": 2,
                                            "placeholder": "每行一个关键词",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                },
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "试运行模式：仅检测重复文件，不实际创建硬链接。建议首次使用开启此选项，确认无误后再关闭。\n硬链接要求源文件和目标文件必须在同一个文件系统/分区上，否则会创建失败。\n注意：硬链接过程会保持文件名不变，以防止做种报错。",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "dry_run": True,
            "cron": "",
            "scan_dirs": "",
            "min_size": 1024,
            "exclude_dirs": "",
            "exclude_extensions": "",
            "exclude_keywords": "",
            "hash_buffer_size": 65536,
        }

    def get_page(self) -> List[dict]:
        pass

    def stop_service(self):
        """
        退出插件
        """
        if self._scheduler:
            self._scheduler.remove_all_jobs()
            if self._scheduler.running:
                self._event.set()
                self._scheduler.shutdown()
                self._event.clear()
            self._scheduler = None 