import re
import time
import requests
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.plugins import _PluginBase
from typing import Any, List, Dict, Tuple, Optional
from app.log import logger
from app.schemas import NotificationType
from app.utils.http import RequestUtils


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

    # 站点URL
    _base_url = "https://club.fnnas.com"
    _sign_url = f"{_base_url}/plugin.php?id=zqlj_sign"
    _credit_url = f"{_base_url}/home.php?mod=spacecp&ac=credit&showcredit=1"

    # 私有属性
    _enabled = False
    _cookie = None
    _notify = False
    _onlyonce = False
    _cron = None
    _history_days = 30
    _scheduler = None

    def __init__(self):
        """
        初始化插件
        """
        try:
            logger.info("============= FnosSign插件初始化开始 =============")
            super().__init__()
            logger.info("FnosSign插件基类初始化完成")
            logger.info("============= FnosSign插件初始化完成 =============")
        except Exception as e:
            logger.error(f"============= FnosSign插件初始化异常: {str(e)} =============")

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        try:
            logger.info("============= FnosSign init_plugin 开始 =============")
            # 停止现有任务
            self.stop_service()

            if config:
                logger.info(f"收到配置: {config}")
                self._enabled = config.get("enabled")
                self._cron = config.get("cron")
                self._cookie = config.get("cookie")
                self._notify = config.get("notify")
                self._onlyonce = config.get("onlyonce")
                self._history_days = config.get("history_days", 30)
                logger.info(f"加载配置完成: enabled={self._enabled}, notify={self._notify}, onlyonce={self._onlyonce}, cron={self._cron}")
            else:
                logger.info("未收到配置，使用默认值")

            # 无论是否启用，都记录一条日志
            logger.info(f"插件初始化完成，enabled={self._enabled}, cron={self._cron}")

            if self._onlyonce:
                # 定时服务
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                logger.info(f"飞牛论坛签到服务启动，立即运行一次")
                self._scheduler.add_job(func=self.__signin, trigger='date',
                                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                    name="飞牛论坛签到")
                # 关闭一次性开关
                self._onlyonce = False
                self.update_config({
                    "onlyonce": False,
                    "cron": self._cron,
                    "enabled": self._enabled,
                    "cookie": self._cookie,
                    "notify": self._notify,
                    "history_days": self._history_days,
                })

                # 启动任务
                if self._scheduler.get_jobs():
                    self._scheduler.print_jobs()
                    self._scheduler.start()
                    logger.info("一次性任务调度器已启动")
                else:
                    logger.warning("没有任务被添加到调度器")
            logger.info("============= FnosSign init_plugin 完成 =============")
        except Exception as e:
            logger.error(f"============= FnosSign init_plugin 异常: {str(e)} =============", exc_info=True)

    def __signin(self):
        """
        执行签到
        """
        try:
            # 访问首页获取cookie
            headers = {
                "Cookie": self._cookie,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.95 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Connection": "keep-alive"
            }
            
            # 创建session以复用连接
            session = requests.Session()
            session.headers.update(headers)
            
            # 添加重试机制
            retry = requests.adapters.Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[500, 502, 503, 504]
            )
            adapter = requests.adapters.HTTPAdapter(max_retries=retry)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            
            # 第一步：访问签到页面
            logger.info("正在访问签到页面...")
            response = session.get(self._sign_url)
            response.raise_for_status()
            
            # 检查是否已签到
            if "今天已经签到" in response.text:
                logger.info("今日已签到")
                
                # 获取积分信息
                logger.info("正在获取积分信息...")
                response = session.get(self._credit_url)
                response.raise_for_status()
                credit_info = self.get_credit_info(response.text)
                
                # 记录已签到状态
                sign_dict = {
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": "已签到",
                    "fnb": credit_info.get("fnb", 0),
                    "nz": credit_info.get("nz", 0),
                    "credit": credit_info.get("credit", 0),
                    "login_days": credit_info.get("login_days", 0)
                }
                
                # 保存签到记录
                history = self.get_data('sign_history') or []
                history.append(sign_dict)
                self.save_data(key="sign_history", value=history)
                
                # 发送通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【飞牛论坛签到】",
                        text=f"今日已签到\n"
                             f"飞牛币: {credit_info.get('fnb', 0)} 💎\n"
                             f"牛值: {credit_info.get('nz', 0)} 🔥\n"
                             f"积分: {credit_info.get('credit', 0)} ✨\n"
                             f"登录天数: {credit_info.get('login_days', 0)} 📆")
                
                # 清理旧记录
                thirty_days_ago = time.time() - int(self._history_days) * 24 * 60 * 60
                history = [record for record in history if
                          datetime.strptime(record["date"], '%Y-%m-%d %H:%M:%S').timestamp() >= thirty_days_ago]
                self.save_data(key="sign_history", value=history)
                return
            
            # 第二步：进行签到 - 直接访问包含sign参数的URL
            logger.info("正在执行签到...")
            sign_url = f"{self._sign_url}&sign=1"  # 根据请求格式直接添加sign=1参数
            response = session.get(sign_url)
            response.raise_for_status()
            
            # 判断签到结果
            if "签到成功" in response.text or "已经签到" in response.text:
                logger.info("签到成功")
                
                # 获取积分信息
                logger.info("正在获取积分信息...")
                response = session.get(self._credit_url)
                response.raise_for_status()
                credit_info = self.get_credit_info(response.text)
                
                # 记录签到记录
                sign_dict = {
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": "签到成功",
                    "fnb": credit_info.get("fnb", 0),
                    "nz": credit_info.get("nz", 0),
                    "credit": credit_info.get("credit", 0),
                    "login_days": credit_info.get("login_days", 0)
                }
                
                # 保存签到记录
                history = self.get_data('sign_history') or []
                history.append(sign_dict)
                self.save_data(key="sign_history", value=history)
                
                # 发送通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【飞牛论坛签到成功】",
                        text=f"飞牛币: {credit_info.get('fnb', 0)} 💎\n"
                             f"牛值: {credit_info.get('nz', 0)} 🔥\n"
                             f"积分: {credit_info.get('credit', 0)} ✨\n"
                             f"登录天数: {credit_info.get('login_days', 0)} 📆")
                
                # 清理旧记录
                thirty_days_ago = time.time() - int(self._history_days) * 24 * 60 * 60
                history = [record for record in history if
                          datetime.strptime(record["date"], '%Y-%m-%d %H:%M:%S').timestamp() >= thirty_days_ago]
                self.save_data(key="sign_history", value=history)
            else:
                logger.error(f"签到失败，响应内容: {response.text[:200]}")
                
                # 记录签到失败
                sign_dict = {
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": "签到失败"
                }
                
                # 保存签到记录
                history = self.get_data('sign_history') or []
                history.append(sign_dict)
                self.save_data(key="sign_history", value=history)
                
                # 发送通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【飞牛论坛签到失败】",
                        text="请检查Cookie是否有效")
        except Exception as e:
            logger.error(f"签到异常: {str(e)}")
            # 记录签到异常
            try:
                sign_dict = {
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": f"签到异常: {str(e)}"
                }
                history = self.get_data('sign_history') or []
                history.append(sign_dict)
                self.save_data(key="sign_history", value=history)
                
                # 发送异常通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【飞牛论坛签到异常】",
                        text=f"签到过程发生异常: {str(e)}")
            except Exception as e2:
                logger.error(f"记录异常签到状态时发生错误: {str(e2)}")

    def get_credit_info(self, html_content):
        """
        从积分页面解析积分信息
        """
        try:
            credit_info = {}
            
            # 解析飞牛币
            fnb_match = re.search(r'飞牛币</em>.*?(\d+)', html_content, re.DOTALL)
            if fnb_match:
                credit_info["fnb"] = fnb_match.group(1)
            
            # 解析牛值
            nz_match = re.search(r'牛值</em>.*?(\d+)', html_content, re.DOTALL)
            if nz_match:
                credit_info["nz"] = nz_match.group(1)
            
            # 解析积分
            credit_match = re.search(r'积分: (\d+)', html_content)
            if credit_match:
                credit_info["credit"] = credit_match.group(1)
            
            # 解析连续登录天数
            login_days_match = re.search(r'连续登录(\d+)天', html_content)
            if login_days_match:
                credit_info["login_days"] = login_days_match.group(1)
            
            return credit_info
        except Exception as e:
            logger.error(f"解析积分信息异常: {str(e)}")
            return {}

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        logger.info(f"============= FnosSign get_state 被调用，当前状态为 {self._enabled} =============")
        return self._enabled

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
        logger.info(f"============= FnosSign get_service 被调用，enabled={self._enabled} =============")
        if self._enabled and self._cron:
            logger.info("返回签到服务配置")
            return [{
                "id": "FnosSign",
                "name": "飞牛论坛签到",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.__signin,
                "kwargs": {}
            }]
        logger.info("未启用服务，返回空")
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
                                    'md': 3
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
                                    'md': 3
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
                                    'md': 3
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
                                            'label': '站点Cookie',
                                            'placeholder': '请输入站点Cookie值'
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '签到周期',
                                            'placeholder': '0 8 * * *'
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
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'history_days',
                                            'label': '历史保留天数',
                                            'placeholder': '30'
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
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '请填写有效的Cookie信息，签到周期使用Cron表达式，默认为：每天8点执行一次。'
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
            "notify": True,
            "onlyonce": False,
            "cookie": "",
            "cron": "0 8 * * *",
            "history_days": 30
        }

    def get_page(self) -> List[dict]:
        # 查询签到历史
        historys = self.get_data('sign_history')
        if not historys:
            logger.error("历史记录为空，无法显示任何信息。")
            return [
                {
                    'component': 'div',
                    'text': '暂无签到记录',
                    'props': {
                        'class': 'text-center',
                    }
                }
            ]

        if not isinstance(historys, list):
            logger.error(f"历史记录格式不正确，类型为: {type(historys)}")
            return [
                {
                    'component': 'div',
                    'text': '数据格式错误，请检查日志以获取更多信息。',
                    'props': {
                        'class': 'text-center',
                    }
                }
            ]

        # 按照签到时间倒序
        historys = sorted(historys, key=lambda x: x.get("date") or 0, reverse=True)

        # 签到消息
        sign_msgs = [
            {
                'component': 'tr',
                'props': {
                    'class': 'text-sm'
                },
                'content': [
                    {
                        'component': 'td',
                        'props': {
                            'class': 'whitespace-nowrap break-keep text-high-emphasis'
                        },
                        'text': history.get("date")
                    },
                    {
                        'component': 'td',
                        'text': history.get("status")
                    },
                    {
                        'component': 'td',
                        'text': f"{history.get('fnb', 0)} 💎"
                    },
                    {
                        'component': 'td',
                        'text': f"{history.get('nz', 0)} 🔥"
                    },
                    {
                        'component': 'td',
                        'text': f"{history.get('credit', 0)} ✨"
                    },
                    {
                        'component': 'td',
                        'text': f"{history.get('login_days', 0)} 📆"
                    }
                ]
            } for history in historys
        ]

        # 拼装页面
        return [
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {
                            'cols': 12,
                        },
                        'content': [
                            {
                                'component': 'VTable',
                                'props': {
                                    'hover': True
                                },
                                'content': [
                                    {
                                        'component': 'thead',
                                        'content': [
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '时间'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '状态'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '飞牛币'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '牛值'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '积分'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '登录天数'
                                            }
                                        ]
                                    },
                                    {
                                        'component': 'tbody',
                                        'content': sign_msgs
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
        退出插件
        """
        try:
            logger.info("============= FnosSign stop_service 开始 =============")
            if self._scheduler:
                logger.info("正在停止调度器...")
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
                logger.info("调度器已停止")
            logger.info("============= FnosSign stop_service 完成 =============")
            return True
        except Exception as e:
            logger.error(f"============= FnosSign stop_service 异常: {str(e)} =============")
            return False

    def get_command(self) -> List[Dict[str, Any]]:
        """
        注册命令
        """
        logger.info("============= FnosSign get_command 被调用 =============")
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册API
        """
        logger.info("============= FnosSign get_api 被调用 =============")
        return []