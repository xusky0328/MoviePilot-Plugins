import json
import re
import time
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


class FengchaoSignin(_PluginBase):
    # 插件名称
    plugin_name = "蜂巢签到"
    # 插件描述
    plugin_desc = "蜂巢论坛签到。"
    # 插件图标
    plugin_icon = "fengchao.png"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "madrays"
    # 作者主页
    author_url = "https://github.com/madrays"
    # 插件配置项ID前缀
    plugin_config_prefix = "fengchaosignin_"
    # 加载顺序
    plugin_order = 24
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _enabled = False
    # 任务执行间隔
    _cron = None
    _cookie = None
    _onlyonce = False
    _notify = False
    _history_days = None

    # 定时器
    _scheduler: Optional[BackgroundScheduler] = None

    def init_plugin(self, config: dict = None):
        # 停止现有任务
        self.stop_service()

        if config:
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._cookie = config.get("cookie")
            self._notify = config.get("notify")
            self._onlyonce = config.get("onlyonce")
            self._history_days = config.get("history_days") or 30

        if self._onlyonce:
            # 定时服务
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            logger.info(f"蜂巢签到服务启动，立即运行一次")
            self._scheduler.add_job(func=self.__signin, trigger='date',
                                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                    name="蜂巢签到")
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

    def _send_notification(self, title, text):
        """
        发送通知
        """
        if self._notify:
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=title,
                text=text
            )

    def __signin(self):
        """
        蜂巢签到
        """
        res = RequestUtils(cookies=self._cookie).get_res(url="https://pting.club")
        if not res or res.status_code != 200:
            logger.error("请求蜂巢错误")
            
            # 发送通知
            if self._notify:
                self._send_notification(
                    title="【❌ 蜂巢签到失败】",
                    text=(
                        f"📢 执行结果\n"
                        f"━━━━━━━━━━\n"
                        f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"❌ 状态：签到失败，无法连接到站点\n"
                        f"━━━━━━━━━━\n"
                        f"💡 可能的解决方法\n"
                        f"• 检查Cookie是否过期\n"
                        f"• 确认站点是否可访问\n"
                        f"• 尝试手动登录网站\n"
                        f"━━━━━━━━━━"
                    )
                )
            
            # 记录历史
            history = {
                "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                "status": "签到失败：无法连接到站点",
                "money": None,
                "totalContinuousCheckIn": None
            }
            self._save_history(history)
            return

        # 获取csrfToken
        pattern = r'"csrfToken":"(.*?)"'
        csrfToken = re.findall(pattern, res.text)
        if not csrfToken:
            logger.error("请求csrfToken失败")
            
            # 发送通知
            if self._notify:
                self._send_notification(
                    title="【❌ 蜂巢签到失败】",
                    text=(
                        f"📢 执行结果\n"
                        f"━━━━━━━━━━\n"
                        f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"❌ 状态：签到失败，无法获取CSRF令牌\n"
                        f"━━━━━━━━━━\n"
                        f"💡 可能的解决方法\n"
                        f"• 检查Cookie是否过期\n"
                        f"• 尝试手动登录网站\n"
                        f"━━━━━━━━━━"
                    )
                )
            
            # 记录历史
            history = {
                "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                "status": "签到失败：无法获取CSRF令牌",
                "money": None,
                "totalContinuousCheckIn": None
            }
            self._save_history(history)
            return

        csrfToken = csrfToken[0]
        logger.info(f"获取csrfToken成功 {csrfToken}")

        # 获取userid
        pattern = r'"userId":(\d+)'
        match = re.search(pattern, res.text)

        if match:
            userId = match.group(1)
            logger.info(f"获取userid成功 {userId}")
        else:
            logger.error("未找到userId")
            
            # 发送通知
            if self._notify:
                self._send_notification(
                    title="【❌ 蜂巢签到失败】",
                    text=(
                        f"📢 执行结果\n"
                        f"━━━━━━━━━━\n"
                        f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"❌ 状态：签到失败，无法获取用户ID\n"
                        f"━━━━━━━━━━\n"
                        f"💡 可能的解决方法\n"
                        f"• 检查Cookie是否有效\n"
                        f"• 尝试手动登录网站\n"
                        f"━━━━━━━━━━"
                    )
                )
            
            # 记录历史
            history = {
                "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                "status": "签到失败：无法获取用户ID",
                "money": None,
                "totalContinuousCheckIn": None
            }
            self._save_history(history)
            return

        headers = {
            "X-Csrf-Token": csrfToken,
            "X-Http-Method-Override": "PATCH",
            "Cookie": self._cookie
        }

        data = {
            "data": {
                "type": "users",
                "attributes": {
                    "canCheckin": False,
                    "totalContinuousCheckIn": 2
                },
                "id": userId
            }
        }

        # 开始签到
        res = RequestUtils(headers=headers).post_res(url=f"https://pting.club/api/users/{userId}", json=data)

        if not res or res.status_code != 200:
            logger.error("蜂巢签到失败")

            # 发送通知
            if self._notify:
                self._send_notification(
                    title="【❌ 蜂巢签到失败】",
                    text=(
                        f"📢 执行结果\n"
                        f"━━━━━━━━━━\n"
                        f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"❌ 状态：签到失败，API请求错误\n"
                        f"━━━━━━━━━━\n"
                        f"💡 可能的解决方法\n"
                        f"• 检查Cookie是否有效\n"
                        f"• 确认站点是否可访问\n"
                        f"• 尝试手动登录网站\n"
                        f"━━━━━━━━━━"
                    )
                )
            
            # 记录历史
            history = {
                "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                "status": "签到失败：API请求错误",
                "money": None,
                "totalContinuousCheckIn": None
            }
            self._save_history(history)
            return

        sign_dict = json.loads(res.text)
        money = sign_dict['data']['attributes']['money']
        totalContinuousCheckIn = sign_dict['data']['attributes']['totalContinuousCheckIn']

        # 检查是否已签到
        if "canCheckin" in sign_dict['data']['attributes'] and not sign_dict['data']['attributes']['canCheckin']:
            status_text = "已签到"
            reward_text = "今日已领取奖励"
            logger.info(f"蜂巢已签到，当前花粉: {money}，累计签到: {totalContinuousCheckIn}")
        else:
            status_text = "签到成功"
            reward_text = "获得10花粉奖励"
            logger.info(f"蜂巢签到成功，当前花粉: {money}，累计签到: {totalContinuousCheckIn}")

        # 发送通知
        if self._notify:
            self._send_notification(
                title=f"【✅ 蜂巢{status_text}】",
                text=(
                    f"📢 执行结果\n"
                    f"━━━━━━━━━━\n"
                    f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"✨ 状态：{status_text}\n"
                    f"🎁 奖励：{reward_text}\n"
                    f"━━━━━━━━━━\n"
                    f"📊 积分统计\n"
                    f"🌸 花粉：{money}\n"
                    f"📆 签到天数：{totalContinuousCheckIn}\n"
                    f"━━━━━━━━━━"
                )
            )

        # 读取历史记录
        history = {
            "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
            "status": status_text,
            "money": money,
            "totalContinuousCheckIn": totalContinuousCheckIn
        }
        
        # 保存签到历史
        self._save_history(history)

    def _save_history(self, record):
        """
        保存签到历史记录
        """
        # 读取历史记录
        history = self.get_data('history') or []
        
        # 添加新记录
        history.append(record)
        
        # 保留指定天数的记录
        if self._history_days:
            try:
                thirty_days_ago = time.time() - int(self._history_days) * 24 * 60 * 60
                history = [record for record in history if
                          datetime.strptime(record["date"],
                                         '%Y-%m-%d %H:%M:%S').timestamp() >= thirty_days_ago]
            except Exception as e:
                logger.error(f"清理历史记录异常: {str(e)}")
        
        # 保存历史记录
        self.save_data(key="history", value=history)

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
        """
        if self._enabled and self._cron:
            return [{
                "id": "FengchaoSignin",
                "name": "蜂巢签到服务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.__signin,
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
                        'component': 'VCard',
                        'props': {
                            'variant': 'outlined',
                            'class': 'mb-3'
                        },
                        'content': [
                            {
                                'component': 'VCardTitle',
                                'props': {
                                    'class': 'd-flex align-center'
                                },
                                'content': [
                                    {
                                        'component': 'VIcon',
                                        'props': {
                                            'color': 'primary',
                                            'class': 'mr-2'
                                        },
                                        'text': 'mdi-calendar-check'
                                    },
                                    {
                                        'component': 'span',
                                        'text': '基本设置'
                                    }
                                ]
                            },
                            {
                                'component': 'VDivider'
                            },
                            {
                                'component': 'VCardText',
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
                                                        'component': 'VCronField',
                                                        'props': {
                                                            'model': 'cron',
                                                            'label': '签到周期'
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
                                                    'cols': 12
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VAlert',
                                                        'props': {
                                                            'type': 'info',
                                                            'variant': 'tonal',
                                                            'density': 'compact',
                                                            'class': 'mt-2'
                                                        },
                                                        'content': [
                                                            {
                                                                'component': 'div',
                                                                'props': {
                                                                    'class': 'd-flex align-center'
                                                                },
                                                                'content': [
                                                                    {
                                                                        'component': 'VIcon',
                                                                        'props': {
                                                                            'size': 'small',
                                                                            'class': 'mr-2'
                                                                        },
                                                                        'text': 'mdi-flower'
                                                                    },
                                                                    {
                                                                        'component': 'span',
                                                                        'text': '每日签到可获得10花粉奖励'
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
                            'variant': 'outlined'
                        },
                        'content': [
                            {
                                'component': 'VCardTitle',
                                'props': {
                                    'class': 'd-flex align-center'
                                },
                                'content': [
                                    {
                                        'component': 'VIcon',
                                        'props': {
                                            'color': 'primary',
                                            'class': 'mr-2'
                                        },
                                        'text': 'mdi-cookie'
                                    },
                                    {
                                        'component': 'span',
                                        'text': '账号设置'
                                    }
                                ]
                            },
                            {
                                'component': 'VDivider'
                            },
                            {
                                'component': 'VCardText',
                                'content': [
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
                                                        'component': 'VTextField',
                                                        'props': {
                                                            'model': 'cookie',
                                                            'label': 'Cookie',
                                                            'placeholder': '输入蜂巢Cookie'
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
                                                    'cols': 12
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VAlert',
                                                        'props': {
                                                            'type': 'info',
                                                            'variant': 'tonal',
                                                            'density': 'compact',
                                                            'text': '蜂巢Cookie获取方法：浏览器登录蜂巢，F12控制台，Network标签，刷新页面，找到pting.club请求，右键Copy -> Copy as cURL，从复制内容中找到cookie: 后的内容'
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
                                                    'cols': 12
                                                },
                                                'content': [
                                                    {
                                                        'component': 'div',
                                                        'props': {
                                                            'class': 'text-caption text-grey text-right mt-2'
                                                        },
                                                        'text': 'Plugin improved by: thsrite'
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
        ], {
            "enabled": False,
            "notify": True,
            "cron": "30 8 * * *",
            "onlyonce": False,
            "cookie": "",
            "history_days": 30
        }

    def get_page(self) -> List[dict]:
        """
        构建插件详情页面，展示签到历史
        """
        # 获取签到历史
        history = self.get_data('history') or []
        
        # 如果没有历史记录
        if not history:
            return [
                {
                    'component': 'VAlert',
                    'props': {
                        'type': 'info',
                        'variant': 'tonal',
                        'text': '暂无签到记录，请先配置Cookie并启用插件',
                        'class': 'mb-2',
                        'prepend-icon': 'mdi-information'
                    }
                },
                {
                    'component': 'VCard',
                    'props': {'variant': 'outlined', 'class': 'mb-4'},
                    'content': [
                        {
                            'component': 'VCardTitle',
                            'props': {'class': 'd-flex align-center'},
                            'content': [
                                {
                                    'component': 'VIcon',
                                    'props': {
                                        'color': 'amber-darken-2',
                                        'class': 'mr-2'
                                    },
                                    'text': 'mdi-flower'
                                },
                                {
                                    'component': 'span',
                                    'props': {'class': 'text-h6'},
                                    'text': '签到奖励说明'
                                }
                            ]
                        },
                        {
                            'component': 'VDivider'
                        },
                        {
                            'component': 'VCardText',
                            'props': {'class': 'pa-3'},
                            'content': [
                                {
                                    'component': 'div',
                                    'props': {'class': 'd-flex align-center mb-2'},
                                    'content': [
                                        {
                                            'component': 'VIcon',
                                            'props': {
                                                'color': 'amber-darken-2',
                                                'size': 'small',
                                                'class': 'mr-2'
                                            },
                                            'text': 'mdi-check-circle'
                                        },
                                        {
                                            'component': 'span',
                                            'text': '每日签到可获得10花粉奖励'
                                        }
                                    ]
                                },
                                {
                                    'component': 'div',
                                    'props': {'class': 'd-flex align-center'},
                                    'content': [
                                        {
                                            'component': 'VIcon',
                                            'props': {
                                                'color': 'primary',
                                                'size': 'small',
                                                'class': 'mr-2'
                                            },
                                            'text': 'mdi-calendar-check'
                                        },
                                        {
                                            'component': 'span',
                                            'text': '连续签到可累积天数，提升论坛等级'
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        
        # 按时间倒序排列历史
        history = sorted(history, key=lambda x: x.get("date", ""), reverse=True)
        
        # 构建历史记录表格行
        history_rows = []
        for record in history:
            status_text = record.get("status", "未知")
            
            # 根据状态设置颜色和图标
            if "签到成功" in status_text or "已签到" in status_text:
                status_color = "success"
                status_icon = "mdi-check-circle"
            else:
                status_color = "error"
                status_icon = "mdi-close-circle"
            
            history_rows.append({
                'component': 'tr',
                'content': [
                    # 日期列
                    {
                        'component': 'td',
                        'props': {
                            'class': 'text-caption'
                        },
                        'text': record.get("date", "")
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
                                    'variant': 'outlined',
                                    'prepend-icon': status_icon
                                },
                                'text': status_text
                            }
                        ]
                    },
                    # 花粉列
                    {
                        'component': 'td',
                        'content': [
                            {
                                'component': 'div',
                                'props': {
                                    'class': 'd-flex align-center'
                                },
                                'content': [
                                    {
                                        'component': 'VIcon',
                                        'props': {
                                            'size': 'x-small',
                                            'color': 'amber-darken-2',
                                            'class': 'mr-1'
                                        },
                                        'text': 'mdi-flower'
                                    },
                                    {
                                        'component': 'span',
                                        'text': record.get('money', '—')
                                    }
                                ]
                            }
                        ]
                    },
                    # 签到天数列
                    {
                        'component': 'td',
                        'content': [
                            {
                                'component': 'div',
                                'props': {
                                    'class': 'd-flex align-center'
                                },
                                'content': [
                                    {
                                        'component': 'VIcon',
                                        'props': {
                                            'size': 'x-small',
                                            'color': 'primary',
                                            'class': 'mr-1'
                                        },
                                        'text': 'mdi-calendar-check'
                                    },
                                    {
                                        'component': 'span',
                                        'text': record.get('totalContinuousCheckIn', '—')
                                    }
                                ]
                            }
                        ]
                    },
                    # 奖励列
                    {
                        'component': 'td',
                        'content': [
                            {
                                'component': 'div',
                                'props': {
                                    'class': 'd-flex align-center'
                                },
                                'content': [
                                    {
                                        'component': 'VIcon',
                                        'props': {
                                            'size': 'x-small',
                                            'color': 'amber-darken-2',
                                            'class': 'mr-1'
                                        },
                                        'text': 'mdi-gift'
                                    },
                                    {
                                        'component': 'span',
                                        'text': '10花粉' if ("签到成功" in status_text or "已签到" in status_text) else '—'
                                    }
                                ]
                            }
                        ]
                    }
                ]
            })
        
        # 最终页面组装
        return [
            # 标题和卡片
            {
                'component': 'VCard',
                'props': {'variant': 'outlined', 'class': 'mb-4'},
                'content': [
                    {
                        'component': 'VCardTitle',
                        'props': {'class': 'd-flex align-center'},
                        'content': [
                            {
                                'component': 'VIcon',
                                'props': {
                                    'color': 'primary',
                                    'class': 'mr-2'
                                },
                                'text': 'mdi-calendar-check'
                            },
                            {
                                'component': 'span',
                                'props': {'class': 'text-h6'},
                                'text': '蜂巢签到历史'
                            },
                            {
                                'component': 'VSpacer'
                            },
                            {
                                'component': 'VChip',
                                'props': {
                                    'color': 'amber-darken-2',
                                    'size': 'small',
                                    'variant': 'outlined',
                                    'prepend-icon': 'mdi-flower'
                                },
                                'text': '每日可得10花粉'
                            }
                        ]
                    },
                    {
                        'component': 'VDivider'
                    },
                    {
                        'component': 'VCardText',
                        'props': {'class': 'pa-2'},
                        'content': [
                            {
                                'component': 'VTable',
                                'props': {
                                    'hover': True,
                                    'density': 'comfortable'
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
                                                    {'component': 'th', 'text': '花粉'},
                                                    {'component': 'th', 'text': '签到天数'},
                                                    {'component': 'th', 'text': '奖励'}
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
            },
            # 添加样式
            {
                'component': 'style',
                'text': """
                .v-table {
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
                }
                .v-table th {
                    background-color: rgba(var(--v-theme-primary), 0.05);
                    color: rgb(var(--v-theme-primary));
                    font-weight: 600;
                }
                """
            }
        ]

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error("退出插件失败：%s" % str(e)) 