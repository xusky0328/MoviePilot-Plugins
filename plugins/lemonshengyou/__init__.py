import pytz
import time
import requests
import threading
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Optional
from urllib.parse import urljoin
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from ruamel.yaml import CommentedMap

from app.core.config import settings
from app.core.event import eventmanager
from app.db.site_oper import SiteOper
from app.helper.sites import SitesHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.timer import TimerUtils

class lemonshengyou(_PluginBase):
    # 插件名称
    plugin_name = "柠檬站点神游"
    # 插件描述
    plugin_desc = "自动完成柠檬站点每日免费神游三清天，获取奖励。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/madrays/MoviePilot-Plugins/main/icons/lemon.ico"
    # 插件版本
    plugin_version = "0.9.2"
    # 插件作者
    plugin_author = "madrays"
    # 作者主页
    author_url = "https://github.com/madrays"
    # 插件配置项ID前缀
    plugin_config_prefix = "lemonshengyou_"
    # 加载顺序
    plugin_order = 0
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    sites: SitesHelper = None
    siteoper: SiteOper = None
    
    # 定时器
    _scheduler: Optional[BackgroundScheduler] = None

    # 配置属性
    _enabled: bool = False
    _cron: str = ""
    _onlyonce: bool = False
    _notify: bool = False
    _retry_count: int = 3
    _retry_interval: int = 5
    _history_days: int = 7
    _lemon_site: str = None
    _lock: Optional[threading.Lock] = None
    _running: bool = False

    def init_plugin(self, config: Optional[dict] = None):
        self._lock = threading.Lock()
        self.sites = SitesHelper()
        self.siteoper = SiteOper()

        # 停止现有任务
        self.stop_service()

        if config:
            self._enabled = bool(config.get("enabled", False))
            self._cron = str(config.get("cron", ""))
            self._onlyonce = bool(config.get("onlyonce", False))
            self._notify = bool(config.get("notify", False))
            self._retry_count = int(config.get("retry_count", 3))
            self._retry_interval = int(config.get("retry_interval", 5))
            self._history_days = int(config.get("history_days", 7))
            self._lemon_site = config.get("lemon_site")

            # 保存配置
            self.__update_config()

        # 加载模块
        if self._enabled or self._onlyonce:
            # 立即运行一次
            if self._onlyonce:
                try:
                    # 定时服务
                    self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                    logger.info("柠檬神游服务启动，立即运行一次")
                    self._scheduler.add_job(func=self.do_shenyou, trigger='date',
                                         run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                         name="柠檬神游服务")

                    # 关闭一次性开关
                    self._onlyonce = False
                    # 保存配置
                    self.__update_config()

                    # 启动任务
                    if self._scheduler and self._scheduler.get_jobs():
                        self._scheduler.print_jobs()
                        self._scheduler.start()
                except Exception as e:
                    logger.error(f"启动一次性任务失败: {str(e)}")

    def __update_config(self):
        """
        更新配置
        """
        self.update_config({
            "enabled": self._enabled,
            "notify": self._notify,
            "cron": self._cron,
            "onlyonce": self._onlyonce,
            "retry_count": self._retry_count,
            "retry_interval": self._retry_interval,
            "history_days": self._history_days,
            "lemon_site": self._lemon_site
        })

    def get_state(self) -> bool:
        return self._enabled

    def get_command(self) -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
        if self._enabled and self._cron:
            try:
                # 检查是否为5位cron表达式
                if str(self._cron).strip().count(" ") == 4:
                    return [{
                        "id": "LemonShenYou",
                        "name": "柠檬神游服务",
                        "trigger": CronTrigger.from_crontab(self._cron),
                        "func": self.do_shenyou,
                        "kwargs": {}
                    }]
                else:
                    logger.error("cron表达式格式错误")
                    return []
            except Exception as err:
                logger.error(f"定时任务配置错误：{str(err)}")
                return []
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面
        """
        # 获取支持的站点列表
        site_options = []
        for site in self.sites.get_indexers():
            if not site.get("public"):
                site_name = site.get("name", "")
                if "柠檬" in site_name:
                    site_options.append({
                        "title": site_name,
                        "value": site.get("id")
                    })
        
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
                                            'label': '启用插件'
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
                                            'label': '发送通知'
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
                                            'label': '立即运行一次'
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
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'lemon_site',
                                            'label': '选择站点',
                                            'items': site_options
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
                                            'label': '执行周期',
                                            'placeholder': '5位cron表达式，默认每天8点'
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
                                            'model': 'retry_count',
                                            'label': '最大重试次数'
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
                                            'model': 'retry_interval',
                                            'label': '重试间隔(秒)'
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
                                            'label': '历史保留天数'
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
            "notify": False,
            "cron": "0 8 * * *",
            "onlyonce": False,
            "retry_count": 3,
            "retry_interval": 5,
            "history_days": 7,
            "lemon_site": None
        }

    def get_page(self) -> List[dict]:
        pass

    def stop_service(self):
        """退出插件"""
        try:
            if self._scheduler:
                if self._lock and hasattr(self._lock, 'locked') and self._lock.locked():
                    logger.info("等待当前任务执行完成...")
                    try:
                        self._lock.acquire()
                        self._lock.release()
                    except:
                        pass
                if hasattr(self._scheduler, 'remove_all_jobs'):
                    self._scheduler.remove_all_jobs()
                if hasattr(self._scheduler, 'running') and self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"退出插件失败：{str(e)}")

    @eventmanager.register(EventType.SiteDeleted)
    def site_deleted(self, event):
        """
        删除对应站点选中
        """
        site_id = event.event_data.get("site_id")
        if site_id and str(site_id) == str(self._lemon_site):
            self._lemon_site = None
            self._enabled = False
            # 保存配置
            self.__update_config()

    def do_shenyou(self):
        """
        执行神游
        """
        if not self._lock:
            self._lock = threading.Lock()
            
        if not self._lock.acquire(blocking=False):
            logger.warning("已有任务正在执行，本次调度跳过！")
            return
            
        try:
            self._running = True
            
            # 获取站点信息
            if not self._lemon_site:
                logger.error("未配置柠檬站点！")
                return
                
            site_info = None
            for site in self.sites.get_indexers():
                if str(site.get("id")) == str(self._lemon_site):
                    site_info = site
                    break
                    
            if not site_info:
                logger.error("未找到配置的柠檬站点信息！")
                return
                
            # 执行神游
            success = False
            error_msg = None
            rewards = []
            
            for i in range(self._retry_count):
                try:
                    success, error_msg, rewards = self.__do_shenyou(site_info)
                    if success:
                        break
                    logger.error(f"第{i+1}次神游失败：{error_msg}")
                    if i < self._retry_count - 1:
                        time.sleep(self._retry_interval)
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"第{i+1}次神游出错：{error_msg}")
                    if i < self._retry_count - 1:
                        time.sleep(self._retry_interval)
            
            # 发送通知
            if self._notify:
                title = "🌈 柠檬神游任务"
                text = f"站点：{site_info.get('name')}\n"
                if success:
                    text += "状态：✅ 神游成功\n"
                    if rewards:
                        text += "\n🎁 获得奖励：\n"
                        for reward in rewards:
                            text += f"- {reward}\n"
                else:
                    text += f"状态：❌ 神游失败\n原因：{error_msg}"
                
                text += f"\n⏱️ {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
                
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title=title,
                    text=text
                )
                
        except Exception as e:
            logger.error(f"神游任务执行出错：{str(e)}")
        finally:
            self._running = False
            if self._lock and hasattr(self._lock, 'locked') and self._lock.locked():
                try:
                    self._lock.release()
                except RuntimeError:
                    pass
            logger.debug("任务执行完成，锁已释放")

    def __do_shenyou(self, site_info: CommentedMap) -> Tuple[bool, Optional[str], List[str]]:
        """
        执行神游操作
        :return: (是否成功, 错误信息, 奖励列表)
        """
        site_name = site_info.get("name", "").strip()
        site_url = site_info.get("url", "").strip()
        site_cookie = site_info.get("cookie", "").strip()
        ua = site_info.get("ua", "").strip()
        proxies = settings.PROXY if site_info.get("proxy") else None

        if not all([site_name, site_url, site_cookie, ua]):
            return False, "站点信息不完整", []

        # 构建请求Session
        session = requests.Session()
        
        # 配置重试
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[403, 404, 500, 502, 503, 504],
            allowed_methods=frozenset(['GET', 'POST']),
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        
        # 设置请求头
        session.headers.update({
            'User-Agent': ua,
            'Cookie': site_cookie,
            'Referer': site_url
        })
        
        if proxies:
            session.proxies = proxies
            
        try:
            # 1. 访问神游页面
            lottery_url = urljoin(site_url, "lottery.php")
            logger.info(f"访问神游页面: {lottery_url}")
            response = session.get(lottery_url, timeout=(3.05, 10))
            response.raise_for_status()
            
            # 使用BeautifulSoup解析页面
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找所有神游按钮
            free_button = None
            for form in soup.find_all('form', {'action': '?', 'method': 'post'}):
                type_input = form.find('input', {'name': 'type', 'value': '0'})
                if type_input:
                    button = form.find('button')
                    if button and '免费' in button.get_text():
                        if not button.has_attr('disabled'):
                            free_button = form
                        break
            
            # 查找神游记录
            lottery_list = soup.find('div', class_='lottery_list')
            if lottery_list:
                # 尝试查找当前用户的最近一次神游记录
                for item in lottery_list.find_all('div', class_='item'):
                    user_link = item.find('a', class_=['User_Name', 'PowerUser_Name', 'EliteUser_Name', 'CrazyUser_Name', 'InsaneUser_Name', 'VIP_Name', 'Uploader_Name'])
                    if user_link and 'title' in user_link.attrs:
                        username = user_link['title'].split()[0]  # 获取用户名(可能包含身份标识,只取第一部分)
                        if username == site_info.get('username'):
                            reward_text = item.get_text(strip=True)
                            if '【神游' in reward_text:  # 修改为只匹配前缀
                                # 找到了用户的神游记录
                                reward_parts = reward_text.split('-')[-1].strip()  # 获取奖励部分
                                if not free_button:  # 如果按钮是禁用的,说明今天已经神游过
                                    return False, "今天已经神游过", [reward_parts]
            
            # 如果没有免费按钮,说明今天已经神游过了
            if not free_button:
                return False, "今天已经神游过,未能获取最近奖励记录", []
                
            # 2. 执行神游 - 使用免费神游选项
            logger.info("找到免费神游按钮，执行神游操作")
            shenyou_data = {
                "type": "0"  # 0 表示免费神游
            }
            
            response = session.post(lottery_url, data=shenyou_data, timeout=(3.05, 10))
            response.raise_for_status()
            
            # 3. 解析结果
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 重新获取神游记录列表
            lottery_list = soup.find('div', class_='lottery_list')
            if lottery_list:
                # 查找最新的神游记录(应该是第一条)
                first_item = lottery_list.find('div', class_='item')
                if first_item:
                    user_link = first_item.find('a', class_=['User_Name', 'PowerUser_Name', 'EliteUser_Name', 'CrazyUser_Name', 'InsaneUser_Name', 'VIP_Name', 'Uploader_Name'])
                    if user_link and 'title' in user_link.attrs:
                        username = user_link['title'].split()[0]
                        if username == site_info.get('username'):
                            reward_text = first_item.get_text(strip=True)
                            if '【神游' in reward_text:  # 修改为只匹配前缀
                                reward_parts = reward_text.split('-')[-1].strip()
                                logger.info(f"神游成功，奖励: {reward_parts}")
                                return True, None, [reward_parts]
            
            # 如果没有找到神游记录,返回失败
            logger.warning("无法从神游记录中获取结果")
            return False, "无法获取神游结果", []
                
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {str(e)}")
            return False, f"请求失败: {str(e)}", []
        except Exception as e:
            logger.error(f"神游失败: {str(e)}")
            return False, f"神游失败: {str(e)}", []
        finally:
            session.close() 