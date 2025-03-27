"""
NodeSeek论坛签到插件
版本: 1.0.0
作者: Hosea
功能:
- 自动完成NodeSeek论坛每日签到
- 支持选择随机奖励或固定奖励
- 自动给帖子加鸡腿（可配置）
- 定时签到和历史记录
- 支持绕过CloudFlare防护
"""
import time
import random
import traceback
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.plugins import _PluginBase
from typing import Any, List, Dict, Tuple, Optional
from app.log import logger
from app.schemas import NotificationType
import requests
from urllib.parse import urlencode

# 尝试导入curl_cffi库，用于绕过CloudFlare防护
try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
    logger.info("成功加载curl_cffi库，可以绕过CloudFlare防护")
except ImportError:
    HAS_CURL_CFFI = False
    logger.warning("未安装curl_cffi库，无法绕过CloudFlare防护。建议安装: pip install curl_cffi>=0.5.9")


class nodeseeksign(_PluginBase):
    # 插件名称
    plugin_name = "NodeSeek论坛签到"
    # 插件描述
    plugin_desc = "懒羊羊定制：自动完成NodeSeek论坛每日签到，支持随机奖励和自动加鸡腿功能"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/madrays/MoviePilot-Plugins/main/icons/nodeseeksign.png"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "madrays"
    # 作者主页
    author_url = "https://github.com/madrays"
    # 插件配置项ID前缀
    plugin_config_prefix = "nodeseeksign_"
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
    _auto_chicken = False  # 是否自动加鸡腿
    _random_choice = True  # 是否选择随机奖励，否则选择固定奖励
    _history_days = 30  # 历史保留天数
    _use_proxy = True     # 是否使用代理，默认启用

    # 定时器
    _scheduler: Optional[BackgroundScheduler] = None
    _manual_trigger = False

    def init_plugin(self, config: dict = None):
        # 停止现有任务
        self.stop_service()

        logger.info("============= nodeseeksign 初始化 =============")
        try:
            if config:
                self._enabled = config.get("enabled")
                self._cookie = config.get("cookie")
                self._notify = config.get("notify")
                self._cron = config.get("cron")
                self._onlyonce = config.get("onlyonce")
                self._auto_chicken = config.get("auto_chicken")
                self._random_choice = config.get("random_choice")
                self._history_days = int(config.get("history_days", 30))
                self._use_proxy = config.get("use_proxy", True)
                
                logger.info(f"配置: enabled={self._enabled}, notify={self._notify}, cron={self._cron}, "
                           f"auto_chicken={self._auto_chicken}, "
                           f"random_choice={self._random_choice}, history_days={self._history_days}, "
                           f"use_proxy={self._use_proxy}")
            
            if self._onlyonce:
                logger.info("执行一次性签到")
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                self._manual_trigger = True
                self._scheduler.add_job(func=self.sign, trigger='date',
                                   run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                   name="NodeSeek论坛签到")
                self._onlyonce = False
                self.update_config({
                    "onlyonce": False,
                    "enabled": self._enabled,
                    "cookie": self._cookie,
                    "notify": self._notify,
                    "cron": self._cron,
                    "auto_chicken": self._auto_chicken,
                    "random_choice": self._random_choice,
                    "history_days": self._history_days,
                    "use_proxy": self._use_proxy
                })

                # 启动任务
                if self._scheduler.get_jobs():
                    self._scheduler.print_jobs()
                    self._scheduler.start()

        except Exception as e:
            logger.error(f"nodeseeksign初始化错误: {str(e)}", exc_info=True)

    def sign(self):
        """
        执行NodeSeek签到
        """
        logger.info("============= 开始NodeSeek签到 =============")
        sign_dict = None
        
        try:
            # 检查是否今日已成功签到（通过记录）
            if self._is_already_signed_today():
                logger.info("根据历史记录，今日已成功签到，跳过本次执行")
                
                # 创建跳过记录
                sign_dict = {
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": "跳过: 今日已签到",
                }
                
                # 发送通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【NodeSeek论坛重复签到】",
                        text=f"今日已完成签到，跳过执行\n⏱️ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                
                return sign_dict
            
            # 检查Cookie
            if not self._cookie:
                logger.error("未配置Cookie")
                sign_dict = {
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": "签到失败: 未配置Cookie",
                }
                self._save_sign_history(sign_dict)
                
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【NodeSeek论坛签到失败】",
                        text="未配置Cookie，请在设置中添加Cookie"
                    )
                return sign_dict
            
            # 执行API签到
            result = self._run_api_sign()
            
            # 处理签到结果
            if result["success"]:
                # 保存签到记录
                sign_dict = {
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": "签到成功" if not result.get("already_signed") else "已签到",
                    "message": result.get("message", "")
                }
                self._save_sign_history(sign_dict)
                self._save_last_sign_date()
                
                # 发送通知
                if self._notify:
                    self._send_sign_notification(sign_dict, result)
            else:
                # 签到失败
                sign_dict = {
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": "签到失败",
                    "message": result.get("message", "")
                }
                self._save_sign_history(sign_dict)
                
                # 发送通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【NodeSeek论坛签到失败】",
                        text=f"签到失败: {result.get('message', '未知错误')}\n⏱️ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
            
            return sign_dict
        
        except Exception as e:
            logger.error(f"NodeSeek签到过程中出错: {str(e)}", exc_info=True)
            sign_dict = {
                "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                "status": f"签到出错: {str(e)}",
            }
            self._save_sign_history(sign_dict)
            
            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【NodeSeek论坛签到出错】",
                    text=f"签到过程中出错: {str(e)}\n⏱️ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            
            return sign_dict
    
    def _run_api_sign(self):
        """
        使用API执行NodeSeek签到
        """
        try:
            logger.info("使用API执行NodeSeek签到...")
            
            # 初始化结果字典
            result = {
                "success": False,
                "signed": False,
                "already_signed": False,
                "added_chicken": False,
                "message": ""
            }
            
            # 准备请求头
            headers = {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                'origin': "https://www.nodeseek.com",
                'referer': "https://www.nodeseek.com/board",
                'Cookie': self._cookie
            }
            
            # 构建签到URL，根据配置决定是否使用随机奖励
            random_param = "true" if self._random_choice else "false"
            url = f"https://www.nodeseek.com/api/attendance?random={random_param}"
            
            # 获取代理设置
            proxies = self._get_proxies()
            
            # 输出调试信息
            if proxies:
                logger.info(f"使用代理: {proxies}")
            
            logger.info(f"执行签到请求: {url}")
            
            # 使用curl_cffi库发送请求以绕过CloudFlare防护
            if HAS_CURL_CFFI:
                logger.info("使用curl_cffi绕过CloudFlare防护发送请求")
                
                try:
                    # 创建一个curl_cffi会话
                    session = curl_requests.Session(impersonate="chrome110")
                    
                    # 设置代理（如果有）
                    if proxies:
                        # 提取代理URL
                        http_proxy = proxies.get('http')
                        if http_proxy:
                            session.proxies = {"http": http_proxy, "https": http_proxy}
                    
                    # 发送POST请求
                    response = session.post(
                        url,
                        headers=headers,
                        timeout=30
                    )
                    
                except Exception as e:
                    logger.error(f"curl_cffi请求失败: {str(e)}")
                    # 回退到普通请求
                    response = requests.post(url, headers=headers, proxies=proxies, timeout=30)
            else:
                # 使用普通requests发送请求
                response = requests.post(url, headers=headers, proxies=proxies, timeout=30)
            
            # 解析响应
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    logger.info(f"签到响应: {response_data}")
                    
                    message = response_data.get('message', '')
                    
                    # 判断签到结果
                    if "鸡腿" in message or response_data.get('success') == True:
                        # 签到成功
                        result["success"] = True
                        result["signed"] = True
                        result["message"] = message
                        logger.info(f"签到成功: {message}")
                    elif "已完成签到" in message:
                        # 今日已签到
                        result["success"] = True
                        result["already_signed"] = True
                        result["message"] = message
                        logger.info(f"今日已签到: {message}")
                    elif message == "USER NOT FOUND" or response_data.get('status') == 404:
                        # Cookie失效
                        result["message"] = "Cookie已失效，请更新"
                        logger.error("Cookie已失效，请更新")
                    else:
                        # 其他失败情况
                        result["message"] = f"签到失败: {message}"
                        logger.error(f"签到失败: {message}")
                    
                    # 如果签到成功或已签到，且开启了自动加鸡腿功能，则继续执行加鸡腿操作
                    if (result["success"]) and self._auto_chicken:
                        chicken_result = self._perform_add_chicken()
                        if chicken_result.get("success"):
                            result["added_chicken"] = True
                            result["message"] += f" | 加鸡腿: {chicken_result.get('message', '成功')}"
                        else:
                            result["message"] += f" | 加鸡腿: {chicken_result.get('message', '失败')}"
                
                except ValueError:
                    # JSON解析失败
                    result["message"] = f"解析响应失败: {response.text[:100]}..."
                    logger.error(f"解析签到响应失败: {response.text[:100]}...")
            else:
                # 非200响应
                result["message"] = f"请求失败，状态码: {response.status_code}"
                logger.error(f"签到请求失败，状态码: {response.status_code}, 响应: {response.text[:100]}...")
                
                # 检查是否是CloudFlare防护
                if response.status_code == 403 and ("cloudflare" in response.text.lower() or "cf-" in response.text.lower()):
                    logger.error("请求被CloudFlare防护拦截，建议安装curl_cffi库绕过防护")
                    result["message"] += " | 被CloudFlare拦截，请安装curl_cffi库"
            
            return result
            
        except Exception as e:
            logger.error(f"API签到出错: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"API签到出错: {str(e)}"
            }
    
    def _get_proxies(self):
        """
        获取代理设置
        """
        if not self._use_proxy:
            logger.info("未启用代理")
            return None
            
        try:
            # 获取系统代理设置
            if hasattr(settings, 'PROXY') and settings.PROXY:
                logger.info(f"使用系统代理: {settings.PROXY}")
                return settings.PROXY
            else:
                logger.warning("系统代理未配置")
                return None
        except Exception as e:
            logger.error(f"获取代理设置出错: {str(e)}")
            return None
    
    def _perform_add_chicken(self):
        """
        执行加鸡腿操作
        """
        try:
            logger.info("开始执行加鸡腿操作...")
            
            # 获取热门帖子ID
            topic_id = self._get_random_topic_id()
            if not topic_id:
                return {"success": False, "message": "未找到合适的帖子"}
            
            # 添加鸡腿API
            headers = {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                'origin': "https://www.nodeseek.com",
                'referer': f"https://www.nodeseek.com/post/{topic_id}",
                'Cookie': self._cookie
            }
            
            url = f"https://www.nodeseek.com/api/post/{topic_id}/chick"
            
            # 获取代理设置
            proxies = self._get_proxies()
            
            # 使用curl_cffi库发送请求以绕过CloudFlare防护
            if HAS_CURL_CFFI:
                logger.info("使用curl_cffi绕过CloudFlare防护发送请求")
                
                try:
                    # 创建一个curl_cffi会话
                    session = curl_requests.Session(impersonate="chrome110")
                    
                    # 设置代理（如果有）
                    if proxies:
                        # 提取代理URL
                        http_proxy = proxies.get('http')
                        if http_proxy:
                            session.proxies = {"http": http_proxy, "https": http_proxy}
                    
                    # 发送POST请求
                    response = session.post(
                        url,
                        headers=headers,
                        timeout=30
                    )
                    
                except Exception as e:
                    logger.error(f"curl_cffi请求失败: {str(e)}")
                    # 回退到普通请求
                    response = requests.post(url, headers=headers, proxies=proxies, timeout=30)
            else:
                # 使用普通requests发送请求
                response = requests.post(url, headers=headers, proxies=proxies, timeout=30)
            
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    logger.info(f"加鸡腿响应: {response_data}")
                    
                    if response_data.get('success') == True:
                        return {"success": True, "message": f"成功给帖子 {topic_id} 加鸡腿"}
                    else:
                        return {"success": False, "message": response_data.get('message', '未知原因')}
                        
                except ValueError:
                    return {"success": False, "message": f"解析响应失败: {response.text[:100]}..."}
            else:
                return {"success": False, "message": f"请求失败，状态码: {response.status_code}"}
            
        except Exception as e:
            logger.error(f"执行加鸡腿出错: {str(e)}", exc_info=True)
            return {"success": False, "message": f"执行出错: {str(e)}"}
    
    def _get_random_topic_id(self):
        """
        获取随机帖子ID
        """
        try:
            # 获取热门帖子列表
            headers = {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                'Cookie': self._cookie
            }
            
            # 从交易区获取帖子
            url = "https://www.nodeseek.com/api/posts?filter=featured&offset=0&limit=20"
            
            # 获取代理设置
            proxies = self._get_proxies()
            
            # 使用curl_cffi库发送请求以绕过CloudFlare防护
            if HAS_CURL_CFFI:
                logger.info("使用curl_cffi绕过CloudFlare防护获取帖子列表")
                
                try:
                    # 创建一个curl_cffi会话
                    session = curl_requests.Session(impersonate="chrome110")
                    
                    # 设置代理（如果有）
                    if proxies:
                        # 提取代理URL
                        http_proxy = proxies.get('http')
                        if http_proxy:
                            session.proxies = {"http": http_proxy, "https": http_proxy}
                    
                    # 发送GET请求
                    response = session.get(
                        url,
                        headers=headers,
                        timeout=30
                    )
                    
                except Exception as e:
                    logger.error(f"curl_cffi请求失败: {str(e)}")
                    # 回退到普通请求
                    response = requests.get(url, headers=headers, proxies=proxies, timeout=30)
            else:
                # 使用普通requests发送请求
                response = requests.get(url, headers=headers, proxies=proxies, timeout=30)
            
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    posts = response_data.get('data', [])
                    
                    if posts:
                        # 随机选择一个帖子
                        random_post = random.choice(posts)
                        return random_post.get('_id')
                    
                except ValueError:
                    logger.error(f"解析帖子列表失败: {response.text[:100]}...")
            
            return None
            
        except Exception as e:
            logger.error(f"获取帖子ID出错: {str(e)}", exc_info=True)
            return None

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

    def _send_sign_notification(self, sign_dict, result):
        """
        发送签到通知
        """
        if not self._notify:
            return
            
        status = sign_dict.get("status", "未知")
        sign_time = sign_dict.get("date", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # 获取加鸡腿状态
        added_chicken = result.get("added_chicken", False)
        
        # 构建通知文本
        if "签到成功" in status:
            title = "【✅ NodeSeek论坛签到成功】"
            
            text = (
                f"📢 执行结果\n"
                f"━━━━━━━━━━\n"
                f"🕐 时间：{sign_time}\n"
                f"✨ 状态：{status}\n"
            )
            
            # 添加加鸡腿信息
            if self._auto_chicken:
                if added_chicken:
                    text += f"🍗 加鸡腿：成功\n"
                else:
                    text += f"🍗 加鸡腿：失败\n"
                    
            text += f"━━━━━━━━━━"
            
        elif "已签到" in status:
            title = "【ℹ️ NodeSeek论坛重复签到】"
            
            text = (
                f"📢 执行结果\n"
                f"━━━━━━━━━━\n"
                f"🕐 时间：{sign_time}\n"
                f"✨ 状态：{status}\n"
                f"ℹ️ 说明：今日已完成签到\n"
                f"━━━━━━━━━━"
            )
            
        else:
            title = "【❌ NodeSeek论坛签到失败】"
            text = (
                f"📢 执行结果\n"
                f"━━━━━━━━━━\n"
                f"🕐 时间：{sign_time}\n"
                f"❌ 状态：{status}\n"
                f"━━━━━━━━━━\n"
                f"💡 可能的解决方法\n"
                f"• 检查Cookie是否过期\n"
                f"• 确认站点是否可访问\n"
                f"• 检查代理设置是否正确\n"
                f"• 尝试手动登录网站\n"
                f"━━━━━━━━━━"
            )
            
        # 发送通知
        self.post_message(
            mtype=NotificationType.SiteMessage,
            title=title,
            text=text
        )
    
    def _save_last_sign_date(self):
        """
        保存最后一次成功签到的日期和时间
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.save_data('last_sign_date', now)
        logger.info(f"记录签到成功时间: {now}")
        
    def _is_already_signed_today(self):
        """
        检查今天是否已经成功签到过
        只有当今天已经成功签到时才返回True
        """
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 获取历史记录
        history = self.get_data('sign_history') or []
        
        # 检查今天的签到记录
        today_records = [
            record for record in history 
            if record.get("date", "").startswith(today) 
            and record.get("status") in ["签到成功", "已签到"]
        ]
        
        if today_records:
            return True
            
        # 获取最后一次签到的日期和时间
        last_sign_date = self.get_data('last_sign_date')
        if last_sign_date:
            try:
                last_sign_datetime = datetime.strptime(last_sign_date, '%Y-%m-%d %H:%M:%S')
                last_sign_day = last_sign_datetime.strftime('%Y-%m-%d')
                
                # 如果最后一次签到是今天且是成功的
                if last_sign_day == today:
                    return True
            except Exception as e:
                logger.error(f"解析最后签到日期时出错: {str(e)}")
        
        return False

    def get_state(self) -> bool:
        return self._enabled

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            logger.info(f"注册定时服务: {self._cron}")
            return [{
                "id": "nodeseeksign",
                "name": "NodeSeek论坛签到",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.sign,
                "kwargs": {}
            }]
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        # 检测是否安装了curl_cffi库
        curl_cffi_status = "✅ 已安装" if HAS_CURL_CFFI else "❌ 未安装 (无法绕过CloudFlare防护)"
        
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
                                            'model': 'random_choice',
                                            'label': '随机奖励',
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
                                            'model': 'auto_chicken',
                                            'label': '自动加鸡腿',
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
                                            'model': 'use_proxy',
                                            'label': '使用代理',
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
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': f'【使用教程】\n1. 登录NodeSeek论坛网站，按F12打开开发者工具\n2. 在"网络"或"应用"选项卡中复制Cookie\n3. 粘贴Cookie到上方输入框\n4. 设置签到时间，建议早上8点(0 8 * * *)\n5. 启用插件并保存\n\n【功能说明】\n• 随机奖励：开启则使用随机奖励，关闭则使用固定奖励\n• 自动加鸡腿：自动给热门帖子加鸡腿\n• 使用代理：开启则使用系统配置的代理服务器访问NodeSeek\n\n【CloudFlare绕过】\n• curl_cffi库状态: {curl_cffi_status}\n• 如需安装: pip install curl_cffi>=0.5.9'
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
            "auto_chicken": True,
            "random_choice": True,
            "history_days": 30,
            "use_proxy": True
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
                    # 消息列
                    {
                        'component': 'td',
                        'text': history.get('message', '-')
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
                        'text': '📊 NodeSeek论坛签到历史'
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
                                                    {'component': 'th', 'text': '消息'}
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
        """
        退出插件，停止定时任务
        """
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