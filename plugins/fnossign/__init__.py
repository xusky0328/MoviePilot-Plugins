"""
飞牛论坛签到插件
版本: 1.2
作者: madrays
功能:
- 自动完成飞牛论坛每日签到
- 支持签到失败重试
- 保存签到历史记录
- 提供详细的签到通知
- 增强的错误处理和日志

修改记录:
- v1.0: 初始版本，基本签到功能
- v1.1: 添加重试机制和历史记录
- v1.2: 增强错误处理，改进日志，优化签到逻辑
"""
import time
import requests
import re
from datetime import datetime, timedelta
import os
from pathlib import Path
from threading import Event

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.plugins import _PluginBase
from typing import Any, List, Dict, Tuple, Optional, Union
from app.log import logger
from app.schemas import NotificationType


class FnossignSigner:
    """
    飞牛论坛签到插件
    """
    # 插件名称
    plugin_name = "飞牛论坛签到"
    # 插件描述
    plugin_desc = "定时自动签到飞牛论坛"
    # 插件图标
    plugin_icon = "sign.png"
    # 插件版本
    plugin_version = "1.3"
    # 插件作者
    plugin_author = "thsrite"
    # 作者主页
    author_url = "https://github.com/thsrite"
    # 插件配置项ID前缀
    plugin_config_prefix = "fnossign_"
    # 加载顺序
    plugin_order = 31
    # 可使用的用户级别
    auth_level = 1

    def __init__(self, app):
        self.app = app
        # 日志
        self._logger = None
        # 退出事件
        self.exit_event = Event()
        # 调度器
        self._scheduler = None
        # 配置
        self._enabled = False
        self._notify = False
        self._cron = None
        self._cookie = None
        self._cookie_ua = None
        self._onlyonce = False
        self._sign_url = "https://club.fnnas.com"
        self._max_retries = 1
        self._retry_interval = 30
        self._history_days = 30
        # 签到历史记录
        self._history_file = None
        self._history_data = {}
        self._failed_history_data = {}
        # 签到结果
        self._sign_result = {}
        self._user_status = {}

    def init_plugin(self, config: dict = None):
        # 停止现有任务
        self.stop_service()

        # 获取配置
        if config:
            self._enabled = config.get("enabled", False)
            self._notify = config.get("notify", False)
            self._cron = config.get("cron")
            self._cookie = config.get("cookie")
            self._cookie_ua = config.get("cookie_ua")
            self._onlyonce = config.get("onlyonce")
            self._sign_url = config.get("sign_url") or "https://club.fnnas.com"
            self._max_retries = int(config.get("max_retries", 1))
            self._retry_interval = int(config.get("retry_interval", 30))
            self._history_days = int(config.get("history_days", 30))
        else:
            self._enabled = self.get_config("enabled")
            self._notify = self.get_config("notify")
            self._cron = self.get_config("cron")
            self._cookie = self.get_config("cookie")
            self._cookie_ua = self.get_config("cookie_ua")
            self._onlyonce = self.get_config("onlyonce")
            self._sign_url = self.get_config("sign_url") or "https://club.fnnas.com"
            self._max_retries = int(self.get_config("max_retries") or 1)
            self._retry_interval = int(self.get_config("retry_interval") or 30)
            self._history_days = int(self.get_config("history_days") or 30)

        # 加载历史记录
        self.init_history()

        # 通知
        self.post_message(
            channel=self.plugin_name,
            title="飞牛论坛签到",
            text=f"插件已{"启用" if self._enabled else "禁用"}"
        )

        if self._enabled or self._onlyonce:
            # 立即运行一次
            if self._onlyonce:
                self.info(f"执行一次性签到")
                self.set_config("onlyonce", False)
                self.__sign()

            # 启动定时任务
            if self._scheduler and self._cron and self._enabled:
                self.info(f"签到任务已启动，计划 {self._cron}")
                try:
                    self._scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Shanghai'))
                    self._scheduler.add_job(
                        func=self.__sign,
                        trigger=CronTrigger.from_crontab(self._cron),
                        name="飞牛论坛自动签到"
                    )
                    self._scheduler.print_jobs()
                    self._scheduler.start()
                except Exception as err:
                    self.error(f"签到任务启动失败：{str(err)}")

    def __sign(self):
        """
        签到
        """
        if not self._cookie:
            self.error(f"未配置Cookie，无法签到")
            return False

        # 签到开始
        self.info(f"============= 开始签到 =============")
        self.info(f"使用Cookie长度: {len(self._cookie)} 字符")

        # 检查Cookie格式
        if not self.__check_cookie():
            self.error(f"Cookie格式不正确，无法签到，请检查Cookie")
            return False

        # 记录签到结果
        self._sign_result = {}
        success_count = 0
        failed_count = 0
        try_count = 0
        
        # 签到主流程
        success = False
        
        while try_count <= self._max_retries:
            try:
                try_count += 1
                
                # 访问论坛首页，获取签到页面链接
                self.info(f"正在访问论坛首页...")
                headers = self.__get_headers()
                main_page = self.request_get(url=self._sign_url, 
                                            headers=headers,
                                            cookies=self.__get_cookies())
                
                if not main_page or main_page.status_code != 200:
                    self.error(f"访问论坛首页失败，HTTP状态码：{main_page.status_code if main_page else '未知'}")
                    continue
                
                # 访问签到页面，获取签到参数
                self.info(f"正在访问签到页面...")
                sign_page_url = f"{self._sign_url}/plugin.php?id=zqlj_sign"
                sign_page = self.request_get(url=sign_page_url,
                                           headers=headers,
                                           cookies=self.__get_cookies())
                
                if not sign_page or sign_page.status_code != 200:
                    self.error(f"访问签到页面失败，HTTP状态码：{sign_page.status_code if sign_page else '未知'}")
                    continue
                
                # 提取签到所需的sign参数
                sign_param_match = re.search(r'sign&sign=(.+)" class="btna', sign_page.text)
                if not sign_param_match:
                    # 检查是否今天已经签到
                    if "您今天已经打过卡了" in sign_page.text:
                        self.info(f"今天已经签到过了，获取积分信息...")
                        success = True
                        self._sign_result["message"] = "今天已经签到过了"
                        self._sign_result["status"] = "success"
                        break
                    else:
                        self.error(f"无法找到签到参数，可能签到页面格式已变更")
                        continue
                
                sign_param = sign_param_match.group(1)
                self.info(f"找到签到按钮 (匹配规则: '签到')")
                
                # 执行签到请求
                self.info(f"正在执行签到...")
                sign_url = f"{self._sign_url}/plugin.php?id=zqlj_sign&sign={sign_param}"
                sign_response = self.request_get(url=sign_url,
                                               headers=headers,
                                               cookies=self.__get_cookies())
                
                if not sign_response or sign_response.status_code != 200:
                    self.error(f"签到请求失败，HTTP状态码：{sign_response.status_code if sign_response else '未知'}")
                    continue
                
                # 检查签到结果
                if "恭喜您，打卡成功" in sign_response.text:
                    self.info(f"签到成功")
                    success = True
                    self._sign_result["message"] = "签到成功"
                    self._sign_result["status"] = "success"
                    break
                elif "您今天已经打过卡了" in sign_response.text:
                    self.info(f"今天已经签到过了")
                    success = True
                    self._sign_result["message"] = "今天已经签到过了"
                    self._sign_result["status"] = "success"
                    break
                else:
                    # 记录部分响应内容以便调试
                    preview = sign_response.text[:500] + "..." if len(sign_response.text) > 500 else sign_response.text
                    self.error(f"签到请求发送成功，但结果异常: {preview}")
                    continue
                
            except Exception as e:
                self.error(f"签到过程出错: {str(e)}")
                continue
            
            finally:
                if try_count <= self._max_retries and not success:
                    self.info(f"将在{self._retry_interval}秒后进行第{try_count}次重试...")
                    time.sleep(self._retry_interval)
        
        # 如果签到成功，获取用户积分信息
        if success:
            try:
                self.info(f"获取用户积分信息...")
                credit_url = f"{self._sign_url}/home.php?mod=spacecp&ac=credit&showcredit=1"
                credit_response = self.request_get(url=credit_url,
                                                 headers=headers,
                                                 cookies=self.__get_cookies())
                
                if credit_response and credit_response.status_code == 200:
                    # 提取积分信息
                    fnb_match = re.search(r'飞牛币: </em>(\d+)', credit_response.text)
                    nz_match = re.search(r'牛值: </em>(\d+)', credit_response.text)
                    ts_match = re.search(r'登陆天数: </em>(\d+)', credit_response.text)
                    jf_match = re.search(r'积分: </em>(\d+)', credit_response.text)
                    
                    self._user_status = {
                        "飞牛币": fnb_match.group(1) if fnb_match else "未知",
                        "牛值": nz_match.group(1) if nz_match else "未知",
                        "登陆天数": ts_match.group(1) if ts_match else "未知",
                        "积分": jf_match.group(1) if jf_match else "未知"
                    }
                    
                    status_text = " | ".join([f"{k}:{v}" for k, v in self._user_status.items()])
                    self.info(f"用户信息: {status_text}")
                    self._sign_result["user_info"] = self._user_status
            except Exception as e:
                self.error(f"获取用户积分信息失败: {str(e)}")
        
        # 记录签到历史
        self.add_history(success)
        
        # 发送通知
        if self._notify:
            if success:
                title = f"飞牛论坛签到成功"
                text = f"{self._sign_result.get('message', '签到成功')}\n"
                if self._user_status:
                    text += "\n".join([f"{k}: {v}" for k, v in self._user_status.items()])
            else:
                title = f"飞牛论坛签到失败"
                text = f"尝试{try_count}次后仍然失败，请检查Cookie或网站访问情况"
            
            self.post_message(channel=self.plugin_name, title=title, text=text)
        
        return success

    def __check_cookie(self):
        """
        检查Cookie是否合法
        """
        if not self._cookie:
            return False
        
        # 这里可以添加更多的Cookie检查逻辑，如格式检查等
        if len(self._cookie) < 10:
            self.warning(f"Cookie长度异常，可能无效")
            return False
            
        # 检查是否含有用户名
        username_match = re.search(r'(?:username|memberName)=([^;]+)', self._cookie)
        if not username_match:
            self.warning(f"Cookie可能有效，但未找到用户名")
        
        return True

    def __get_cookies(self):
        """
        将Cookie字符串转换为字典
        """
        cookies = {}
        if not self._cookie:
            return cookies
            
        try:
            # 分割Cookie字符串并转换为字典
            for item in self._cookie.split(';'):
                if not item.strip():
                    continue
                if '=' in item:
                    key, value = item.strip().split('=', 1)
                    cookies[key.strip()] = value.strip()
        except Exception as e:
            self.error(f"Cookie转换出错: {str(e)}")
            
        return cookies

    def __get_headers(self):
        """
        获取请求头
        """
        headers = {
            'User-Agent': self._cookie_ua or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.95 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
        }
        
        return headers

    def _get_credit_info(self, session):
        """
        获取积分信息并解析
        """
        try:
            # 先尝试从签到成功页面解析积分变动
            # 如果失败，再访问个人积分页面
            
            # 访问个人积分页面
            credit_url = "https://club.fnnas.com/home.php?mod=spacecp&ac=credit&showcredit=1"
            response = session.get(credit_url)
            response.raise_for_status()
            
            # 检查是否重定向到登录页
            if "您需要先登录才能继续本操作" in response.text or "请先登录后才能继续浏览" in response.text:
                logger.error("获取积分信息失败：需要登录")
                return {}
            
            # 记录调试信息
            debug_content = response.text[:300]
            logger.debug(f"积分页面内容预览: {debug_content}")
            
            credit_info = {}
            
            # 尝试多种可能的格式匹配积分信息
            
            # 解析飞牛币 - 多种可能的格式
            fnb_patterns = [
                r'飞牛币</em>.*?(\d+)',
                r'飞牛币.*?(\d+)',
                r'extcredits1.*?(\d+)'
            ]
            
            for pattern in fnb_patterns:
                fnb_match = re.search(pattern, response.text, re.DOTALL)
                if fnb_match:
                    credit_info["fnb"] = int(fnb_match.group(1))
                    logger.debug(f"找到飞牛币: {credit_info['fnb']} (匹配规则: '{pattern}')")
                    break
            
            if "fnb" not in credit_info:
                logger.warning("未找到飞牛币信息")
                credit_info["fnb"] = 0
            
            # 解析牛值 - 多种可能的格式
            nz_patterns = [
                r'牛值</em>.*?(\d+)',
                r'牛值.*?(\d+)',
                r'extcredits2.*?(\d+)'
            ]
            
            for pattern in nz_patterns:
                nz_match = re.search(pattern, response.text, re.DOTALL)
                if nz_match:
                    credit_info["nz"] = int(nz_match.group(1))
                    logger.debug(f"找到牛值: {credit_info['nz']} (匹配规则: '{pattern}')")
                    break
                    
            if "nz" not in credit_info:
                logger.warning("未找到牛值信息")
                credit_info["nz"] = 0
            
            # 解析积分 - 多种可能的格式
            credit_patterns = [
                r'积分: (\d+)',
                r'积分</em>.*?(\d+)',
                r'总积分.*?(\d+)'
            ]
            
            for pattern in credit_patterns:
                credit_match = re.search(pattern, response.text, re.DOTALL)
                if credit_match:
                    credit_info["jf"] = int(credit_match.group(1))
                    logger.debug(f"找到积分: {credit_info['jf']} (匹配规则: '{pattern}')")
                    break
                    
            if "jf" not in credit_info:
                logger.warning("未找到积分信息")
                credit_info["jf"] = 0
            
            # 解析连续登录天数 - 多种可能的格式
            login_patterns = [
                r'连续登录(\d+)天',
                r'您已连续登录.*?(\d+).*?天',
                r'已登录.*?(\d+).*?天'
            ]
            
            for pattern in login_patterns:
                login_days_match = re.search(pattern, response.text, re.DOTALL)
                if login_days_match:
                    credit_info["ts"] = int(login_days_match.group(1))
                    logger.debug(f"找到登录天数: {credit_info['ts']} (匹配规则: '{pattern}')")
                    break
                    
            if "ts" not in credit_info:
                logger.warning("未找到登录天数信息")
                credit_info["ts"] = 0
                
            logger.info(f"获取到积分信息: 飞牛币={credit_info.get('fnb', 0)}, 牛值={credit_info.get('nz', 0)}, "
                       f"积分={credit_info.get('jf', 0)}, 登录天数={credit_info.get('ts', 0)}")
            
            return credit_info
        except requests.RequestException as re:
            logger.error(f"获取积分信息网络错误: {str(re)}")
            return {}
        except Exception as e:
            logger.error(f"获取积分信息失败: {str(e)}", exc_info=True)
            return {}

    def _save_sign_history(self, sign_data):
        """
        保存签到历史记录
        """
        try:
            # 读取现有历史
            history = self.get_data('sign_history') or []
            
            # 确保日期格式正确
            if "date" not in sign_data:
                sign_data["date"] = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
                
            history.append(sign_data)
            
            # 清理旧记录
            retention_days = int(self._history_days)
            now = datetime.now()
            valid_history = []
            
            for record in history:
                try:
                    # 尝试将记录日期转换为datetime对象
                    record_date = datetime.strptime(record["date"], '%Y-%m-%d %H:%M:%S')
                    # 检查是否在保留期内
                    if (now - record_date).days < retention_days:
                        valid_history.append(record)
                except (ValueError, KeyError):
                    # 如果记录日期格式不正确，尝试修复
                    logger.warning(f"历史记录日期格式无效: {record.get('date', '无日期')}")
                    # 添加新的日期并保留记录
                    record["date"] = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
                    valid_history.append(record)
            
            # 保存历史
            self.save_data(key="sign_history", value=valid_history)
            logger.info(f"保存签到历史记录，当前共有 {len(valid_history)} 条记录")
            
        except Exception as e:
            logger.error(f"保存签到历史记录失败: {str(e)}", exc_info=True)

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
        if "签到成功" in status or "已签到" in status:
            title = "【飞牛论坛签到成功】"
            text = f"✅ 状态: {status}\n" \
                   f"💎 飞牛币: {fnb}\n" \
                   f"🔥 牛值: {nz}\n" \
                   f"✨ 积分: {credit}\n" \
                   f"📆 登录天数: {login_days}"
        else:
            title = "【飞牛论坛签到失败】"
            text = f"❌ 状态: {status}\n\n" \
                   f"⚠️ 可能的解决方法:\n" \
                   f"• 检查Cookie是否过期\n" \
                   f"• 确认站点是否可正常访问\n" \
                   f"• 手动登录查看是否需要验证码"
            
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
                "func": self.__sign,
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
                                    'md': 3
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
                                    'md': 3
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
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'retry_interval',
                                            'label': '重试间隔(秒)',
                                            'type': 'number',
                                            'placeholder': '30'
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
                                            'text': '飞牛论坛签到插件，支持自动签到、失败重试和通知。v1.2增强了错误处理和重试机制。'
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

    def _check_cookie_valid(self, session):
        """检查Cookie是否有效"""
        try:
            # 访问需要登录的页面
            profile_url = "https://club.fnnas.com/home.php?mod=space&do=profile"
            response = session.get(profile_url)
            response.raise_for_status()

            # 检查是否需要登录
            if "请先登录后才能继续浏览" in response.text or "您需要登录后才能继续本操作" in response.text:
                logger.error("Cookie无效或已过期")
                return False

            # 尝试获取用户名，确认已登录
            username_match = re.search(r'title="访问我的空间">(.*?)</a>', response.text)
            if username_match:
                username = username_match.group(1)
                logger.info(f"Cookie有效，当前用户: {username}")
                return True
            else:
                logger.warning("Cookie可能有效，但未找到用户名")
                return True  # 假设有效，因为没有明确的无效标志
                
        except Exception as e:
            logger.error(f"检查Cookie有效性时出错: {str(e)}")
            return False 