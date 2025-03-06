from typing import Any, List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import requests
import time
from app.core.event import EventManager, EventType
from app.core.plugin import Plugin, PluginManager
from app.schemas.types import NotificationType, MessageChannel
from app.core.config import settings
import re
import json
import os

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

    def __init__(self):
        super().__init__()
        self._enabled = False
        self._config = {}
        self._cookie = None
        self._sign_url = "https://club.fnnas.com/plugin.php?id=zqlj_sign"
        self._credit_url = "https://club.fnnas.com/home.php?mod=spacecp&ac=credit&showcredit=1"
        self._history_file = "plugins/fnos_sign/history.json"
        self._max_retries = 3
        self._retry_delay = 1  # 重试延迟（秒）

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        if config:
            self._config = config
        self._enabled = self._config.get("enabled", False)
        self._cookie = self._config.get("cookie", "")
        # 确保历史记录文件存在
        os.makedirs(os.path.dirname(self._history_file), exist_ok=True)
        if not os.path.exists(self._history_file):
            self._save_history([])

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
        # 获取配置的签到时间，默认为0点0分0秒
        sign_time = self._config.get("sign_time", "00:00:00")
        hour, minute, second = map(int, sign_time.split(":"))
        
        return [{
            "id": "fnos_sign",
            "name": "飞牛论坛自动签到",
            "trigger": "cron",
            "func": self.sign,
            "kwargs": {
                "hour": str(hour),
                "minute": str(minute),
                "second": str(second)
            }
        }]

    def get_form(self) -> Tuple[List[dict], str]:
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
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cookie',
                                            'label': '飞牛论坛Cookie',
                                            'type': 'password',
                                            'hint': '请填写飞牛论坛的Cookie'
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'sign_time',
                                            'label': '签到时间',
                                            'hint': '格式：HH:MM:SS，例如：00:00:00',
                                            'rules': [
                                                'v => /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$/.test(v) || "请输入正确的时间格式"'
                                            ]
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
            "sign_time": "00:00:00"
        }

    def get_page(self) -> List[dict]:
        """
        拼装插件详情页面，需要返回页面配置，同时附带数据
        """
        # 获取历史记录
        history = self._load_history()
        # 获取统计数据
        stats = self._calculate_stats(history)
        
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
                                            'text': '上次签到时间：' + (self._config.get("last_sign_time", "从未签到") or "从未签到")
                                        }
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
                                        'props': {
                                            'text': f'总签到次数：{stats["total_signs"]}\n连续签到天数：{stats["continuous_days"]}\n最长连续签到：{stats["max_continuous_days"]}天'
                                        }
                                    }
                                ]
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
                            'cols': 12
                        },
                        'content': [
                            {
                                'component': 'VCard',
                                'props': {
                                    'title': '签到历史'
                                },
                                'content': [
                                    {
                                        'component': 'VList',
                                        'props': {
                                            'items': [{
                                                'title': f"{record['date']} {record['time']}",
                                                'subtitle': f"飞牛币: {record['fnb']} | 牛值: {record['nz']} | 登录天数: {record['ts']} | 积分: {record['jf']}"
                                            } for record in history[-10:]]  # 只显示最近10条记录
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def stop_service(self):
        """
        停止插件
        """
        self._enabled = False

    def _load_history(self) -> List[dict]:
        """
        加载签到历史记录
        """
        try:
            if os.path.exists(self._history_file):
                with open(self._history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载历史记录失败: {str(e)}")
        return []

    def _save_history(self, history: List[dict]):
        """
        保存签到历史记录
        """
        try:
            with open(self._history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存历史记录失败: {str(e)}")

    def _calculate_stats(self, history: List[dict]) -> dict:
        """
        计算签到统计数据
        """
        stats = {
            "total_signs": len(history),
            "continuous_days": 0,
            "max_continuous_days": 0
        }
        
        if not history:
            return stats
            
        # 计算连续签到天数
        today = datetime.now().date()
        last_sign_date = datetime.strptime(history[-1]['date'], '%Y-%m-%d').date()
        if last_sign_date == today:
            stats["continuous_days"] = 1
        elif last_sign_date == today - timedelta(days=1):
            stats["continuous_days"] = 1
            
        # 计算最长连续签到天数
        max_continuous = 1
        current_continuous = 1
        for i in range(len(history)-1, 0, -1):
            current_date = datetime.strptime(history[i]['date'], '%Y-%m-%d').date()
            prev_date = datetime.strptime(history[i-1]['date'], '%Y-%m-%d').date()
            if (current_date - prev_date).days == 1:
                current_continuous += 1
                max_continuous = max(max_continuous, current_continuous)
            else:
                current_continuous = 1
                
        stats["max_continuous_days"] = max_continuous
        return stats

    def get_credit_info(self, headers: dict) -> dict:
        """
        获取积分信息
        """
        try:
            response = requests.get(self._credit_url, headers=headers)
            if response.status_code == 200:
                # 使用正则表达式提取积分信息
                content = response.text
                fnb = re.search(r'飞牛币:\s*(\d+)', content)
                nz = re.search(r'牛值:\s*(\d+)', content)
                ts = re.search(r'登录天数:\s*(\d+)', content)
                jf = re.search(r'积分:\s*(\d+)', content)
                
                return {
                    "fnb": fnb.group(1) if fnb else "0",
                    "nz": nz.group(1) if nz else "0",
                    "ts": ts.group(1) if ts else "0",
                    "jf": jf.group(1) if jf else "0"
                }
        except Exception as e:
            print(f"获取积分信息失败: {str(e)}")
        return {"fnb": "0", "nz": "0", "ts": "0", "jf": "0"}

    def sign(self):
        """
        执行签到
        """
        if not self._cookie:
            return {"code": 1, "msg": "未配置Cookie"}
        
        # 重试机制
        for retry in range(self._max_retries):
            try:
                headers = {
                    "Cookie": self._cookie,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.95 Safari/537.36",
                    "Referer": "https://club.fnnas.com/",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "zh-CN,zh;q=0.9"
                }
                
                # 1. 访问签到页面
                response = requests.get(self._sign_url, headers=headers)
                if response.status_code != 200:
                    if retry < self._max_retries - 1:
                        time.sleep(self._retry_delay)
                        continue
                    return {"code": 1, "msg": f"访问签到页面失败: {response.status_code}"}

                # 2. 发送签到请求
                sign_response = requests.get(f"{self._sign_url}&sign=1", headers=headers)
                if sign_response.status_code != 200:
                    if retry < self._max_retries - 1:
                        time.sleep(self._retry_delay)
                        continue
                    return {"code": 1, "msg": f"签到请求失败: {sign_response.status_code}"}

                # 3. 获取积分信息
                credit_info = self.get_credit_info(headers)
                
                # 4. 更新配置和发送通知
                self._config["last_sign_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.save_config(self._config)
                
                # 5. 记录签到历史
                history = self._load_history()
                history.append({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "time": datetime.now().strftime("%H:%M:%S"),
                    **credit_info
                })
                self._save_history(history)
                
                # 6. 发送通知
                notify_msg = f"飞牛币: {credit_info['fnb']} | 牛值: {credit_info['nz']} | 登录天数: {credit_info['ts']} | 积分: {credit_info['jf']}"
                self.send_notify("飞牛论坛签到成功", notify_msg)
                
                return {"code": 0, "msg": "签到成功", "data": credit_info}
                    
            except Exception as e:
                if retry < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                    continue
                return {"code": 1, "msg": f"签到异常: {str(e)}"}
                
        return {"code": 1, "msg": "签到失败，已达到最大重试次数"}

    def get_history(self):
        """
        获取签到历史记录
        """
        return {"code": 0, "data": self._load_history()}

    def get_stats(self):
        """
        获取签到统计数据
        """
        return {"code": 0, "data": self._calculate_stats(self._load_history())}

    @eventmanager.register(EventType.PluginAction)
    def handle_sign(self, event):
        """
        处理签到命令
        """
        if not event.event_data or event.event_data.get("action") != "fnos_sign":
            return
        self.sign() 