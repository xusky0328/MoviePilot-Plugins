"""
NexusPHP站点邀请系统管理插件
"""
import os
import re
import json
import time
import threading
from typing import Any, List, Dict, Tuple, Optional
from datetime import datetime

import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.plugins import _PluginBase
from app.log import logger
from app.schemas import Response
from app.schemas.types import NotificationType, EventType
from app.db.site_oper import SiteOper
from app.helper.sites import SitesHelper

from plugins.nexusinvitee.config import ConfigManager
from plugins.nexusinvitee.data import DataManager
from plugins.nexusinvitee.utils import NotificationHelper, SiteHelper
from plugins.nexusinvitee.module_loader import ModuleLoader


class nexusinvitee(_PluginBase):
    # 插件名称
    plugin_name = "后宫管理系统"
    # 插件描述
    plugin_desc = "管理添加到MP站点的邀请系统，包括邀请名额、已邀请用户状态等"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/madrays/MoviePilot-Plugins/main/icons/nexusinvitee.png"
    # 插件版本
    plugin_version = "1.0.6"
    # 插件作者
    plugin_author = "madrays"
    # 作者主页
    author_url = "https://github.com/madrays"
    # 插件配置项ID前缀
    plugin_config_prefix = "nexusinvitee_"
    # 加载顺序
    plugin_order = 21
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _config = {}  # 配置字典
    _enabled = False
    _notify = False
    _cron = "0 9 * * *"  # 默认每天早上9点检查一次
    _onlyonce = False
    _nexus_sites = []  # 支持多选的站点列表
    
    # 站点助手
    sites: SitesHelper = None
    siteoper: SiteOper = None
    
    # 配置和数据管理器
    config_manager: ConfigManager = None
    data_manager: DataManager = None
    
    # 通知助手
    notify_helper: NotificationHelper = None
    
    # 站点处理器列表
    _site_handlers = []

    def init_plugin(self, config=None):
        """
        插件初始化
        """
        self.sites = SitesHelper()
        self.siteoper = SiteOper()
        
        # 获取数据目录
        data_path = self.get_data_path()
        
        # 确保目录存在
        if not os.path.exists(data_path):
            try:
                os.makedirs(data_path)
            except Exception as e:
                logger.error(f"创建数据目录失败: {str(e)}")
        
        # 获取配置文件路径
        self.config_file = os.path.join(data_path, "config.json")
        
        # 初始化配置和数据管理器
        self.config_manager = ConfigManager(data_path)
        self.data_manager = DataManager(data_path)
        
        # 初始化通知助手
        self.notify_helper = NotificationHelper(self)
        
        # 加载站点处理器
        self._site_handlers = ModuleLoader.load_site_handlers()
        logger.info(f"加载了 {len(self._site_handlers)} 个站点处理器")
        
        # 从配置加载设置
        self._sync_from_file()

        # 处理配置参数
        if config:
            self._enabled = config.get("enabled", False)
            self._notify = config.get("notify", False)
            self._cron = config.get("cron", "0 9 * * *")
            self._onlyonce = config.get("onlyonce", False)
            
            # 如果配置中有站点ID
            if config.get("site_ids"):
                self._nexus_sites = config.get("site_ids", [])
            
            # 更新配置
            self._sync_to_file()
        
        # 如果启用了插件
        if self._enabled:
            # 检查是否配置了站点
            if not self._nexus_sites:
                logger.warning("未选择任何站点，插件将无法正常工作")
            else:
                logger.info(f"后宫管理系统初始化完成，已选择 {len(self._nexus_sites)} 个站点")
                
            # 处理立即运行一次开关
            if self._onlyonce:
                logger.info("立即运行一次开关已开启，3秒后开始刷新数据...")
                # 关闭开关
                self._onlyonce = False
                self._config['onlyonce'] = False
                self._sync_to_file()
                # 延迟3秒执行，避免与初始化冲突
                t = threading.Timer(3, self._async_refresh_sites)
                t.daemon = True
                t.start()

    def _save_config(self):
        """
        保存配置
        """
        config = {
            "enabled": self._enabled,
            "notify": self._notify,
            "cron": self._cron,
            "onlyonce": self._onlyonce,
            "site_ids": self._nexus_sites
        }
        return self.config_manager.update_config(config)
    
    def _async_refresh_sites(self):
        """
        异步刷新站点数据
        """
        # 创建新线程执行刷新
        t = threading.Thread(target=self._background_refresh)
        # 设置为守护线程，随主线程退出而退出
        t.daemon = True
        # 启动线程
        t.start()
    
    def _background_refresh(self):
        """
        后台刷新处理函数
        """
        # 执行刷新，但不在这里发送通知（由refresh_all_sites负责发送）
        self.refresh_all_sites()

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled

    def get_command(self) -> List[Dict[str, Any]]:
        """
        注册插件命令
        """
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API
        """
        return [{
            "path": "/config",
            "endpoint": self.get_config,
            "methods": ["GET"],
            "summary": "获取配置",
            "description": "获取后宫管理系统配置数据",
        }, {
            "path": "/update_config",
            "endpoint": self.update_config,
            "methods": ["POST"],
            "summary": "更新配置",
            "description": "更新后宫管理系统配置数据",
        }, {
            "path": "/get_invitees",
            "endpoint": self.get_invitees,
            "methods": ["GET"],
            "summary": "获取被邀请人列表",
            "description": "获取所有站点的被邀请人列表及状态",
        }, {
            "path": "/refresh_data",
            "endpoint": self.refresh_data,
            "methods": ["GET"],
            "summary": "刷新数据",
            "description": "强制刷新所有站点数据",
        }]

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        """
        获取插件仪表盘元信息
        """
        return [{
            "key": "nexusinvitee_dashboard",
            "name": "后宫管理系统"
        }]
        
    def get_dashboard(self, key: str, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        """
        获取插件仪表盘页面
        """
        if key != "nexusinvitee_dashboard":
            return None
            
        try:
            # 从data_manager获取站点数据
            cached_data = {}
            site_data = self.data_manager.get_site_data()
            for site_name, site_info in site_data.items():
                cached_data[site_name] = site_info
                
            last_update = "未知"
            if cached_data:
                # 找出最新更新时间
                update_times = [cache.get("last_update", 0)
                                for cache in cached_data.values() if cache]
                if update_times:
                    last_update = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(max(update_times)))

            # 计算所有站点统计信息
            total_sites = len(cached_data)
            total_invitees = 0
            total_low_ratio = 0
            total_banned = 0
            total_perm_invites = 0
            total_temp_invites = 0

            for site_name, cache in cached_data.items():
                site_cache_data = cache.get("data", {})
                # 处理数据结构
                invitees = site_cache_data.get("invitees", [])
                if not invitees and "data" in site_cache_data:
                    invitees = site_cache_data.get("data", {}).get("invitees", [])
                
                invite_status = site_cache_data.get("invite_status", {})
                if not invite_status.get("permanent_count") and "data" in site_cache_data:
                    invite_status = site_cache_data.get("data", {}).get("invite_status", {})
                
                # 统计各项数据
                total_invitees += len(invitees)
                total_perm_invites += invite_status.get("permanent_count", 0)
                total_temp_invites += invite_status.get("temporary_count", 0)
                
                # 计算分享率低和被ban的用户
                for invitee in invitees:
                    # 检查是否被ban
                    if invitee.get('enabled', '').lower() == 'no':
                        total_banned += 1

                    # 检查分享率是否低于1
                    ratio_str = invitee.get('ratio', '')
                    if ratio_str != '∞' and ratio_str.lower() != 'inf.' and ratio_str.lower() != 'inf':
                        try:
                            # 标准化字符串，替换逗号为点
                            ratio_str = ratio_str.replace(',', '.')
                            ratio_val = float(ratio_str) if ratio_str else 0
                            if ratio_val < 1:
                                total_low_ratio += 1
                        except (ValueError, TypeError):
                            # 转换错误时记录警告
                            logger.warning(f"分享率转换失败: {ratio_str}")
                                
            # 列配置
            col_config = {
                "cols": 16,
                "md": 12
            }
            
            # 全局配置
            global_config = {
                "refresh": 3600,  # 1小时自动刷新一次
                "title": "后宫总览",
                "subtitle": f"更新时间: {last_update}",
                "border": False
            }
            
            # 页面元素
            elements = []
            
            # 添加全局统计信息 - 与详情页完全一致
            elements.append({
                "component": "VCard",
                "props": {
                    "class": "mb-4",
                    "variant": "outlined"
                },
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "后宫总览"
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 3},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#2196F3",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-web"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 primary--text"},
                                                    "text": str(total_sites)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "站点数量"
                                                }
                                            ]
                                        }]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 2},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#03A9F4",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-human-queue"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 info--text"},
                                                    "text": str(total_invitees)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "后宫成员"
                                                }
                                            ]
                                        }]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 2},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#9C27B0",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-ticket-confirmation"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 purple--text"},
                                                    "text": str(total_perm_invites)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "永久邀请数"
                                                }
                                            ]
                                        }]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 2},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#E91E63",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-ticket"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 pink--text"},
                                                    "text": str(total_temp_invites)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "临时邀请数"
                                                }
                                            ]
                                        }]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 1.5},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#FF9800",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-alert-circle"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 warning--text"},
                                                    "text": str(total_low_ratio)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "低分享率"
                                                }
                                            ]
                                        }]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 1.5},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#F44336",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-account-cancel"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 error--text"},
                                                    "text": str(total_banned)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "已禁用"
                                                }
                                            ]
                                        }]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            })
            
            # 如果没有数据，显示提示信息
            if not cached_data:
                elements = [{
                    "component": "VAlert",
                    "props": {
                        "type": "info",
                        "variant": "tonal",
                        "text": "暂无站点数据，请先在配置中选择要管理的站点。"
                    }
                }]
            
            return col_config, global_config, elements
            
        except Exception as e:
            logger.error(f"生成仪表盘失败: {str(e)}")
            return {
                "cols": 12,
                "md": 6
            }, {
                "refresh": 3600,
                "title": "后宫管理系统",
                "subtitle": "发生错误"
            }, [{
                "component": "VAlert",
                "props": {
                    "type": "error",
                    "variant": "tonal",
                    "text": f"生成仪表盘失败: {str(e)}"
                }
        }]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        配置页面
        """
        # 获取支持的站点列表
        site_options = []
        for site in self.sites.get_indexers():
            site_name = site.get("name", "")
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
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'warning',
                                            'variant': 'tonal',
                                            'density': 'compact',
                                            'text': '注意！"立即运行一次"开关：由于数据存储特殊性，使用后需手动关闭，请在数据刷新后再次关闭此开关并保存',
                                            'class': 'mt-2 mb-4'
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
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'site_ids',
                                            'label': '选择站点',
                                            'items': site_options,
                                            'multiple': True,
                                            'chips': True,
                                            'clearable': True,
                                            'persistent-hint': True,
                                            'hint': '选择要管理的站点，支持多选'
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
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期'
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
                                            'text': '【使用说明】\n本插件适配各站点中，不排除bug，目前尚未适配mt、ptt、ttg等，以及我没有的站点，欢迎大佬们报错时提交错误站点的邀请页和发邀页html结构\n1. 选择要管理的站点（支持多选）\n2. 设置执行周期，建议每天早上9点执行一次\n3. 可选择开启通知，在状态变更时收到通知\n4. 【特别说明】"立即运行一次"开关：由于配置特殊性，使用后需手动关闭，请在数据刷新后再次关闭此开关并保存\n5. 本插件不会自动刷新数据，打开详情页也不会自动刷新数据，需手动刷新'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": self._enabled,
            "notify": self._notify,
            "cron": "0 9 * * *",
            "onlyonce": False,
            "site_ids": self._nexus_sites
        }

    def _is_nexusphp(self, site_url: str) -> bool:
        """
        判断是否为NexusPHP站点
        """
        # 简单判断，后续可以添加更多特征
        return "php" in site_url.lower()

    def get_page(self) -> List[dict]:
        """
        详情页面
        """
        try:
            # 从data_manager获取站点数据
            cached_data = {}
            site_data = self.data_manager.get_site_data()
            for site_name, site_info in site_data.items():
                cached_data[site_name] = site_info
                
            last_update = "未知"
            if cached_data:
                # 找出最新更新时间
                update_times = [cache.get("last_update", 0)
                                for cache in cached_data.values() if cache]
                if update_times:
                    last_update = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(max(update_times)))

            # 准备页面内容
            page_content = []
            
            # 添加样式，优化表格
            page_content.append({
                "component": "style",
                "text": """
                .site-invitees-table {
                    width: auto !important;
                }
                .site-invitees-table th, .site-invitees-table td {
                    padding: 4px 8px !important;
                    white-space: nowrap;
                }
                """
            })

            # 添加头部信息和提示
            page_content.append({
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "text": f"后宫管理系统 - 共 {len(cached_data)} 个站点，数据最后更新时间: {last_update}\n注: 本插件不会自动刷新数据，只显示在MP中已配置并选择的站点",
                    "variant": "tonal",
                    "class": "mb-4"
                }
            })

            # 添加说明提示
            page_content.append({
                "component": "VAlert",
                "props": {
                    "type": "warning",
                    "text": "如需刷新数据，请在配置页面打开\"立即运行一次\"开关并保存，使用后记得关闭该开关并再次保存",
                    "variant": "tonal",
                    "class": "mb-4"
                }
            })

            # 准备站点卡片
            cards = []
            
            # 计算所有站点统计信息
            total_sites = len(cached_data)
            total_invitees = 0
            total_low_ratio = 0
            total_banned = 0
            total_perm_invites = 0
            total_temp_invites = 0

            for site_name, cache in cached_data.items():
                site_cache_data = cache.get("data", {})
                # 处理数据结构
                invitees = site_cache_data.get("invitees", [])
                if not invitees and "data" in site_cache_data:
                    invitees = site_cache_data.get("data", {}).get("invitees", [])
                
                invite_status = site_cache_data.get("invite_status", {})
                if not invite_status.get("permanent_count") and "data" in site_cache_data:
                    invite_status = site_cache_data.get("data", {}).get("invite_status", {})
                    
                # 统计各项数据
                total_invitees += len(invitees)
                total_perm_invites += invite_status.get("permanent_count", 0)
                total_temp_invites += invite_status.get("temporary_count", 0)

                # 计算分享率低和被ban的用户
                for invitee in invitees:
                    # 检查是否被ban
                    if invitee.get('enabled', '').lower() == 'no':
                        total_banned += 1

                    # 检查分享率是否低于1
                    ratio_str = invitee.get('ratio', '')
                    if ratio_str != '∞' and ratio_str.lower() != 'inf.' and ratio_str.lower() != 'inf':
                        try:
                            # 标准化字符串，替换逗号为点
                            ratio_str = ratio_str.replace(',', '.')
                            ratio_val = float(ratio_str) if ratio_str else 0
                            if ratio_val < 1:
                                total_low_ratio += 1
                        except (ValueError, TypeError):
                            # 转换错误时记录警告
                            logger.warning(f"分享率转换失败: {ratio_str}")

            # 添加全局统计信息
            page_content.append({
                "component": "VCard",
                "props": {
                    "class": "mb-4",
                    "variant": "outlined"
                },
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "后宫总览"
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 3},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#2196F3",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-web"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 primary--text"},
                                                    "text": str(total_sites)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "站点数量"
                                                }
                                            ]
                                        }]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 2},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#03A9F4",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-human-queue"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 info--text"},
                                                    "text": str(total_invitees)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "后宫成员"
                                                }
                                            ]
                                        }]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 2},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#9C27B0",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-ticket-confirmation"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 purple--text"},
                                                    "text": str(total_perm_invites)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "永久邀请数"
                                                }
                                            ]
                                        }]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 2},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#E91E63",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-ticket"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 pink--text"},
                                                    "text": str(total_temp_invites)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "临时邀请数"
                                                }
                                            ]
                                        }]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 1.5},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#FF9800",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-alert-circle"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 warning--text"},
                                                    "text": str(total_low_ratio)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "低分享率"
                                                }
                                            ]
                                        }]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 1.5},
                                        "content": [{
                                            "component": "div",
                                            "props": {
                                                "class": "text-center"
                                            },
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "size": "36",
                                                        "color": "#F44336",
                                                        "class": "mb-2"
                                                    },
                                                    "text": "mdi-account-cancel"
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-h5 error--text"},
                                                    "text": str(total_banned)
                                                },
                                                {
                                                    "component": "div",
                                                    "props": {"class": "text-caption"},
                                                    "text": "已禁用"
                                                }
                                            ]
                                        }]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            })

            for site_name, cache in cached_data.items():
                invite_data = cache.get("data", {})

                # 获取站点信息
                site_info = None
                for site in self.sites.get_indexers():
                    if site.get("name") == site_name:
                        site_info = site
                        break
                
                if site_info:
                    # 获取站点数据
                    site_cache_data = cache.get("data", {})
                    # 处理数据结构
                    invitees = site_cache_data.get("invitees", [])
                    if not invitees and "data" in site_cache_data:
                        invitees = site_cache_data.get("data", {}).get("invitees", [])
                    
                    invite_status = site_cache_data.get("invite_status", {})
                    if not invite_status.get("permanent_count") and "data" in site_cache_data:
                        invite_status = site_cache_data.get("data", {}).get("invite_status", {})
                    
                    # 计算此站点的统计信息
                    banned_count = sum(1 for i in invitees if i.get(
                        'enabled', '').lower() == 'no')
                    low_ratio_count = 0

                    for invitee in invitees:
                        ratio_str = invitee.get('ratio', '')
                        if ratio_str != '∞' and ratio_str.lower() != 'inf.' and ratio_str.lower() != 'inf':
                            try:
                                # 标准化字符串，替换逗号为点
                                ratio_str = ratio_str.replace(',', '.')
                                ratio_val = float(
                                    ratio_str) if ratio_str else 0
                                if ratio_val < 1:
                                    low_ratio_count += 1
                            except (ValueError, TypeError):
                                # 转换错误时记录警告
                                logger.warning(f"分享率转换失败: {ratio_str}")

                    # 合并站点信息和数据到一张卡片
                    site_card = {
                        "component": "VCard",
                        "props": {
                            "class": "mb-4",
                            "variant": "outlined",
                            "elevation": "1"
                        },
                        "content": [
                            # 站点信息头部
                            {
                                "component": "VCardItem",
                                "props": {
                                    "class": "py-2"
                                },
                                "content": [
                                    {
                                        "component": "VCardTitle",
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {
                                                    "class": "d-flex align-center"
                                                },
                                                "content": [
                                                    {
                                                        "component": "VIcon",
                                                        "props": {
                                                            "color": "primary",
                                                            "size": "24",
                                                            "class": "mr-2"
                                                        },
                                                        "text": "mdi-crown"
                                                    },
                                                    {
                                                        "component": "span",
                                                        "props": {
                                                            "class": "text-h6"
                                                        },
                                                        "text": site_info.get("name")
                                                    },
                                                    {
                                                        "component": "VSpacer"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "color": "error",
                                                                    "class": "mr-1"
                                                                },
                                                                "text": "mdi-alert-circle" if low_ratio_count > 0 else ""
                                                            },
                                                            {
                                                                "component": "span",
                                                                "props": {"class": "text-caption mr-2"},
                                                                "text": f"{low_ratio_count}人低分享" if low_ratio_count > 0 else ""
                                                            },
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "color": "error",
                                                                    "class": "mr-1"
                                                                },
                                                                "text": "mdi-block-helper" if banned_count > 0 else ""
                                                            },
                                                            {
                                                                "component": "span",
                                                                "props": {"class": "text-caption"},
                                                                "text": f"{banned_count}人禁用" if banned_count > 0 else ""
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            # 邀请状态统计
                            {
                                "component": "VCardText",
                                "props": {
                                    "class": "pt-2 pb-0"
                                },
                                "content": [
                                    {
                                        "component": "VRow",
                                        "props": {
                                            "dense": True
                                        },
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 3},
                                                "content": [{
                                                    "component": "div",
                                                    "props": {
                                                        "class": "d-flex align-center"
                                                    },
                                                    "content": [
                                                        {
                                                            "component": "VIcon",
                                                    "props": {
                                                                "size": "24",
                                                                "color": "#9C27B0",
                                                                "class": "mr-2"
                                                    },
                                                            "text": "mdi-ticket-confirmation"
                                                        },
                                                        {
                                                            "component": "div",
                                                    "content": [
                                                        {
                                                            "component": "div",
                                                                    "props": {"class": "text-body-1 font-weight-medium purple--text"},
                                                                    "text": str(invite_status.get("permanent_count", 0))
                                                        },
                                                        {
                                                            "component": "div",
                                                            "props": {"class": "text-caption"},
                                                            "text": "永久邀请"
                                                                }
                                                            ]
                                                        }
                                                    ]
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 3},
                                                "content": [{
                                                    "component": "div",
                                                    "props": {
                                                        "class": "d-flex align-center"
                                                    },
                                                    "content": [
                                                        {
                                                            "component": "VIcon",
                                                            "props": {
                                                                "size": "24",
                                                                "color": "#E91E63",
                                                                "class": "mr-2"
                                                            },
                                                            "text": "mdi-ticket"
                                                        },
                                                        {
                                                            "component": "div",
                                                            "content": [
                                                                {
                                                                    "component": "div",
                                                                    "props": {"class": "text-body-1 font-weight-medium pink--text"},
                                                                    "text": str(invite_status.get("temporary_count", 0))
                                                        },
                                                        {
                                                            "component": "div",
                                                            "props": {"class": "text-caption"},
                                                            "text": "临时邀请"
                                                                }
                                                            ]
                                                        }
                                                    ]
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 3},
                                                "content": [{
                                                    "component": "div",
                                                    "props": {
                                                        "class": "d-flex align-center"
                                                    },
                                                    "content": [
                                                        {
                                                            "component": "VIcon",
                                                            "props": {
                                                                "size": "24",
                                                                "color": "#4CAF50",
                                                                "class": "mr-2"
                                                            },
                                                            "text": "mdi-account-group"
                                                        },
                                                        {
                                                            "component": "div",
                                                            "content": [
                                                                {
                                                                    "component": "div",
                                                                    "props": {"class": "text-body-1 font-weight-medium success--text"},
                                                                    "text": str(len(invitees))
                                                        },
                                                        {
                                                            "component": "div",
                                                            "props": {"class": "text-caption"},
                                                                    "text": "邀请人数"
                                                                }
                                                            ]
                                                        }
                                                    ]
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 3},
                                                "content": [{
                                                    "component": "div",
                                                    "props": {
                                                        "class": "d-flex align-center"
                                                    },
                                                    "content": [
                                                        {
                                                            "component": "VIcon",
                                                            "props": {
                                                                "size": "24",
                                                                "color": "#4CAF50" if invite_status.get("can_invite") else "#F44336",
                                                                "class": "mr-2"
                                                            },
                                                            "text": "mdi-check-circle" if invite_status.get("can_invite") else "mdi-close-circle"
                                                        },
                                                        {
                                                            "component": "div",
                                                            "content": [
                                                                {
                                                                    "component": "div",
                                                                    "props": {"class": "text-body-1 font-weight-medium " + 
                                                                            ("success--text" if invite_status.get("can_invite") else "error--text")},
                                                                    "text": "可邀请" if invite_status.get("can_invite") else "不可邀请"
                                                        },
                                                        {
                                                            "component": "div",
                                                            "props": {"class": "text-caption"},
                                                            "text": "邀请权限"
                                                                }
                                                            ]
                                                        }
                                                    ]
                                                }]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }

                    # 添加错误信息或不可邀请原因的显示部分
                    # 获取错误信息和不可邀请原因
                    error_message = cache.get("error", "")
                    invite_status = site_cache_data.get("invite_status", {})
                    if not invite_status.get("can_invite") is not None and "data" in site_cache_data:
                        invite_status = site_cache_data.get("data", {}).get("invite_status", {})
                    can_invite = invite_status.get("can_invite", False)
                    reason = invite_status.get("reason", "")

                    # 只有当不可邀请或有错误信息时才显示
                    if (not can_invite and reason) or error_message:
                        site_card["content"].insert(2, {
                            "component": "VCardText",
                            "props": {
                                "class": "py-1"
                            },
                            "content": [
                                {
                                    "component": "VAlert",
                                    "props": {
                                        "type": "warning",
                                        "variant": "tonal",
                                        "density": "compact",
                                        "class": "my-1"
                                    },
                                    "text": error_message or f"不可邀请原因: {reason}"
                                }
                            ]
                        })

                    # 只有在有邀请列表时才添加表格
                    if invitees:
                        table_rows = []
                        for invitee in invitees:
                            # 判断用户是否被ban或分享率较低
                            is_banned = invitee.get(
                                'enabled', '').lower() == 'no'
                            is_low_ratio = False

                            # 处理分享率
                            ratio_str = invitee.get('ratio', '')
                            if ratio_str != '∞' and ratio_str.lower() != 'inf.' and ratio_str.lower() != 'inf':
                                try:
                                    # 标准化字符串，替换逗号为点
                                    ratio_str = ratio_str.replace(',', '.')
                                    # 尝试转换为浮点数
                                    ratio_val = float(
                                        ratio_str) if ratio_str else 0
                                    is_low_ratio = ratio_val < 1
                                except (ValueError, TypeError):
                                    # 转换失败不做特殊处理
                                    logger.warning(f"分享率转换失败: {ratio_str}")
                                    pass

                            row_class = ""
                            if is_banned:
                                row_class = "bg-error-lighten-4"
                            elif is_low_ratio:
                                row_class = "bg-warning-lighten-4"

                            # 判断分享率样式
                            ratio_class = ""
                            if ratio_str == '∞' or ratio_str.lower() == 'inf.' or ratio_str.lower() == 'inf':
                                ratio_class = "text-success"
                            else:
                                try:
                                    ratio_val = float(ratio_str.replace(',', '.')) if ratio_str else 0
                                    ratio_class = "text-success" if ratio_val >= 1 else "text-error font-weight-bold"
                                except (ValueError, TypeError):
                                    ratio_class = ""

                            # 创建行
                            table_rows.append({
                                "component": "tr",
                                "props": {
                                    "class": row_class
                                },
                                "content": [
                                    {
                                        "component": "td",
                                        "content": [{
                                            "component": "VBtn",
                                            "props": {
                                                "variant": "text",
                                                "href": invitee.get("profile_url", ""),
                                                "target": "_blank",
                                                "density": "compact"
                                            },
                                            "text": invitee.get("username", "")
                                        }]
                                    },
                                    {"component": "td",
                                        "text": invitee.get("email", "")},
                                    {"component": "td", "text": invitee.get(
                                        "uploaded", "")},
                                    {"component": "td", "text": invitee.get(
                                        "downloaded", "")},
                                    {
                                        "component": "td",
                                        "props": {
                                            "class": ratio_class
                                        },
                                        "text": invitee.get("ratio", "")
                                    },
                                    {"component": "td", "text": invitee.get(
                                        "seeding", "")},
                                    {"component": "td", "text": invitee.get(
                                        "seeding_size", "")},
                                    {"component": "td", "text": invitee.get(
                                        "seed_magic", "") or invitee.get("magic", "") or invitee.get("seed_time", "")},
                                    {"component": "td", "text": invitee.get(
                                        "seed_bonus", "") or invitee.get("invitee_bonus", "") or invitee.get("bonus", "")},
                                    {"component": "td", "text": invitee.get(
                                        "last_seed_report", "") or invitee.get("last_seen", "")},
                                    {
                                        "component": "td",
                                        "props": {
                                            "class": ("text-success" if invitee.get('status') == '已确认' else "") +
                                                     (" text-error font-weight-bold" if invitee.get('enabled', '').lower() == 'no' else "")
                                        },
                                        "text": invitee.get("status", "") + (" (已禁用)" if invitee.get('enabled', '').lower() == 'no' else "")
                                    }
                                ]
                            })

                        site_card["content"].append({
                            "component": "VCardText",
                            "props": {
                                "class": "pt-0"
                            },
                            "content": [{
                                "component": "VTable",
                                "props": {
                                    "hover": True,
                                    "density": "compact",
                                    "fixed-header": False,
                                    "class": "site-invitees-table",
                                },
                                "content": [{
                                    "component": "thead",
                                    "content": [{
                                        "component": "tr",
                                        "props": {
                                            "class": "bg-primary-lighten-5"
                                        },
                                        "content": [
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#2196F3"
                                                                },
                                                                "text": "mdi-account"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "用户名"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#2196F3"
                                                                },
                                                                "text": "mdi-email"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "邮箱"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#4CAF50"
                                                                },
                                                                "text": "mdi-arrow-up-thick"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "上传量"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#F44336"
                                                                },
                                                                "text": "mdi-arrow-down-thick"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "下载量"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#FF9800"
                                                                },
                                                                "text": "mdi-poll"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "分享率"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#2196F3"
                                                                },
                                                                "text": "mdi-database"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "做种数"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#1976D2"
                                                                },
                                                                "text": "mdi-harddisk"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "做种体积"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#3F51B5"
                                                                },
                                                                "text": "mdi-clock-outline"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "做种时魔"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#9C27B0"
                                                                },
                                                                "text": "mdi-crown"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "后宫加成"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#00BCD4"
                                                                },
                                                                "text": "mdi-calendar-clock"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "最后做种报告"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "th", 
                                                "props": {"class": "text-subtitle-2", "style": "white-space: nowrap;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {
                                                            "class": "d-flex align-center justify-center"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {
                                                                    "size": "small",
                                                                    "class": "mr-1",
                                                                    "color": "#00BCD4"
                                                                },
                                                                "text": "mdi-information"
                                                            },
                                                            {
                                                                "component": "span",
                                                                "text": "状态"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }]
                                }, {
                                    "component": "tbody",
                                    "content": table_rows
                                }]
                            }]
                        })
                    
                    cards.append(site_card)
            
            # 将站点卡片添加到页面
            page_content.extend(cards)

            # 添加说明提示
            if not cards:
                page_content.append({
                    "component": "VAlert",
                    "props": {
                        "type": "warning",
                        "text": "暂无数据，请先在配置中选择要管理的站点，并打开\"立即运行一次\"开关获取数据",
                        "variant": "tonal",
                        "class": "mt-4"
                    }
                })

            return page_content
            
        except Exception as e:
            logger.error(f"生成详情页面失败: {str(e)}")
            return [{
                "component": "VAlert",
                "props": {
                    "type": "error",
                    "text": f"生成详情页面失败: {str(e)}"
                }
            }]

    def stop_service(self):
        """
        退出插件
        """
        logger.info("后宫管理系统插件停止服务")

    def get_config(self, apikey: str) -> Response:
        """
        获取配置
        """
        if apikey != settings.API_TOKEN:
            return Response(success=False, message="API令牌错误!")
        
        try:
            config = self.config_manager.get_config()
            return Response(success=True, message="获取成功", data=config)
        except Exception as e:
            logger.error(f"获取配置失败: {str(e)}")
            return Response(success=False, message=f"获取配置失败: {str(e)}")

    def update_config(self, request: dict) -> Response:
        """
        更新配置
        """
        try:
            # 提取前端更新的配置项
            if "enabled" in request:
                self._enabled = request.get("enabled")
            if "notify" in request:
                self._notify = request.get("notify")
            if "cron" in request:
                self._cron = request.get("cron")
            if "onlyonce" in request:
                self._onlyonce = request.get("onlyonce")
            if "site_ids" in request:
                self._nexus_sites = request.get("site_ids")

            # 更新内存中的配置
            self.__update_config()
            
            # 同步到文件
            if self._sync_to_file():
                # 立即刷新数据开关
                if self._onlyonce:
                    # 关闭开关
                    self._config['onlyonce'] = False
                    self._onlyonce = False
                    self._sync_to_file()
                    # 立即刷新
                    logger.info(f"手动触发刷新站点数据...")
                    # 异步刷新数据，通知会在refresh_all_sites中发送，不需要这里发送
                    self._async_refresh_sites()
                return Response(success=True, message="更新成功")
            else:
                return Response(success=False, message="保存配置失败")
        except Exception as e:
            logger.error(f"更新配置失败: {str(e)}")
            return Response(success=False, message=f"更新配置失败: {str(e)}")

    def _get_site_invite_data(self, site_name):
        """
        获取站点邀请页面数据
        """
        try:
            # 获取站点信息
            site_info = None
            for indexer in self.sites.get_indexers():
                if indexer.get("name") == site_name:
                    site_info = indexer
                    break
                    
            if not site_info:
                logger.error(f"站点 {site_name} 信息不存在")
                return {
                    "error": "站点信息不存在",
                    "invite_status": {
                        "can_invite": False,
                        "permanent_count": 0,
                        "temporary_count": 0,
                        "reason": "站点信息不存在"
                    }
                }
                
            site_url = site_info.get("url", "").strip()
            site_cookie = site_info.get("cookie", "").strip()
            ua = site_info.get("ua", "").strip()
            site_id = site_info.get("id", "")

            # 先验证此站点是否在用户选择的站点列表中
            if str(site_id) not in [str(x) for x in self._nexus_sites]:
                logger.warning(f"站点 {site_name} 不在用户选择的站点列表中，跳过处理")
                return {
                    "error": "站点未被选择",
                    "invite_status": {
                        "can_invite": False,
                        "permanent_count": 0,
                        "temporary_count": 0,
                        "reason": "站点未被选择"
                    }
                }
            
            if not all([site_url, site_cookie, ua]):
                logger.error(f"站点 {site_name} 信息不完整")
                return {
                    "error": "站点信息不完整，请在站点管理中完善配置",
                    "invite_status": {
                        "can_invite": False,
                        "permanent_count": 0,
                        "temporary_count": 0,
                        "reason": "站点信息不完整，请在站点管理中完善配置"
                    }
                }

            # 构建请求Session
            session = requests.Session()
            session.headers.update({
                'User-Agent': ua,
                'Cookie': site_cookie,
                'Referer': site_url,
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin'
            })

            # 先测试cookie是否有效
            test_url = urljoin(site_url, "index.php")
            test_response = session.get(test_url, timeout=(5, 15))
            if test_response.status_code == 403:
                logger.error(f"站点 {site_name} 的Cookie已失效，请更新")
                return {
                    "error": "Cookie已失效，请更新站点Cookie",
                    "invite_status": {
                        "can_invite": False,
                        "permanent_count": 0,
                        "temporary_count": 0,
                        "reason": "Cookie已失效，请更新站点Cookie"
                    }
                }

            # 获取用户ID
            user_id = self._get_user_id(session, site_info)
            if not user_id:
                logger.error(f"无法获取站点 {site_name} 的用户ID")
                return {
                    "error": "无法获取用户ID，请检查站点Cookie是否有效",
                    "invite_status": {
                        "can_invite": False,
                        "permanent_count": 0,
                        "temporary_count": 0,
                        "reason": "无法获取用户ID，请检查站点Cookie是否有效"
                    }
                }

            # 根据站点类型获取数据
            if "m-team" in site_url.lower():
                # 获取API认证信息
                api_key = site_info.get("api_key")
                auth_header = site_info.get("authorization")
                
                if not api_key or not auth_header:
                    logger.error(f"站点 {site_name} API认证信息不完整")
                    return {
                        "error": "API认证信息不完整，请在站点设置中配置API Key和Authorization",
                        "invite_status": {
                            "can_invite": False,
                            "permanent_count": 0,
                            "temporary_count": 0,
                            "reason": "API认证信息不完整，请在站点设置中配置API Key和Authorization"
                        }
                    }
                
                # 更新请求头
                session.headers.update({
                    'Authorization': auth_header,
                    'API-Key': api_key
                })
                
                try:
                    # 获取站点统计数据
                    domain = site_url.split("//")[-1].split("/")[0]
                    api_url = f"https://{domain}/api/v1/site/statistic/{domain}"
                    stats_response = session.get(api_url, timeout=(10, 30))
                    stats_response.raise_for_status()
                    stats_data = stats_response.json()
                    
                    # 获取邀请页面数据
                    invite_url = urljoin(site_url, "invite")
                    invite_response = session.get(invite_url, timeout=(10, 30))
                    invite_response.raise_for_status()
                    
                    # 使用站点处理器
                    handler = ModuleLoader.get_handler_for_site(site_url)
                    if handler:
                        # 如果有匹配的站点处理器，使用处理器解析
                        return handler.parse_invite_page(site_info, session)
                    else:
                        logger.error(f"找不到适合站点 {site_name} 的处理器")
                    return {
                            "error": f"找不到适合站点 {site_name} 的处理器",
                        "invite_status": {
                            "can_invite": False,
                            "permanent_count": 0,
                            "temporary_count": 0,
                                "reason": f"找不到适合站点 {site_name} 的处理器"
                            }
                        }
                except requests.exceptions.RequestException as e:
                    logger.error(f"访问站点 {site_name} API或页面失败: {str(e)}")
                    return {
                        "error": f"访问站点API或页面失败: {str(e)}",
                        "invite_status": {
                            "can_invite": False,
                            "permanent_count": 0,
                            "temporary_count": 0,
                            "reason": f"访问站点API或页面失败: {str(e)}"
                        }
                    }
            elif "hdchina" in site_url.lower() or "totheglory" in site_url.lower():
                # 特殊站点预留处理位置 - HDChina/TTG等
                logger.warning(f"站点 {site_name} 使用特殊架构，采用通用方法尝试获取数据")
                try:
                    # 使用站点处理器
                    handler = ModuleLoader.get_handler_for_site(site_url, self._site_handlers)
                    if handler:
                        return handler.parse_invite_page(site_info, session)
                    else:
                        # 如果找不到处理器，尝试导入NexusPhpHandler作为后备处理器
                        try:
                            from plugins.nexusinvitee.sites.nexusphp import NexusPhpHandler
                            backup_handler = NexusPhpHandler()
                            return backup_handler.parse_invite_page(site_info, session)
                        except Exception as import_err:
                            logger.error(f"导入通用NexusPHP处理器失败: {str(import_err)}")
                    return {
                            "error": f"找不到匹配的站点处理器，且后备处理器加载失败",
                        "invite_status": {
                            "can_invite": False,
                            "permanent_count": 0,
                            "temporary_count": 0,
                                "reason": f"找不到匹配的站点处理器，且后备处理器加载失败"
                            },
                            "invitees": []
                        }
                except Exception as e:
                    logger.error(f"处理站点 {site_name} 失败: {str(e)}")
                    return {
                        "error": f"处理站点失败: {str(e)}",
                        "invite_status": {
                            "can_invite": False,
                            "permanent_count": 0,
                            "temporary_count": 0,
                            "reason": f"处理站点失败: {str(e)}"
                        }
                    }
            
            # 使用通用处理方式
            logger.info(f"站点 {site_name} 使用通用方式处理")
            handler = ModuleLoader.get_handler_for_site(site_url, self._site_handlers)
            if handler:
                return handler.parse_invite_page(site_info, session)
            else:
                # 如果找不到合适的处理器，使用通用NexusPHP处理器
                from plugins.nexusinvitee.sites.nexusphp import NexusPhpHandler
                default_handler = NexusPhpHandler()
                return default_handler.parse_invite_page(site_info, session)

        except Exception as e:
            logger.error(f"获取站点 {site_name} 邀请数据失败: {str(e)}")
            return {
                "error": f"获取站点邀请数据失败: {str(e)}",
                "invite_status": {
                    "can_invite": False,
                    "permanent_count": 0,
                    "temporary_count": 0,
                    "reason": f"获取站点邀请数据失败: {str(e)}"
                }
            }
            
    @staticmethod
    def get_api_handlers():
        """
        获取API接口
        """
        return {
            "/get_invitees": {"func": nexusinvitee.get_invitees, "methods": ["GET"], "desc": "获取所有站点邀请数据"},
            "/refresh": {"func": nexusinvitee.refresh_data, "methods": ["GET"], "desc": "强制刷新站点数据"}
        }

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
        if self._enabled and self._cron:
            try:
                # 检查是否为5位cron表达式
                if str(self._cron).strip().count(" ") == 4:
                    return [{
                        "id": "nexusinvitee",
                        "name": "后宫管理系统",
                        "trigger": CronTrigger.from_crontab(self._cron),
                        "func": self.refresh_all_sites,
                        "kwargs": {}
                    }]
                else:
                    logger.error("cron表达式格式错误")
                    return []
            except Exception as err:
                logger.error(f"定时任务配置错误：{str(err)}")
                return []
        return []

    def _sync_from_file(self):
        """
        从文件同步配置
        """
        # 同步配置文件到内存配置
        _config = self.config_manager.get_config()
        if _config:
            self._config = _config
            self._enabled = _config.get("enabled", False)
            self._notify = _config.get("notify", False)
            self._cron = _config.get("cron", "0 9 * * *")
            self._onlyonce = _config.get("onlyonce", False)
            self._nexus_sites = _config.get("site_ids", [])
            
            # 迁移数据到独立文件
            if "cached_data" in self._config:
                cached_data = self._config.pop("cached_data", {})
                # 将cached_data内容保存到数据文件
                for site_name, site_data in cached_data.items():
                    self.data_manager.update_site_data(site_name, site_data.get("data", {}))
                # 保存清理后的配置
                self._sync_to_file()
                logger.info("已将数据从配置文件迁移到独立数据文件")
                
            return True
        return False

    def _sync_to_file(self):
        """
        同步配置到文件
        """
        # 更新内存配置到文件
        config = {
            "enabled": self._enabled,
            "notify": self._notify,
            "cron": self._cron,
            "onlyonce": self._onlyonce,
            "site_ids": self._nexus_sites
        }
        
        return self.config_manager.update_config(config)

    def __update_config(self):
        """
        更新内存配置
        """
        # 更新内存中的配置
        self._config["enabled"] = self._enabled
        self._config["notify"] = self._notify
        self._config["cron"] = self._cron
        self._config["onlyonce"] = self._onlyonce
        self._config["site_ids"] = self._nexus_sites

    def refresh_all_sites(self) -> Dict[str, int]:
        """
        刷新所有站点数据
        """
        if not self._nexus_sites:
            logger.error("没有选择任何站点，请先在配置中选择站点")
            return {"success": 0, "error": 0}

        # 重新加载站点处理器以确保使用最新的处理逻辑
        self._site_handlers = ModuleLoader.load_site_handlers()
        logger.info(f"加载了 {len(self._site_handlers)} 个站点处理器")
            
        # 清空旧数据
        self.data_manager.save_data({})
        
        # 获取所有站点配置
        all_sites = self.sites.get_indexers()
        
        # 筛选已选择站点配置
        selected_sites = []
        for site in all_sites:
            site_id = site.get("id")
            if str(site_id) in [str(x) for x in self._nexus_sites]:
                selected_sites.append(site)
        
        logger.info(f"将刷新 {len(selected_sites)} 个站点的数据: {', '.join([site.get('name', '') for site in selected_sites])}")
        
        if not selected_sites:
            return {"success": 0, "error": 0, "message": "没有发现可供刷新的站点"}
        
        # 统计成功/失败站点数
        success_count = 0
        error_count = 0
        
        # 逐个刷新站点数据
        for site in selected_sites:
            site_name = site.get("name", "")
            site_id = site.get("id", "")
            
            logger.info(f"开始获取站点 {site_name} 的后宫数据...")
            
            site_data = self._get_site_invite_data(site_name)
            if "error" in site_data:
                logger.error(f"站点 {site_name} 数据刷新失败: {site_data.get('error', '未知错误')}")
                error_count += 1
            else:
                # 保存站点数据
                self.data_manager.update_site_data(site_name, site_data)
                logger.info(f"站点 {site_name} 数据刷新成功，已邀请 {len(site_data.get('invitees', []))} 人")
                success_count += 1
        
        # 发送通知
        if self._notify:
            total_invitees = 0
            low_ratio_count = 0
            banned_count = 0
            
            # 统计所有站点数据
            all_site_data = self.data_manager.get_site_data()
            for site_name, site_data in all_site_data.items():
                site_invitees = site_data.get("data", {}).get("invitees", [])
                total_invitees += len(site_invitees)
                
                # 统计分享率低的用户和已禁用用户
                for invitee in site_invitees:
                    ratio_value = invitee.get("ratio_value", 0)
                    enabled = invitee.get("enabled", "Yes")
                    
                    # 分享率阈值从0.5改为1.0
                    if ratio_value < 1.0:
                        low_ratio_count += 1
                    
                    if enabled.lower() == "no":
                        banned_count += 1
            
            title = "后宫管理系统 - 刷新结果"
            if success_count > 0 or error_count > 0:
                text = f"刷新完成: 成功 {success_count} 个站点，失败 {error_count} 个站点\n\n"
                text += f"👨‍👩‍👧‍👦 总邀请人数: {total_invitees}人\n"
                # 更新提示文本
                text += f"⚠️ 分享率低于1.0: {low_ratio_count}人\n"
                text += f"🚫 已禁用用户: {banned_count}人\n\n"
                
                # 添加刷新时间
                text += f"🕙 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
                
                # 只使用post_message发送一次通知，避免重复发送
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title=title,
                    text=text
                )
                logger.info(f"发送通知: {title} - 刷新完成: 成功 {success_count} 个站点，失败 {error_count} 个站点")
                
                # 移除通知助手发送，避免重复
                # self.notify_helper.send_notification(title, text, self._notify)
        
        logger.info(f"刷新完成: 成功 {success_count} 个站点, 失败 {error_count} 个站点")
        
        # 如果是立即运行一次，关闭开关并保存配置
        if self._onlyonce:
            self._onlyonce = False
            self.__update_config()
        
        return {"success": success_count, "error": error_count}
        
    def get_invitees(self, apikey: str = None, site_name: str = None) -> dict:
        """
        获取后宫成员API接口
        """
        if apikey and apikey != settings.API_TOKEN:
            return {"code": 1, "message": "API令牌错误!"}
            
        try:
            # 从数据文件获取站点数据
            site_data = self.data_manager.get_site_data(site_name)
            
            # 获取最后更新时间
            last_update = self.data_manager.get_last_update_time()
            
            if not site_data:
                if site_name:
                    return {"code": 1, "message": f"站点 {site_name} 数据不存在"}
                else:
                    return {"code": 1, "message": "暂无站点数据"}

            return {
                "code": 0,
                "message": "获取成功",
                "data": {
                    "sites": site_data,
                    "last_update": last_update
            }
            }
        except Exception as e:
            logger.error(f"获取后宫成员失败: {str(e)}")
            return {"code": 1, "message": f"获取后宫成员失败: {str(e)}"}

    def refresh_data(self, apikey: str = None) -> dict:
        """
        强制刷新所有站点数据API接口
        """
        if apikey and apikey != settings.API_TOKEN:
            return {"code": 1, "message": "API令牌错误!"}

        try:
            # 重新加载站点处理器以确保使用最新的处理逻辑
            self._site_handlers = ModuleLoader.load_site_handlers()
            logger.info(f"已重新加载 {len(self._site_handlers)} 个站点处理器")
            
            # 调用refresh_all_sites方法刷新数据
            result = self.refresh_all_sites()

            if result and result.get("success", 0) > 0:
                # 获取最新的更新时间和站点数据
                site_data = self.data_manager.get_site_data()
                last_update = self.data_manager.get_last_update_time()

                return {
                    "code": 0,
                        "message": f"数据刷新成功: {result.get('success')}个站点, 失败: {result.get('error')}个站点",
                        "data": {
                            "last_update": last_update,
                        "site_count": len(site_data),
                            "success": result.get("success", 0),
                            "error": result.get("error", 0)
                    }
                }
            else:
                return {"code": 1, "message": "数据刷新失败，没有成功刷新的站点"}
            
        except Exception as e:
            logger.error(f"强制刷新数据失败: {str(e)}")
            return {"code": 1, "message": f"强制刷新数据失败: {str(e)}"}

    def _get_user_id(self, session: requests.Session, site_info: Dict[str, Any]) -> str:
        """
        从站点获取用户ID
        :param session: 请求会话
        :param site_info: 站点信息
        :return: 用户ID
        """
        try:
            site_url = site_info.get("url", "").strip()
            site_name = site_info.get("name", "")
            
            # 访问个人页面提取ID
            profile_url = urljoin(site_url, "index.php")
            response = session.get(profile_url, timeout=(5, 15))
            response.raise_for_status()
            html_content = response.text
            
            # 尝试从多种常见格式中提取用户ID
            # 方法1：从class="searchrecord td"中提取
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 查找欢迎语中的用户名和ID链接
            welcome_text = soup.select_one('.welcome')
            if welcome_text:
                user_link = welcome_text.select_one('a[href*="userdetails.php"]')
                if user_link:
                    href = user_link.get('href', '')
                    id_match = re.search(r'id=(\d+)', href)
                    if id_match:
                        return id_match.group(1)
            
            # 方法2：从个人资料链接中提取
            for pattern in [
                r'userdetails\.php\?id=(\d+)',
                r'getusertorrentlistajax\.php\?userid=(\d+)',
                r'<input[^>]*name=["\']passkey["\'][^>]*value=["\']([a-zA-Z0-9]+)["\']',
                r'passkey=([a-zA-Z0-9]+)',
                r'usercp\.php\?action=personal&userid=(\d+)',
                r'id=(\d+)',
                r'uid=(\d+)'
            ]:
                matches = re.search(pattern, html_content)
                if matches:
                    return matches.group(1)
            
            # 方法3：尝试通过访问具体的用户资料页面
            try:
                user_link = None
                # 找到包含用户名的链接
                for a_tag in soup.select('a[href*="userdetails.php"], a[href*="user.php"]'):
                    if a_tag.get_text().strip():
                        user_link = a_tag
                        break
                
                if user_link:
                    href = user_link.get('href', '')
                    if 'id=' in href:
                        id_match = re.search(r'id=(\d+)', href)
                        if id_match:
                            return id_match.group(1)
                    
                    # 访问用户链接，从重定向或内容中提取用户ID
                    user_response = session.get(urljoin(site_url, href), timeout=(5, 15))
                    user_response.raise_for_status()
                    user_content = user_response.text
                    
                    # 在返回的内容中搜索用户ID
                    for pattern in [r'userdetails\.php\?id=(\d+)', r'passkey=([a-zA-Z0-9]+)', r'id=(\d+)', r'uid=(\d+)']:
                        matches = re.search(pattern, user_content)
                        if matches:
                            return matches.group(1)
            except Exception as e:
                logger.warning(f"通过用户资料页面获取用户ID失败: {str(e)}")
            
            # 方法4：尝试从邀请页面获取
            try:
                invite_url = urljoin(site_url, "invite.php")
                invite_response = session.get(invite_url, timeout=(5, 15))
                invite_response.raise_for_status()
                invite_content = invite_response.text
                
                # 搜索邀请页面中的用户ID
                for pattern in [r'id=(\d+)', r'uid=(\d+)', r'user(?:id|_id)=(\d+)']:
                    matches = re.search(pattern, invite_content)
                    if matches:
                        return matches.group(1)
            except Exception as e:
                logger.warning(f"通过邀请页面获取用户ID失败: {str(e)}")
            
            # 未能从任何途径获取用户ID
            logger.error(f"无法从站点 {site_name} 获取用户ID")
            return ""
            
        except Exception as e:
            logger.error(f"获取用户ID失败: {str(e)}")
            return ""

    def refresh_site_info(self, site_id):
        """
        刷新站点信息
        """
        site_info = self.get_site_info(site_id)
        if not site_info:
            return {
                "code": 1,
                "msg": "站点不存在"
            }
        # 回调消息
        self.eventmanager.send_event(EventType.TransactionUpdate, {
            "event_data": {
                "title": "刷新站点信息",
                "type_str": "站点信息",
                "f_id": site_id,
                "s_id": 0,
                "status": "处理中"
            }
        })
        # 查询站点信息
        _site_message = PluginHelper().get_site_info(site_info.get("url"))
        if not _site_message or not _site_message.get("cookie"):
            return {
                "code": 1,
                "msg": "站点不存在"
            }
        cookies = _site_message.get("cookie")
        ua = _site_message.get("ua")
        # 获取站点处理器
        _site_name = site_info.get("name")
        _site_id = site_id
        _site_url = site_info.get("url")
        try:
            # 根据站点类型选择处理器
            if self._is_nexusphp(_site_url):
                nexus_handler = self._load_site_handler("nexusphp")
                if nexus_handler:
                    nexus_handler.set_cookie(cookies)
                    nexus_handler.set_ua(ua)
                    # 创建会话并获取HTML内容
                    session = nexus_handler.create_session(_site_url, cookies)
                    content = nexus_handler.get_invite_page_content(_site_name, _site_url, session)
                    # 解析邀请页面
                    result = nexus_handler.parse_invite_page(_site_name, _site_url, content)
                else:
                    return {
                        "code": 1,
                        "msg": "未找到NexusPhp站点处理器"
                    }
            else:
                # 尝试蝶粉站点
                butterfly_handler = self._load_site_handler("butterfly")
                if butterfly_handler:
                    butterfly_handler.set_cookie(cookies)
                    butterfly_handler.set_ua(ua)
                    # 创建会话并获取HTML内容
                    session = butterfly_handler.create_session(_site_url, cookies)
                    content = butterfly_handler.get_invite_page_content(_site_name, _site_url, session)
                    # 解析邀请页面
                    result = butterfly_handler.parse_invite_page(_site_name, _site_url, content)
                else:
                    return {
                        "code": 1,
                        "msg": "未找到蝶粉站点处理器"
                    }
            
            # 处理结果
            if result:
                invite_status = result.get("invite_status", {})
                invitees = result.get("invitees", [])
                
                # 更新站点统计
                site_info["can_invite"] = invite_status.get("can_invite", False)
                site_info["invite_reason"] = invite_status.get("reason", "")
                site_info["permanent_invite_count"] = invite_status.get("permanent_count", 0)
                site_info["temporary_invite_count"] = invite_status.get("temporary_count", 0)
                site_info["refresh_time"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
                
                # 保存站点信息
                self.update_site_info(site_info)
                
                # 处理邀请者
                self.save_invitees(_site_id, invitees)
                
                # 发送成功消息
                self.eventmanager.send_event(EventType.TransactionUpdate, {
                    "event_data": {
                        "title": "刷新站点信息",
                        "type_str": "站点信息",
                        "f_id": site_id,
                        "s_id": 0,
                        "status": "成功"
                    }
                })
                
                logger.info(f"站点 {_site_name} 信息刷新成功，后宫成员数: {len(invitees)}")
                
                # 发送通知
                if invite_status.get("can_invite", False):
                    invite_count = invite_status.get("permanent_count", 0) + invite_status.get("temporary_count", 0)
                    if invite_count > 0:
                        NotificationHelper.send_notification(
                            self,
                            title=f"站点 {_site_name} 可邀请",
                            text=f"站点 {_site_name} 可邀请，永久邀请数: {invite_status.get('permanent_count', 0)}，临时邀请数: {invite_status.get('temporary_count', 0)}"
                        )
                
                return {
                    "code": 0,
                    "msg": "站点信息刷新成功"
                }
            else:
                # 发送失败消息
                self.eventmanager.send_event(EventType.TransactionUpdate, {
                    "event_data": {
                        "title": "刷新站点信息",
                        "type_str": "站点信息",
                        "f_id": site_id,
                        "s_id": 0,
                        "status": "失败"
                    }
                })
                
                return {
                    "code": 1,
                    "msg": "未能解析邀请页面，请检查站点Cookie是否有效"
                }
        
        except Exception as e:
            logger.error(f"刷新站点信息失败: {str(e)}")
            logger.exception(e)
            
            # 发送失败消息
            self.eventmanager.send_event(EventType.TransactionUpdate, {
                "event_data": {
                    "title": "刷新站点信息",
                    "type_str": "站点信息",
                    "f_id": site_id,
                    "s_id": 0,
                    "status": "失败"
                }
            })
            
            return {
                "code": 1,
                "msg": f"刷新站点信息失败: {str(e)}"
            }


# 插件类导出
plugin_class = nexusinvitee 
