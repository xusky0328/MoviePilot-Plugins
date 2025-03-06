"""
飞牛论坛签到插件
"""
from typing import Any, List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import time
import threading
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from app.core.event import EventManager, EventType
from app.plugins import _PluginBase
from app.schemas.types import NotificationType, MessageChannel
from app.core.config import settings
from app.log import logger
from app.utils.http import RequestUtils
from app.core.event import eventmanager
import re
import json
import os
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import requests
from app.core.plugin import Plugin
from app.core.pluginmanager import PluginManager
from app.helper.notification import NotificationHelper
from app.schemas import NotificationConf
from app.utils.time import TimeUtils

class FnosSign(Plugin):
    # 插件名称
    plugin_name = "飞牛论坛签到"
    # 插件描述
    plugin_desc = "自动完成飞牛论坛每日签到"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/madrays/MoviePilot-Plugins/main/icons/fnos.ico"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "madrays"
    # 作者主页
    author_url = "https://github.com/madrays"
    # 插件配置项ID前缀
    plugin_config_prefix = "fnossign_"
    # 加载顺序
    plugin_order = 1
    # 可使用的用户级别
    auth_level = 2

    # 站点URL
    _base_url = "https://club.fnnas.com"
    _sign_url = f"{_base_url}/plugin.php?id=dsu_paulsign:sign"
    _credit_url = f"{_base_url}/home.php?mod=spacecp&ac=credit&op=base"

    # 重试配置
    _retry_times = 3
    _retry_backoff_factor = 1
    _retry_status_forcelist = [403, 404, 500, 502, 503, 504]

    @staticmethod
    def get_plugin_name() -> str:
        """
        获取插件名称
        """
        return "fnos_sign"

    def __init__(self):
        """
        初始化插件
        """
        super().__init__()
        # 插件配置
        self._enabled = False
        self._cookie = None
        self._notify = False
        self._onlyonce = False
        self._scheduler = None
        self._lock = threading.Lock()
        self._version = None
        self._history_file = os.path.join(settings.PLUGIN_DATA_PATH, "fnos_sign_history.json")
        self._history = []
        self._stats = {
            "total_signs": 0,
            "success_signs": 0,
            "failed_signs": 0,
            "last_sign_time": None,
            "continuous_days": 0
        }

        # 设置日志
        self._logger = logging.getLogger(self.plugin_name)
        self._logger.setLevel(logging.INFO)
        # 创建日志目录
        log_dir = os.path.join(settings.PLUGIN_DATA_PATH, "logs")
        os.makedirs(log_dir, exist_ok=True)
        # 创建文件处理器
        log_file = os.path.join(log_dir, "fnos_sign.log")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        # 创建格式化器
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        # 添加处理器
        self._logger.addHandler(file_handler)
        self._logger.addHandler(console_handler)

        # 初始化通知服务
        if hasattr(settings, 'VERSION_FLAG'):
            self._version = settings.VERSION_FLAG  # V2
            self._logger.info("飞牛论坛签到插件运行在 V2 版本")
        else:
            self._version = "v1"  # V1
            self._logger.info("飞牛论坛签到插件运行在 V1 版本")

    def __update_config(self):
        """
        更新配置
        """
        try:
            self.update_config({
                "enabled": self._enabled,
                "cookie": self._cookie,
                "notify": self._notify,
                "onlyonce": self._onlyonce,
                "last_sign_time": self._config.get("last_sign_time")
            })
            self._logger.debug("配置更新成功")
        except Exception as e:
            self._logger.error(f"配置更新失败: {str(e)}")

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        try:
            # 停止现有任务
            self.stop_service()

            if config:
                self._config = config
                self._enabled = config.get("enabled")
                self._cookie = config.get("cookie")
                self._notify = config.get("notify")
                self._onlyonce = config.get("onlyonce")
            
            # 确保历史记录文件存在
            os.makedirs(os.path.dirname(self._history_file), exist_ok=True)
            if not os.path.exists(self._history_file):
                self._save_history([])

            # V2版本特定功能初始化
            if self._version == "v2":
                # 注册模块重载事件监听
                eventmanager.register(EventType.ModuleReload)(self.module_reload)
                self._logger.info("飞牛论坛签到插件 V2 版本特定功能初始化完成")

            if self._onlyonce:
                # 定时服务
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                self._logger.info("飞牛论坛签到服务启动，立即运行一次")
                self._scheduler.add_job(func=self.sign, trigger='date',
                                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                    name="飞牛论坛签到")
                
                # 关闭一次性开关
                self._onlyonce = False
                self.__update_config()

                # 启动任务
                if self._scheduler.get_jobs():
                    self._scheduler.print_jobs()
                    self._scheduler.start()

            self._logger.info("飞牛论坛签到插件初始化完成")
        except Exception as e:
            self._logger.error(f"飞牛论坛签到插件初始化失败: {str(e)}")
            self._enabled = False

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled

    def get_command(self) -> List[Dict[str, Any]]:
        """
        注册插件命令
        """
        return [{
            "cmd": "/fnos_sign",
            "event": EventType.PluginAction,
            "desc": "飞牛论坛签到",
            "category": "签到",
            "data": {
                "action": "fnos_sign"
            }
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件API
        """
        return [
            {
                "path": "/sign",
                "endpoint": self.sign,
                "methods": ["GET"],
                "summary": "飞牛论坛签到",
                "description": "执行飞牛论坛每日签到"
            },
            {
                "path": "/history",
                "endpoint": self.get_history,
                "methods": ["GET"],
                "summary": "获取签到历史",
                "description": "获取历史签到记录"
            },
            {
                "path": "/stats",
                "endpoint": self.get_stats,
                "methods": ["GET"],
                "summary": "获取签到统计",
                "description": "获取签到统计数据"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件服务
        """
        if self._enabled:
            return [{
                "id": "fnos_sign",
                "name": "飞牛论坛自动签到",
                "trigger": CronTrigger.from_crontab("0 0 * * *"),  # 每天0点执行
                "func": self.sign,
                "kwargs": {}
            }]
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cookie',
                                            'label': 'Cookie',
                                            'placeholder': '请输入飞牛论坛Cookie',
                                            'hint': '请确保Cookie有效，否则可能导致签到失败'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '签到通知',
                                            'hint': '开启后将在签到完成后发送通知'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                            'hint': '开启后将在每天0点自动签到'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                            'hint': '开启后将在保存配置后立即执行一次签到'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "cookie": "",
            "notify": False,
            "onlyonce": False
        }

    def get_page(self) -> List[dict]:
        """
        拼装插件详情页面，需要返回页面配置，同时为数据请求提供接口
        """
        try:
            # 获取统计数据
            stats = self.get_stats()
            # 获取历史记录
            history = self.get_history()
            
            return [
                {
                    'component': 'VRow',
                    'content': [
                        {
                            'component': 'VCol',
                            'props': {
                                'cols': 12,
                                'md': 6
                            },
                            'content': [
                                {
                                    'component': 'VCard',
                                    'props': {
                                        'title': '签到状态'
                                    },
                                    'content': [
                                        {
                                            'component': 'VCardText',
                                            'props': {
                                                'class': 'text-center'
                                            },
                                            'content': [
                                                {
                                                    'component': 'VIcon',
                                                    'props': {
                                                        'icon': 'mdi-check-circle' if stats.get('last_sign_status') == 'success' else 'mdi-close-circle',
                                                        'color': 'success' if stats.get('last_sign_status') == 'success' else 'error',
                                                        'size': 48
                                                    }
                                                },
                                                {
                                                    'component': 'div',
                                                    'props': {
                                                        'class': 'text-h6 mt-2'
                                                    },
                                                    'text': '今日已签到' if stats.get('last_sign_status') == 'success' else '今日未签到'
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            'component': 'VCol',
                            'props': {
                                'cols': 12,
                                'md': 6
                            },
                            'content': [
                                {
                                    'component': 'VCard',
                                    'props': {
                                        'title': '签到统计'
                                    },
                                    'content': [
                                        {
                                            'component': 'VCardText',
                                            'content': [
                                                {
                                                    'component': 'VRow',
                                                    'content': [
                                                        {
                                                            'component': 'VCol',
                                                            'props': {
                                                                'cols': 6
                                                            },
                                                            'content': [
                                                                {
                                                                    'component': 'div',
                                                                    'props': {
                                                                        'class': 'text-subtitle-2'
                                                                    },
                                                                    'text': '总签到次数'
                                                                },
                                                                {
                                                                    'component': 'div',
                                                                    'props': {
                                                                        'class': 'text-h6'
                                                                    },
                                                                    'text': str(stats.get('total_signs', 0))
                                                                }
                                                            ]
                                                        },
                                                        {
                                                            'component': 'VCol',
                                                            'props': {
                                                                'cols': 6
                                                            },
                                                            'content': [
                                                                {
                                                                    'component': 'div',
                                                                    'props': {
                                                                        'class': 'text-subtitle-2'
                                                                    },
                                                                    'text': '连续签到天数'
                                                                },
                                                                {
                                                                    'component': 'div',
                                                                    'props': {
                                                                        'class': 'text-h6'
                                                                    },
                                                                    'text': str(stats.get('continuous_days', 0))
                                                                }
                                                            ]
                                                        }
                                                    ]
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    'component': 'VCard',
                    'props': {
                        'title': '签到历史'
                    },
                    'content': [
                        {
                            'component': 'VDataTable',
                            'props': {
                                'headers': [
                                    {'text': '时间', 'value': 'time'},
                                    {'text': '状态', 'value': 'status'},
                                    {'text': '飞牛币', 'value': 'fnb'},
                                    {'text': '牛值', 'value': 'nz'},
                                    {'text': '积分', 'value': 'credit'}
                                ],
                                'items': history,
                                'items-per-page': 10,
                                'sort-by': ['time'],
                                'sort-desc': True
                            }
                        }
                    ]
                }
            ]
        except Exception as e:
            self._logger.error(f"生成页面失败: {str(e)}")
            return [
                {
                    'component': 'div',
                    'text': '页面生成失败，请检查日志以获取更多信息。',
                    'props': {
                        'class': 'text-center',
                    }
                }
            ]

    def stop_service(self):
        """
        停止插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
            self._logger.info("飞牛论坛签到插件已停止")
        except Exception as e:
            self._logger.error(f"停止插件失败: {str(e)}")

    def get_credit_info(self, html_content: str) -> Dict[str, Any]:
        """
        从页面内容中提取积分信息
        """
        try:
            # 提取飞牛币
            fnb_match = re.search(r'飞牛币</a>.*?(\d+)</td>', html_content, re.DOTALL)
            fnb = int(fnb_match.group(1)) if fnb_match else 0

            # 提取牛值
            nz_match = re.search(r'牛值</a>.*?(\d+)</td>', html_content, re.DOTALL)
            nz = int(nz_match.group(1)) if nz_match else 0

            # 提取积分
            credit_match = re.search(r'积分</a>.*?(\d+)</td>', html_content, re.DOTALL)
            credit = int(credit_match.group(1)) if credit_match else 0

            # 提取登录天数
            login_days_match = re.search(r'登录天数</a>.*?(\d+)</td>', html_content, re.DOTALL)
            login_days = int(login_days_match.group(1)) if login_days_match else 0

            return {
                "fnb": fnb,
                "nz": nz,
                "credit": credit,
                "login_days": login_days
            }
        except Exception as e:
            self._logger.error(f"提取积分信息失败: {str(e)}")
            return {
                "fnb": 0,
                "nz": 0,
                "credit": 0,
                "login_days": 0
            }

    def sign(self):
        """
        执行签到
        """
        if not self._enabled:
            self._logger.warning("飞牛论坛签到插件未启用")
            return

        if not self._cookie:
            self._logger.error("未配置Cookie，无法签到")
            return

        if not self._lock.acquire(blocking=False):
            self._logger.warning("已有签到任务正在运行")
            return

        try:
            # 配置请求头
            headers = {
                "Cookie": self._cookie,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": self._base_url,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
            }

            # 配置重试策略
            retry = Retry(
                total=self._retry_times,
                backoff_factor=self._retry_backoff_factor,
                status_forcelist=self._retry_status_forcelist
            )
            adapter = HTTPAdapter(max_retries=retry)
            session = requests.Session()
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            # 访问签到页面
            self._logger.info("正在访问签到页面...")
            response = session.get(self._sign_url, headers=headers)
            response.raise_for_status()

            # 发送签到请求
            self._logger.info("正在发送签到请求...")
            response = session.post(self._sign_url, headers=headers)
            response.raise_for_status()

            # 获取积分信息
            self._logger.info("正在获取积分信息...")
            response = session.get(self._credit_url, headers=headers)
            response.raise_for_status()
            credit_info = self.get_credit_info(response.text)

            # 更新配置
            self._config["last_sign_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.__update_config()

            # 记录签到历史
            history_item = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "success",
                "fnb": credit_info["fnb"],
                "nz": credit_info["nz"],
                "credit": credit_info["credit"]
            }
            self._history.append(history_item)
            self._save_history(self._history)

            # 更新统计
            self._stats["total_signs"] += 1
            self._stats["success_signs"] += 1
            self._stats["last_sign_time"] = datetime.now()
            self._stats["last_sign_status"] = "success"

            # 计算连续签到天数
            if len(self._history) > 1:
                last_sign = datetime.strptime(self._history[-2]["time"], "%Y-%m-%d %H:%M:%S")
                current_sign = datetime.strptime(history_item["time"], "%Y-%m-%d %H:%M:%S")
                if (current_sign - last_sign).days == 1:
                    self._stats["continuous_days"] += 1
                else:
                    self._stats["continuous_days"] = 1
            else:
                self._stats["continuous_days"] = 1

            # 发送通知
            if self._notify:
                self.send_notify(
                    title="【飞牛论坛签到成功】",
                    text=f"飞牛币: {credit_info['fnb']} | 牛值: {credit_info['nz']} | 登录天数: {credit_info['login_days']} | 积分: {credit_info['credit']}"
                )

            self._logger.info("签到成功")
        except Exception as e:
            self._logger.error(f"签到失败: {str(e)}")
            # 更新统计
            self._stats["total_signs"] += 1
            self._stats["failed_signs"] += 1
            self._stats["last_sign_status"] = "failed"
            # 记录失败历史
            history_item = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "failed",
                "fnb": 0,
                "nz": 0,
                "credit": 0
            }
            self._history.append(history_item)
            self._save_history(self._history)
        finally:
            self._lock.release()

    def get_history(self) -> List[Dict[str, Any]]:
        """
        获取签到历史
        """
        try:
            if not os.path.exists(self._history_file):
                return []
            with open(self._history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            return history
        except Exception as e:
            self._logger.error(f"获取签到历史失败: {str(e)}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """
        获取签到统计
        """
        try:
            # 计算连续签到天数
            if len(self._history) > 1:
                last_sign = datetime.strptime(self._history[-2]["time"], "%Y-%m-%d %H:%M:%S")
                current_sign = datetime.strptime(self._history[-1]["time"], "%Y-%m-%d %H:%M:%S")
                if (current_sign - last_sign).days == 1:
                    self._stats["continuous_days"] += 1
                else:
                    self._stats["continuous_days"] = 1
            else:
                self._stats["continuous_days"] = 1

            return self._stats
        except Exception as e:
            self._logger.error(f"获取签到统计失败: {str(e)}")
            return {
                "total_signs": 0,
                "success_signs": 0,
                "failed_signs": 0,
                "last_sign_time": None,
                "last_sign_status": "unknown",
                "continuous_days": 0
            }

    def _save_history(self, history: List[Dict[str, Any]]):
        """
        保存签到历史
        """
        try:
            # 确保历史记录是列表
            if not isinstance(history, list):
                history = []
            # 只保留最近30天的记录
            history = history[-30:]
            with open(self._history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._logger.error(f"保存签到历史失败: {str(e)}")

    def _load_history(self):
        """
        加载签到历史
        """
        try:
            if os.path.exists(self._history_file):
                with open(self._history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    if isinstance(history, list):
                        self._history = history
                    else:
                        self._history = []
            else:
                self._history = []
        except Exception as e:
            self._logger.error(f"加载签到历史失败: {str(e)}")
            self._history = []

    def send_notify(self, title: str, text: str = None):
        """
        发送通知
        """
        if not self._notify:
            return
        self.post_message(
            mtype=NotificationType.Plugin,
            title=title,
            text=text,
            channel=MessageChannel.System
        )

    @eventmanager.register(EventType.ModuleReload)
    def module_reload(self, event: Event):
        """
        模块重载事件处理
        """
        self._logger.info("收到模块重载事件")
        self.init_plugin(self._config)

    def sign(self, username: str, password: str) -> bool:
        """
        执行签到
        """
        try:
            # 登录
            login_url = "https://www.fnw.cc/member.php?mod=logging&action=login&loginsubmit=yes&infloat=yes&lssubmit=yes&inajax=1"
            login_data = {
                "username": username,
                "password": password,
                "quickforward": "yes",
                "handlekey": "ls"
            }
            login_res = RequestUtils().post(login_url, data=login_data)
            if not login_res or "succeedmessage" not in login_res.text:
                self._logger.error("登录失败")
                return False

            # 签到
            sign_url = "https://www.fnw.cc/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1&sign_as=1&inajax=1"
            sign_res = RequestUtils().get(sign_url)
            if not sign_res or "今日已经签到" not in sign_res.text:
                self._logger.error("签到失败")
                return False

            # 获取积分信息
            credit_info = self.get_credit_info()
            if credit_info:
                self._logger.info(f"签到成功，当前积分：{credit_info}")
                # 发送通知
                if self._version == "v2":
                    self._notification.send(
                        title="飞牛论坛签到",
                        text=f"签到成功，当前积分：{credit_info}",
                        mtype=NotificationType.Plugin
                    )
                else:
                    self._notification.send(
                        title="飞牛论坛签到",
                        text=f"签到成功，当前积分：{credit_info}"
                    )
            return True
        except Exception as e:
            self._logger.error(f"签到异常: {str(e)}")
            return False

    def get_credit_info(self) -> str:
        """
        获取积分信息
        """
        try:
            credit_url = "https://www.fnw.cc/home.php?mod=spacecp&ac=credit&op=base"
            credit_res = RequestUtils().get(credit_url)
            if not credit_res:
                return None

            # 使用正则表达式匹配积分信息
            credit_pattern = r'积分:\s*(\d+)'
            credit_match = re.search(credit_pattern, credit_res.text)
            if credit_match:
                return credit_match.group(1)
            return None
        except Exception as e:
            self._logger.error(f"获取积分信息失败: {str(e)}")
            return None 