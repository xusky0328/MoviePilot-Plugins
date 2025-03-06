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

class FnosSign(_PluginBase):
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
        # 插件配置
        self._enabled = False
        self._cookie = None
        self._notify = False
        self._onlyonce = False
        self._scheduler = None
        self._lock = threading.Lock()
        self._version = "v1"
        self._history_file = os.path.join(settings.PLUGIN_DATA_PATH, "fnos_sign_history.json")
        self._history = []
        self._stats = {
            "total_signs": 0,
            "success_signs": 0,
            "failed_signs": 0,
            "last_sign_time": None
        }

        # 设置日志
        self.logger = logging.getLogger("fnos_sign")
        self.logger.setLevel(logging.INFO)
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
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

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
                logger.info("飞牛论坛签到插件 V2 版本特定功能初始化完成")

            if self._onlyonce:
                # 定时服务
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                logger.info("飞牛论坛签到服务启动，立即运行一次")
                self._scheduler.add_job(func=self.sign, trigger='date',
                                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                    name="飞牛论坛签到")
                
                # 关闭一次性开关
                self._onlyonce = False
                self.update_config({
                    "onlyonce": False,
                    "enabled": self._enabled,
                    "cookie": self._cookie,
                    "notify": self._notify
                })

                # 启动任务
                if self._scheduler.get_jobs():
                    self._scheduler.print_jobs()
                    self._scheduler.start()

            logger.info("飞牛论坛签到插件初始化完成")
        except Exception as e:
            logger.error(f"飞牛论坛签到插件初始化失败: {str(e)}")
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
                                    'md': 4
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
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '开启通知',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
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
                    }
                ]
            }
        ], {
            "enabled": False,
            "cookie": "",
            "notify": False,
            "onlyonce": False
        }

    def get_page(self) -> Tuple[str, str, str]:
        """
        拼装插件详情页面，需要返回页面标题、页面内容、页面脚本
        """
        # 获取签到历史
        history = self._load_history()
        # 获取签到统计
        stats = self._stats

        # 拼装页面
        template = """
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">签到状态</h3>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-12">
                                <div class="alert alert-info">
                                    <i class="fas fa-info-circle"></i>
                                    插件状态：<span class="badge badge-primary">%s</span>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-12">
                                <button class="btn btn-primary" onclick="sign()">
                                    <i class="fas fa-sign-in-alt"></i> 立即签到
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">签到统计</h3>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-12">
                                <table class="table table-bordered">
                                    <tr>
                                        <td>总签到次数</td>
                                        <td>%d</td>
                                    </tr>
                                    <tr>
                                        <td>成功次数</td>
                                        <td>%d</td>
                                    </tr>
                                    <tr>
                                        <td>失败次数</td>
                                        <td>%d</td>
                                    </tr>
                                    <tr>
                                        <td>最后签到时间</td>
                                        <td>%s</td>
                                    </tr>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">签到历史</h3>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-12">
                                <table class="table table-bordered">
                                    <thead>
                                        <tr>
                                            <th>时间</th>
                                            <th>状态</th>
                                            <th>积分</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        %s
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """ % (
            "已启用" if self._enabled else "未启用",
            stats.get("total_signs", 0),
            stats.get("success_signs", 0),
            stats.get("failed_signs", 0),
            stats.get("last_sign_time", "从未签到"),
            "".join([
                f"<tr><td>{item['time']}</td><td>{item['status']}</td><td>{item['points']}</td></tr>"
                for item in history
            ])
        )

        # 页面脚本
        script = """
        function sign() {
            $.ajax({
                url: '/api/v1/plugin/fnos_sign/sign',
                type: 'post',
                data: {},
                success: function(res) {
                    if (res.code === 0) {
                        $.toast.success('签到成功');
                        setTimeout(function() {
                            window.location.reload();
                        }, 1000);
                    } else {
                        $.toast.error(res.msg || '签到失败');
                    }
                }
            });
        }
        """
        return "飞牛论坛签到", template, script

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
            self._enabled = False
            logger.info("飞牛论坛签到插件已停止")
        except Exception as e:
            logger.error(f"停止飞牛论坛签到插件失败: {str(e)}")

    def _load_history(self) -> List[dict]:
        """
        加载签到历史记录
        """
        try:
            if os.path.exists(self._history_file):
                with open(self._history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载历史记录失败: {str(e)}")
        return []

    def _save_history(self, history: List[dict]):
        """
        保存签到历史记录
        """
        try:
            with open(self._history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存历史记录失败: {str(e)}")

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
            response = RequestUtils(headers=headers).get_res(self._credit_url)
            if response and response.status_code == 200:
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
            logger.error(f"获取积分信息失败: {str(e)}")
        return {"fnb": "0", "nz": "0", "ts": "0", "jf": "0"}

    def sign(self):
        """
        执行签到
        """
        if not self._cookie:
            return {"code": 1, "msg": "未配置Cookie"}
            
        if not self._lock.acquire(blocking=False):
            logger.warning("已有任务正在执行，本次调度跳过！")
            return {"code": 1, "msg": "已有任务正在执行"}
            
        try:
            self._running = True
            
            headers = {
                "Cookie": self._cookie,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.95 Safari/537.36",
                "Referer": "https://club.fnnas.com/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9"
            }
            
            # 1. 访问签到页面
            response = RequestUtils(headers=headers).get_res(self._sign_url)
            if not response or response.status_code != 200:
                return {"code": 1, "msg": f"访问签到页面失败: {response.status_code if response else '无响应'}"}

            # 2. 发送签到请求
            sign_response = RequestUtils(headers=headers).get_res(f"{self._sign_url}&sign=1")
            if not sign_response or sign_response.status_code != 200:
                return {"code": 1, "msg": f"签到请求失败: {sign_response.status_code if sign_response else '无响应'}"}

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
            if self._notify:
                notify_msg = f"飞牛币: {credit_info['fnb']} | 牛值: {credit_info['nz']} | 登录天数: {credit_info['ts']} | 积分: {credit_info['jf']}"
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【飞牛论坛签到成功】",
                    text=notify_msg
                )
            
            return {"code": 0, "msg": "签到成功", "data": credit_info}
                    
        except Exception as e:
            logger.error(f"签到异常: {str(e)}")
            return {"code": 1, "msg": f"签到异常: {str(e)}"}
        finally:
            self._running = False
            self._lock.release()
            logger.debug("任务执行完成，锁已释放")

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

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        """
        获取插件仪表盘元信息
        """
        return [{
            "key": "fnos_sign_dashboard",
            "name": "飞牛论坛签到统计"
        }]

    def get_dashboard(self, key: str, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        """
        获取插件仪表盘页面
        """
        if key != "fnos_sign_dashboard":
            return None
            
        # 获取历史记录和统计数据
        history = self._load_history()
        stats = self._calculate_stats(history)
        
        # 仪表板配置
        return {
            "cols": 12,
            "md": 6
        }, {
            "refresh": 300,  # 5分钟刷新一次
            "border": True,
            "title": "飞牛论坛签到统计"
        }, [
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
            }
        ] 

    @eventmanager.register(EventType.ModuleReload)
    def module_reload(self, event):
        """
        模块重载事件处理
        """
        if not event:
            return
        event_data = event.event_data or {}
        module_id = event_data.get("module_id")
        # 如果模块标识不存在，则说明所有模块均发生重载
        if not module_id:
            logger.info("检测到模块重载，重新初始化插件")
            self.init_plugin(self._config) 