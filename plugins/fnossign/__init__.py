import time
import requests
import re
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.plugins import _PluginBase
from typing import Any, List, Dict, Tuple, Optional
from app.log import logger
from app.schemas import NotificationType


class fnossign(_PluginBase):
    # 插件名称
    plugin_name = "飞牛论坛签到"
    # 插件描述
    plugin_desc = "自动完成飞牛论坛每日签到"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/madrays/MoviePilot-Plugins/main/icons/fnos.ico"
    # 插件版本
    plugin_version = "1.1"
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

    # 私有属性
    _enabled = False
    _cookie = None
    _notify = False
    _onlyonce = False
    _cron = None
    _scheduler = None
    _max_retries = 3  # 最大重试次数
    _retry_interval = 30  # 重试间隔(秒)
    _history_days = 30  # 历史保留天数

    def init_plugin(self, config: dict = None):
        logger.info("============= fnossign 初始化 =============")
        try:
            if config:
                self._enabled = config.get("enabled")
                self._cookie = config.get("cookie")
                self._notify = config.get("notify")
                self._cron = config.get("cron")
                self._onlyonce = config.get("onlyonce")
                self._max_retries = int(config.get("max_retries", 3))
                self._retry_interval = int(config.get("retry_interval", 30))
                self._history_days = int(config.get("history_days", 30))
                logger.info(f"配置: enabled={self._enabled}, notify={self._notify}, cron={self._cron}, max_retries={self._max_retries}")
            
            if self._onlyonce:
                logger.info("执行一次性签到")
                self._onlyonce = False
                self.update_config({
                    "onlyonce": False,
                    "enabled": self._enabled,
                    "cookie": self._cookie,
                    "notify": self._notify,
                    "cron": self._cron,
                    "max_retries": self._max_retries,
                    "retry_interval": self._retry_interval,
                    "history_days": self._history_days
                })
                self.sign()
        except Exception as e:
            logger.error(f"fnossign初始化错误: {str(e)}", exc_info=True)

    def sign(self, retry_count=0):
        """执行签到，支持失败重试"""
        logger.info("============= 开始签到 =============")
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
            sign_page_url = "https://club.fnnas.com/plugin.php?id=zqlj_sign"
            response = session.get(sign_page_url)
            response.raise_for_status()
            
            # 检查是否已签到
            if "今天已经签到" in response.text:
                logger.info("今日已签到")
                
                # 获取积分信息
                logger.info("正在获取积分信息...")
                credit_info = self._get_credit_info(session)
                
                # 记录已签到状态
                sign_dict = {
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": "已签到",
                    "fnb": credit_info.get("fnb", 0),
                    "nz": credit_info.get("nz", 0),
                    "credit": credit_info.get("jf", 0),
                    "login_days": credit_info.get("ts", 0)
                }
                
                # 保存签到记录
                self._save_sign_history(sign_dict)
                
                # 发送通知
                if self._notify:
                    self._send_sign_notification(sign_dict)
                
                return sign_dict
            
            # 第二步：进行签到 - 直接访问包含sign参数的URL
            logger.info("正在执行签到...")
            sign_url = f"{sign_page_url}&sign=1"  # 根据请求格式直接添加sign=1参数
            response = session.get(sign_url)
            response.raise_for_status()
            
            # 判断签到结果
            if "签到成功" in response.text or "已经签到" in response.text:
                logger.info("签到成功")
                
                # 获取积分信息
                logger.info("正在获取积分信息...")
                credit_info = self._get_credit_info(session)
                
                # 记录签到记录
                sign_dict = {
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": "签到成功",
                    "fnb": credit_info.get("fnb", 0),
                    "nz": credit_info.get("nz", 0),
                    "credit": credit_info.get("jf", 0),
                    "login_days": credit_info.get("ts", 0)
                }
                
                # 保存签到记录
                self._save_sign_history(sign_dict)
                
                # 发送通知
                if self._notify:
                    self._send_sign_notification(sign_dict)
                
                return sign_dict
            else:
                # 签到失败，尝试重试
                logger.error(f"签到请求发送成功，但结果异常: {response.text[:200]}")
                if retry_count < self._max_retries:
                    logger.info(f"将在{self._retry_interval}秒后进行第{retry_count+1}次重试...")
                    time.sleep(self._retry_interval)
                    return self.sign(retry_count + 1)
                else:
                    raise Exception("签到失败，已达最大重试次数")
                    
        except requests.RequestException as re:
            # 网络请求异常处理
            logger.error(f"网络请求异常: {str(re)}")
            if retry_count < self._max_retries:
                logger.info(f"将在{self._retry_interval}秒后进行第{retry_count+1}次重试...")
                time.sleep(self._retry_interval)
                return self.sign(retry_count + 1)
            else:
                raise Exception(f"网络请求异常: {str(re)}")
                
        except Exception as e:
            # 签到过程中的异常
            logger.error(f"签到过程异常: {str(e)}", exc_info=True)
            
            # 记录失败
            sign_dict = {
                "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                "status": f"签到失败: {str(e)}",
            }
            self._save_sign_history(sign_dict)
            
            # 发送失败通知
            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【飞牛论坛签到失败】",
                    text=f"签到过程发生异常: {str(e)}"
                )
                
            return sign_dict

    def _get_credit_info(self, session):
        """
        获取积分信息并解析
        """
        try:
            credit_url = "https://club.fnnas.com/home.php?mod=spacecp&ac=credit&showcredit=1"
            response = session.get(credit_url)
            response.raise_for_status()
            
            credit_info = {}
            
            # 解析飞牛币
            fnb_match = re.search(r'飞牛币</em>.*?(\d+)', response.text, re.DOTALL)
            if fnb_match:
                credit_info["fnb"] = int(fnb_match.group(1))
            
            # 解析牛值
            nz_match = re.search(r'牛值</em>.*?(\d+)', response.text, re.DOTALL)
            if nz_match:
                credit_info["nz"] = int(nz_match.group(1))
            
            # 解析积分
            credit_match = re.search(r'积分: (\d+)', response.text)
            if credit_match:
                credit_info["jf"] = int(credit_match.group(1))
            
            # 解析连续登录天数
            login_days_match = re.search(r'连续登录(\d+)天', response.text)
            if login_days_match:
                credit_info["ts"] = int(login_days_match.group(1))
                
            logger.info(f"获取到积分信息: 飞牛币={credit_info.get('fnb', 0)}, 牛值={credit_info.get('nz', 0)}, "
                       f"积分={credit_info.get('jf', 0)}, 登录天数={credit_info.get('ts', 0)}")
            
            return credit_info
        except Exception as e:
            logger.error(f"获取积分信息失败: {str(e)}")
            return {}

    def _save_sign_history(self, sign_data):
        """
        保存签到历史记录
        """
        # 读取现有历史
        history = self.get_data('sign_history') or []
        history.append(sign_data)
        
        # 清理旧记录
        retention_days = int(self._history_days)
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).timestamp()
        history = [record for record in history if
                  datetime.strptime(record["date"], '%Y-%m-%d %H:%M:%S').timestamp() >= cutoff_date]
        
        # 保存历史
        self.save_data(key="sign_history", value=history)

    def _send_sign_notification(self, sign_data):
        """
        发送美观的签到通知
        """
        if not self._notify:
            return
            
        status = sign_data.get("status", "未知")
        fnb = sign_data.get("fnb", "—")
        nz = sign_data.get("nz", "—")
        credit = sign_data.get("credit", "—")
        login_days = sign_data.get("login_days", "—")
        
        # 构建通知文本
        if status in ["签到成功", "已签到"]:
            title = "【飞牛论坛签到成功】"
            text = f"✅ 状态: {status}\n" \
                   f"💎 飞牛币: {fnb}\n" \
                   f"🔥 牛值: {nz}\n" \
                   f"✨ 积分: {credit}\n" \
                   f"📆 登录天数: {login_days}"
        else:
            title = "【飞牛论坛签到失败】"
            text = f"❌ 状态: {status}"
            
        # 发送通知
        self.post_message(
            mtype=NotificationType.SiteMessage,
            title=title,
            text=text
        )

    def get_state(self) -> bool:
        logger.info(f"fnossign状态: {self._enabled}")
        return self._enabled

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            logger.info(f"注册定时服务: {self._cron}")
            return [{
                "id": "fnossign",
                "name": "飞牛论坛签到",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.sign,
                "kwargs": {}
            }]
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
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
                                    'md': 4
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
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'max_retries',
                                            'label': '最大重试次数',
                                            'type': 'number',
                                            'placeholder': '3'
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'history_days',
                                            'label': '历史保留天数',
                                            'type': 'number',
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
                                            'text': '飞牛论坛签到插件，支持自动签到、失败重试和通知。'
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
            "max_retries": 3,
            "retry_interval": 30,
            "history_days": 30
        }

    def get_page(self) -> List[dict]:
        """
        构建插件详情页面，展示签到历史
        """
        # 获取签到历史
        historys = self.get_data('sign_history') or []
        
        # 如果没有历史记录
        if not historys:
            return [
                {
                    'component': 'VAlert',
                    'props': {
                        'type': 'info',
                        'variant': 'tonal',
                        'text': '暂无签到记录，请先配置Cookie并启用插件',
                        'class': 'mb-2'
                    }
                }
            ]
        
        # 按时间倒序排列历史
        historys = sorted(historys, key=lambda x: x.get("date", ""), reverse=True)
        
        # 构建历史记录表格行
        history_rows = []
        for history in historys:
            status_text = history.get("status", "未知")
            status_color = "success" if status_text in ["签到成功", "已签到"] else "error"
            
            history_rows.append({
                'component': 'tr',
                'content': [
                    # 日期列
                    {
                        'component': 'td',
                        'props': {
                            'class': 'text-caption'
                        },
                        'text': history.get("date", "")
                    },
                    # 状态列
                    {
                        'component': 'td',
                        'content': [
                            {
                                'component': 'VChip',
                                'props': {
                                    'color': status_color,
                                    'size': 'small',
                                    'variant': 'outlined'
                                },
                                'text': status_text
                            }
                        ]
                    },
                    # 飞牛币列
                    {
                        'component': 'td',
                        'text': f"{history.get('fnb', '—')} 💎" if "fnb" in history else "—"
                    },
                    # 牛值列
                    {
                        'component': 'td',
                        'text': f"{history.get('nz', '—')} 🔥" if "nz" in history else "—"
                    },
                    # 积分列
                    {
                        'component': 'td',
                        'text': f"{history.get('credit', '—')} ✨" if "credit" in history else "—"
                    },
                    # 登录天数列
                    {
                        'component': 'td',
                        'text': f"{history.get('login_days', '—')} 📆" if "login_days" in history else "—"
                    }
                ]
            })
        
        # 最终页面组装
        return [
            # 标题
            {
                'component': 'VCard',
                'props': {'variant': 'outlined', 'class': 'mb-4'},
                'content': [
                    {
                        'component': 'VCardTitle',
                        'props': {'class': 'text-h6'},
                        'text': '📊 飞牛论坛签到历史'
                    },
                    {
                        'component': 'VCardText',
                        'content': [
                            {
                                'component': 'VTable',
                                'props': {
                                    'hover': True,
                                    'density': 'compact'
                                },
                                'content': [
                                    # 表头
                                    {
                                        'component': 'thead',
                                        'content': [
                                            {
                                                'component': 'tr',
                                                'content': [
                                                    {'component': 'th', 'text': '时间'},
                                                    {'component': 'th', 'text': '状态'},
                                                    {'component': 'th', 'text': '飞牛币'},
                                                    {'component': 'th', 'text': '牛值'},
                                                    {'component': 'th', 'text': '积分'},
                                                    {'component': 'th', 'text': '登录天数'}
                                                ]
                                            }
                                        ]
                                    },
                                    # 表内容
                                    {
                                        'component': 'tbody',
                                        'content': history_rows
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def stop_service(self):
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"退出插件失败: {str(e)}")

    def get_command(self) -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [] 