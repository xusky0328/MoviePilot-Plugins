"""
两步验证码管理插件
"""
import hashlib
import json
import os
import time
import threading
import pyotp
from typing import Any, List, Dict, Tuple, Optional
import requests

from app.core.config import settings
from app.plugins import _PluginBase
from app.log import logger


class twofahelper(_PluginBase):
    # 插件名称
    plugin_name = "两步验证助手"
    # 插件描述
    plugin_desc = "管理两步验证码"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/madrays/MoviePilot-Plugins/main/icons/fnos.ico"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "madrays"
    # 作者主页
    author_url = "https://github.com/madrays"
    # 插件配置项ID前缀
    plugin_config_prefix = "twofahelper_"
    # 加载顺序
    plugin_order = 20
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _sites = {}
    _config_path = None
    
    # 配置文件路径
    config_file = None
    
    # 定时任务相关变量
    _sync_task = None
    _sync_interval = 300  # 默认5分钟同步一次
    _sync_running = False

    def init_plugin(self, config: dict = None):
        """
        插件初始化 - 移除配置页面提交处理
        """
        logger.info("两步验证助手插件开始初始化...")
        # 直接使用settings获取配置路径
        data_path = self.get_data_path()
        logger.info(f"数据目录路径: {data_path}")
        
        # 确保目录存在
        if not os.path.exists(data_path):
            try:
                os.makedirs(data_path)
                logger.info(f"创建数据目录: {data_path}")
            except Exception as e:
                logger.error(f"创建数据目录失败: {str(e)}")
        
        self.config_file = os.path.join(data_path, "twofahelper_sites.json")
        logger.info(f"配置文件路径: {self.config_file}")
        
        # 初始化时从文件加载配置到内存
        self._sync_from_file()
        
        # 如果内存中没有配置，尝试初始化空配置并保存
        if not self._sites:
            logger.info("内存中没有配置，初始化空配置")
            self._sites = {}
            # 写入空配置文件
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self._sites, f, ensure_ascii=False, indent=2)
                logger.info("成功写入空配置文件")
            except Exception as e:
                logger.error(f"写入空配置文件失败: {str(e)}")
        
        if self._sites:
            logger.info(f"两步验证码管理插件初始化完成，已加载 {len(self._sites)} 个站点: {list(self._sites.keys())}")
        else:
            logger.info("两步验证码管理插件初始化完成，暂无配置")
            
        # 检查HOST设置
        self._check_and_fix_host()
            
        # 启动自动同步任务
        self._start_auto_sync()

    def _check_and_fix_host(self):
        """
        检查HOST设置，确保包含协议前缀
        """
        host = settings.HOST
        logger.info(f"当前HOST设置: {host}")
        
        # 确保有协议前缀
        if not host.startswith(('http://', 'https://')):
            # 对于localhost或IP地址，默认使用http
            new_host = f"http://{host}"
            logger.info(f"更新HOST设置: {host} -> {new_host}")
            settings.HOST = new_host

    def _start_auto_sync(self):
        """
        启动自动同步任务
        """
        if self._sync_task and self._sync_running:
            logger.info("自动同步任务已在运行中")
            return
            
        self._sync_running = True
        logger.info(f"启动自动同步任务，同步间隔: {self._sync_interval}秒")
        
        # 创建并启动线程
        self._sync_task = threading.Thread(target=self._auto_sync_task, daemon=True)
        self._sync_task.start()
        
    def _stop_auto_sync(self):
        """
        停止自动同步任务
        """
        self._sync_running = False
        logger.info("停止自动同步任务")
        if self._sync_task:
            # 等待线程结束
            if self._sync_task.is_alive():
                self._sync_task.join(timeout=1.0)
            self._sync_task = None
            
    def _auto_sync_task(self):
        """
        自动同步任务函数 - 在后台线程中运行
        """
        logger.info("自动同步任务开始运行")
        
        while self._sync_running:
            try:
                # 从文件获取最新数据并同步内存
                logger.info("自动同步任务：开始同步配置...")
                
                # 先检查内存中的数据
                memory_sites_count = len(self._sites) if self._sites else 0
                memory_sites = list(self._sites.keys()) if self._sites else []
                logger.info(f"同步前：内存中有 {memory_sites_count} 个站点: {memory_sites}")
                
                # 从文件同步到内存
                success = self._sync_from_file()
                
                # 同步后检查内存数据
                new_memory_count = len(self._sites) if self._sites else 0
                new_memory_sites = list(self._sites.keys()) if self._sites else []
                logger.info(f"同步后：内存中有 {new_memory_count} 个站点: {new_memory_sites}")
                
                if success:
                    logger.info(f"自动同步成功，同步间隔: {self._sync_interval}秒")
                else:
                    logger.warning(f"自动同步失败，将在 {self._sync_interval}秒 后重试")
            except Exception as e:
                logger.error(f"自动同步过程中发生错误: {str(e)}")
                
            # 休眠指定间隔时间
            for _ in range(self._sync_interval):
                if not self._sync_running:
                    break
                time.sleep(1)
    
    def _sync_from_api_to_file(self):
        """
        从API获取配置数据并写入配置文件和内存
        """
        try:
            # 构建API URL - 尝试多个端口和主机以确保能访问
            # 注意：需要匹配MoviePilot实际运行的端口
            base_urls = [
                "http://127.0.0.1:3000",  # 默认开发端口
                "http://localhost:3000",   # 本地主机名
                "http://127.0.0.1:3333",   # 可能的端口
                "http://127.0.0.1:6222",   # 常用端口
                f"{settings.HOST}"         # 配置中的HOST
            ]
            
            api_data = None
            for base_url in base_urls:
                api_url = f"{base_url}/api/v1/plugin/twofahelper"
                logger.info(f"尝试从API获取数据: {api_url}")
                
                try:
                    # 发送请求获取数据
                    headers = {
                        "Authorization": f"Bearer {settings.API_TOKEN}",
                        "Content-Type": "application/json"
                    }
                    
                    response = requests.get(api_url, headers=headers, timeout=3)
                    
                    # 检查响应状态
                    if response.status_code == 200:
                        api_data = response.json()
                        logger.info(f"成功从 {api_url} 获取到API数据")
                        break
                    else:
                        logger.warning(f"从 {api_url} 获取数据失败，状态码: {response.status_code}")
                except Exception as e:
                    logger.warning(f"请求 {api_url} 出错: {str(e)}")
                    continue
            
            if not api_data:
                logger.error("所有API端点都无法访问")
                return False
            
            logger.info(f"API响应数据: {api_data.keys() if isinstance(api_data, dict) else '非字典格式'}")
            
            # 提取站点数据 - 格式: {"sites": {...}}
            sites_data = None
            if isinstance(api_data, dict):
                if "sites" in api_data:
                    sites_data = api_data["sites"]
                    logger.info(f"从API响应中提取sites字段，站点数: {len(sites_data)}")
                elif "data" in api_data and isinstance(api_data["data"], dict) and "sites" in api_data["data"]:
                    sites_data = api_data["data"]["sites"]
                    logger.info(f"从API响应的data.sites字段提取，站点数: {len(sites_data)}")
            
            # 检查提取的站点数据
            if not sites_data or not isinstance(sites_data, dict):
                logger.error(f"提取的站点数据无效: {type(sites_data)}")
                return False
            
            # 读取文件中的现有配置
            file_sites = {}
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        file_sites = json.load(f)
                    logger.info(f"读取文件配置成功，站点数: {len(file_sites)}")
                except Exception as e:
                    logger.error(f"读取文件配置失败: {e}")
            
            # 比较API数据和文件数据是否有变化
            if file_sites == sites_data:
                logger.info("API数据与文件数据相同，无需更新")
                # 仍然更新内存，确保同步
                self._sites = sites_data.copy()
                return True
            
            # 写入文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(sites_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"API配置已写入文件，站点数: {len(sites_data)}")
            
            # 更新内存
            memory_old_count = len(self._sites) if self._sites else 0
            self._sites = sites_data.copy()
            
            logger.info(f"内存配置已更新: {memory_old_count} -> {len(self._sites)} 个站点")
            logger.info(f"更新后的站点列表: {list(self._sites.keys())}")
            
            return True
        except Exception as e:
            logger.error(f"从API同步配置失败: {str(e)}")
            return False

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return True if self._sites else False

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        注册插件命令
        """
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
        return []

    def get_dashboard_meta(self) -> List[Dict[str, str]]:
        """
        获取插件仪表盘元信息
        """
        return [{
            "key": "totp_codes",
            "name": "两步验证码"
        }]

    def get_dashboard(self, key: str, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        """
        获取插件仪表盘页面
        """
        if key != "totp_codes":
            return None
        
        # 从文件重新加载配置，确保使用最新数据
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._sites = json.load(f)
                logger.info(f"仪表盘页面：从文件重新加载配置，站点数: {len(self._sites)}")
        except Exception as e:
            logger.error(f"仪表盘页面：重新加载配置文件失败: {str(e)}")
        
        # 栅格配置
        col_config = {
            "cols": 12,
            "md": 6,
            "lg": 4
        }
        
        # 全局配置
        global_config = {
            "refresh": 5,  # 每5秒刷新一次
            "title": "两步验证码",
            "subtitle": f"共 {len(self._sites)} 个站点",
            "border": True
        }
        
        # 获取所有验证码
        codes = self.get_all_codes()
        
        # 构建仪表盘内容
        content = [
            {
                "component": "div",
                "props": {
                    "class": "d-flex flex-wrap"
                },
                "content": []
            }
        ]
        
        # 如果没有验证码，显示提示信息
        if not codes:
            content[0]["content"].append({
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "text": "还没有添加任何验证站点，请前往「插件设置」添加",
                    "class": "w-100"
                }
            })
        else:
            # 为每个站点创建一个卡片
            for site_name, code_info in codes.items():
                # 计算进度条颜色
                progress_color = "success"
                if code_info["remaining_seconds"] < 10:
                    progress_color = "error"
                elif code_info["remaining_seconds"] < 20:
                    progress_color = "warning"
                
                # 添加到内容中
                content[0]["content"].append({
                    "component": "VCard",
                    "props": {
                        "width": "150",
                        "class": "ma-2",
                        "variant": "outlined"
                    },
                    "content": [
                        {
                            "component": "VCardTitle",
                            "props": {
                                "class": "text-subtitle-2 pa-2"
                            },
                            "text": site_name
                        },
                        {
                            "component": "VCardText",
                            "props": {
                                "class": "pa-2"
                            },
                            "content": [
                                {
                                    "component": "div",
                                    "props": {
                                        "class": "text-h5 text-center font-weight-bold"
                                    },
                                    "text": code_info["code"]
                                },
                                {
                                    "component": "VProgressLinear",
                                    "props": {
                                        "model-value": code_info["progress_percent"],
                                        "color": progress_color,
                                        "height": "5",
                                        "class": "mt-2"
                                    }
                                },
                                {
                                    "component": "div",
                                    "props": {
                                        "class": "text-caption text-center mt-1"
                                    },
                                    "text": f"{code_info['remaining_seconds']}秒"
                                }
                            ]
                        },
                        {
                            "component": "VCardActions",
                            "props": {
                                "class": "pa-2 justify-center"
                            },
                            "content": [
                                {
                                    "component": "VBtn",
                                    "props": {
                                        "size": "small",
                                        "variant": "outlined",
                                        "color": progress_color,
                                        "@click": f"navigator.clipboard.writeText('{code_info['code']}');$toast.success('验证码已复制: {code_info['code']}')"
                                    },
                                    "text": "复制"
                                }
                            ]
                        }
                    ]
                })
        
        return col_config, global_config, content

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件API
        
        API流向说明:
        1. get_plugin_config (服务器 -> 浏览器): 浏览器获取TOTP站点配置信息
        2. update_totp_config (浏览器 -> 服务器): 浏览器更新TOTP站点配置
        3. get_totp_codes (服务器 -> 浏览器): 获取所有站点的TOTP验证码
        4. copy_code (服务器 -> 浏览器): 获取单个站点的验证码
        5. sync_now (服务器): 立即执行同步，从文件同步到内存
        """
        return [
            {
                'path': '',
                'endpoint': self.get_plugin_config,
                'methods': ['GET'],
                'summary': '获取插件配置',
                'description': '获取TOTP站点配置信息',
                'auth': True
            },
            {
                'path': '',
                'endpoint': self.update_totp_config,
                'methods': ['PUT'],
                'summary': '更新插件配置(新版)',
                'description': '使用PUT请求和sites参数更新TOTP站点配置',
                'auth': True
            },
            {
                'path': '/get_codes',
                'endpoint': self.get_totp_codes,
                'methods': ['GET'],
                'summary': '获取所有TOTP验证码',
                'description': '获取所有站点的TOTP验证码信息',
                'auth': True
            },
            {
                'path': '/update_config',
                'endpoint': self.update_totp_config,
                'methods': ['POST'],
                'summary': '更新TOTP配置(旧版)',
                'description': '使用POST请求和config参数更新TOTP站点配置',
                'auth': True
            },
            {
                'path': '/copy_code',
                'endpoint': self.copy_code,
                'methods': ['GET'],
                'summary': '获取单个站点的验证码',
                'description': '获取指定站点的验证码信息',
                'auth': False
            },
            {
                'path': '/sync_now',
                'endpoint': self.api_sync_now,
                'methods': ['GET'],
                'summary': '立即同步',
                'description': '立即从文件获取最新配置并更新到内存',
                'auth': True
            },
            {
                'path': '/set_sync_interval',
                'endpoint': self.api_set_sync_interval,
                'methods': ['POST'],
                'summary': '设置同步间隔',
                'description': '设置API自动同步的时间间隔',
                'auth': True
            },
            {
                'path': '/status',
                'endpoint': self.api_get_status,
                'methods': ['GET'],
                'summary': '获取状态信息',
                'description': '获取插件当前状态、配置和HOST设置信息',
                'auth': True
            },
            {
                'path': '/test',
                'endpoint': self.api_test,
                'methods': ['GET'],
                'summary': '测试API连接',
                'description': '测试API连接是否正常，返回当前时间和配置数量',
                'auth': False
            },
            {
                'path': '/dump_sites',
                'endpoint': self.api_dump_sites,
                'methods': ['GET'],
                'summary': '转储内存中的站点配置',
                'description': '输出内存中的站点配置用于调试',
                'auth': True
            }
        ]

    def get_plugin_config(self, **kwargs):
        """
        API接口：获取插件配置
        返回格式：{"sites": { 站点配置 }}
        """
        # 每次获取前先从文件同步一次，确保数据最新
        self._sync_from_file()
        logger.info(f"API获取配置：当前内存中有 {len(self._sites)} 个站点")
        
        # 注意返回格式包含外层sites字段
        return {"code": 0, "message": "成功", "sites": self._sites}

    def get_totp_codes(self, **kwargs):
        """
        API接口：获取所有TOTP验证码
        """
        # 每次获取验证码前先从文件同步一次配置，确保数据最新
        self._sync_from_file()
        logger.info(f"API获取验证码：当前内存中有 {len(self._sites)} 个站点")
        
        codes = {}
        current_time = int(time.time())
        time_step = 30
        remaining_seconds = time_step - (current_time % time_step)
        
        for site, data in self._sites.items():
            try:
                totp = pyotp.TOTP(data.get("secret"))
                codes[site] = {
                    "code": totp.now(),
                    "urls": data.get("urls", []),
                    "remaining_seconds": remaining_seconds,
                    "progress_percent": (remaining_seconds / time_step) * 100
                }
            except Exception as e:
                logger.error(f"生成站点 {site} 的验证码失败: {str(e)}")
        
        logger.info(f"生成验证码成功，共 {len(codes)} 个站点")
        return {"code": 0, "message": "成功", "data": codes}

    def update_totp_config(self, **kwargs):
        """
        API接口：更新TOTP配置 - 支持两种方式更新配置
        1. PUT /api/v1/plugin/twofahelper：直接使用请求体中的sites字段 (浏览器插件 -> 服务器)
        2. POST /api/v1/plugin/twofahelper/update_config：使用请求体中的config字段 (浏览器插件 -> 服务器)
        
        这个接口用于接收浏览器插件发送的配置数据，然后保存到文件并更新内存。
        """
        logger.info(f"接收到更新配置请求，方法: {kwargs.get('request_method', 'UNKNOWN')}, 参数: {list(kwargs.keys())}")
        
        # 记录请求体内容
        for key in kwargs.keys():
            if key not in ['request_method', 'headers']:
                logger.info(f"请求参数 {key}: {type(kwargs[key])}")
                # 如果是字典，记录键
                if isinstance(kwargs[key], dict):
                    logger.info(f"参数 {key} 包含的键: {list(kwargs[key].keys())}")
        
        # 检查是否是PUT请求 - 浏览器插件使用这种方式
        sites_config = None
        request_method = kwargs.get('request_method')
        
        # 1. 如果是PUT请求，从请求体中直接获取sites字段
        if request_method == 'PUT':
            logger.info("检测到PUT请求，尝试从请求体中获取sites字段")
            # 先尝试获取外层sites字段
            if "sites" in kwargs:
                sites_config = kwargs.get("sites")
                logger.info(f"从PUT请求中获取到外层sites字段，站点数: {len(sites_config)}")
            else:
                # 如果没有外层sites字段，直接使用整个请求体作为配置
                sites_config = kwargs
                logger.info(f"PUT请求中未找到外层sites字段，使用整个请求体，参数数: {len(sites_config)}")
        
        # 2. 如果不是PUT请求或没有找到sites字段，则尝试从config字段获取
        if not sites_config:
            config = kwargs.get("config")
            if not config:
                logger.error("未找到有效的配置参数")
                return {"code": 400, "message": "缺少配置参数"}
            
            # 如果是JSON字符串，则解析
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                    logger.info(f"从config字段解析JSON成功")
                    
                    # 检查是否有外层sites字段
                    if "sites" in config:
                        sites_config = config["sites"]
                        logger.info(f"从config字段中提取sites字段，站点数: {len(sites_config)}")
                    else:
                        sites_config = config
                        logger.info(f"config字段中无外层sites字段，使用整个config内容，站点数: {len(sites_config)}")
                except Exception as e:
                    logger.error(f"解析config字段失败: {str(e)}")
                    return {"code": 400, "message": f"配置参数格式错误: {str(e)}"}
            else:
                # 对象类型，检查是否有外层sites字段
                if isinstance(config, dict) and "sites" in config:
                    sites_config = config["sites"]
                    logger.info(f"从config对象中提取sites字段，站点数: {len(sites_config)}")
                else:
                    sites_config = config
                    logger.info(f"config对象中无外层sites字段，使用整个config内容，站点数: {len(sites_config) if isinstance(config, dict) else 'N/A'}")
        
        # 确认有有效的站点配置
        if not sites_config or not isinstance(sites_config, dict):
            logger.error(f"站点配置无效: {type(sites_config)}")
            return {"code": 400, "message": "无效的站点配置"}
        
        try:
            logger.info(f"准备更新配置，站点数: {len(sites_config)}")
            
            # 获取当前站点列表
            old_sites = list(self._sites.keys()) if self._sites else []
            new_sites = list(sites_config.keys())
            
            # 检查变化
            added_sites = [site for site in new_sites if site not in old_sites]
            removed_sites = [site for site in old_sites if site not in new_sites]
            
            if added_sites:
                logger.info(f"新增站点: {added_sites}")
            if removed_sites:
                logger.info(f"移除站点: {removed_sites}")
            
            # 保存到文件 - 确保相同格式
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(sites_config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"配置文件写入成功: {self.config_file}，站点数: {len(sites_config)}")
            
            # 重要：更新内存中的配置
            self._sites = sites_config.copy()  # 使用copy()避免引用问题
            logger.info(f"内存中的配置已更新，站点数: {len(self._sites)}，站点列表: {list(self._sites.keys())}")
            
            # 返回更详细的信息
            return {
                "code": 0, 
                "message": "配置更新成功", 
                "sites_count": len(sites_config),
                "sites": new_sites,
                "changes": {
                    "added": added_sites,
                    "removed": removed_sites
                }
            }
        except Exception as e:
            logger.error(f"通过API更新配置失败: {str(e)}")
            return {"code": 500, "message": f"配置更新失败: {str(e)}"}

    def copy_code(self, **kwargs):
        """
        API接口：获取单个站点的验证码
        """
        site = kwargs.get("site")
        if not site or site not in self._sites:
            return {"code": 400, "message": "站点不存在"}
        
        try:
            data = self._sites.get(site)
            totp = pyotp.TOTP(data.get("secret"))
            now_code = totp.now()
            
            return {
                "code": 0, 
                "message": "成功", 
                "data": {
                    "code": now_code
                }
            }
        except Exception as e:
            logger.error(f"获取站点 {site} 的验证码失败: {str(e)}")
            return {"code": 500, "message": f"获取验证码失败: {str(e)}"}

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        配置页面 - 只显示当前配置，不允许编辑，采用AJAX自动更新内容
        """
        logger.info("开始生成配置页面...")
        
        # 每次都直接从文件读取，确保获取最新内容
        file_config = "{}"
        sites_count = 0
        site_names = []
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_config = f.read()
                logger.info(f"直接读取文件成功: {self.config_file}, 内容长度: {len(file_config)}")
                # 美化JSON格式
                try:
                    parsed = json.loads(file_config)
                    sites_count = len(parsed)
                    site_names = list(parsed.keys())
                    logger.info(f"读取到 {sites_count} 个站点: {site_names}")
                    # 重新格式化为美观的JSON
                    file_config = json.dumps(parsed, indent=2, ensure_ascii=False)
                except Exception as e:
                    logger.error(f"解析配置文件失败: {str(e)}")
            except Exception as e:
                logger.error(f"读取配置文件失败: {str(e)}")
        else:
            logger.warning(f"配置文件不存在: {self.config_file}")
        
        # 当前时间字符串，确保初始显示正确
        current_time = time.strftime("%H:%M:%S", time.localtime())
        
        # 构造表单 - 只读模式，使用AJAX自动刷新
        form = [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'style',
                        'text': """
                        .auto-refresh-info {
                            font-size: 12px;
                            color: #666;
                            text-align: center;
                            margin-top: 5px;
                        }
                        .code-block {
                            background-color: #272822; 
                            color: #f8f8f2; 
                            padding: 16px; 
                            border-radius: 4px; 
                            overflow: auto; 
                            font-family: monospace; 
                            max-height: 600px;
                        }
                        """
                    },
                    {
                        'component': 'script',
                        'text': """
                        // 使用AJAX自动刷新配置内容
                        function refreshConfig() {
                            // 创建AJAX请求
                            var xhr = new XMLHttpRequest();
                            xhr.open('GET', '/api/v1/plugin/twofahelper', true);
                            
                            // 获取当前token
                            var token = localStorage.getItem('token');
                            if (token) {
                                xhr.setRequestHeader('Authorization', 'Bearer ' + token);
                            }
                            
                            xhr.onload = function() {
                                if (xhr.status === 200) {
                                    try {
                                        var response = JSON.parse(xhr.responseText);
                                        console.log('API响应: ', response);
                                        
                                        // 检测响应中的sites字段
                                        var sites = response.sites;
                                        if (!sites && response.code === 0) {
                                            sites = response.data;
                                        }
                                        
                                        if (sites) {
                                            // 更新站点数量和列表
                                            var sitesCount = Object.keys(sites).length;
                                            var sitesList = Object.keys(sites).join(', ');
                                            
                                            // 更新统计信息
                                            document.getElementById('sites-count').textContent = sitesCount;
                                            document.getElementById('sites-list').textContent = sitesList;
                                            
                                            // 更新配置显示
                                            var prettyConfig = JSON.stringify(sites, null, 2);
                                            document.getElementById('config-content').textContent = prettyConfig;
                                            
                                            // 更新刷新时间
                                            document.getElementById('last-refresh').textContent = 
                                                new Date().toLocaleTimeString();
                                        }
                                    } catch (e) {
                                        console.error('解析配置失败:', e);
                                    }
                                }
                            };
                            
                            xhr.send();
                            
                            // 10秒后再次刷新
                            setTimeout(refreshConfig, 10000);
                        }
                        
                        // 页面加载完成后开始自动刷新
                        document.addEventListener('DOMContentLoaded', function() {
                            // 立即开始第一次刷新
                            setTimeout(refreshConfig, 1000);
                        });
                        """
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
                                            'title': '两步验证助手配置',
                                            'text': f'配置文件路径: {self.config_file}'
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
                                            'label': '自动同步间隔（秒）',
                                            'model': 'sync_interval',
                                            'placeholder': '默认300秒',
                                            'type': 'number',
                                            'min': 60,
                                            'hint': '设置从API自动同步配置的时间间隔，最小60秒'
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
                                        'component': 'VBtn',
                                        'props': {
                                            'color': 'primary',
                                            'text': '立即同步',
                                            'block': True,
                                            'onClick': """
                                            (function() {
                                                var xhr = new XMLHttpRequest();
                                                xhr.open('GET', '/api/v1/plugin/twofahelper/sync_now', true);
                                                
                                                var token = localStorage.getItem('token');
                                                if (token) {
                                                    xhr.setRequestHeader('Authorization', 'Bearer ' + token);
                                                }
                                                
                                                xhr.onload = function() {
                                                    var msg = '同步请求已发送';
                                                    if (xhr.status === 200) {
                                                        try {
                                                            var resp = JSON.parse(xhr.responseText);
                                                            msg = resp.message || '同步成功';
                                                            // 刷新页面
                                                            setTimeout(function() {
                                                                location.reload();
                                                            }, 1500);
                                                        } catch (e) {}
                                                    }
                                                    $toast.success(msg);
                                                };
                                                
                                                xhr.send();
                                            })();
                                            """
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
                                            'type': 'success',
                                            'variant': 'tonal'
                                        },
                        'content': [
                            {
                                                'component': 'div',
                                                'text': '当前站点数: '
                                            },
                                            {
                                                'component': 'span',
                                'props': {
                                                    'id': 'sites-count'
                                                },
                                                'text': str(sites_count)
                                            },
                                            {
                                                'component': 'span',
                                                'text': ' 个站点'
                                            },
                                            {
                                                'component': 'br'
                                            },
                                            {
                                                'component': 'div',
                                                'text': '站点列表: '
                                            },
                                            {
                                                'component': 'span',
                                        'props': {
                                                    'id': 'sites-list'
                                                },
                                                'text': ', '.join(site_names)
                                            },
                                            {
                                                'component': 'br'
                                            },
                                            {
                                                'component': 'div',
                                                'text': '上次刷新: '
                                            },
                                            {
                                                'component': 'span',
                                                'props': {
                                                    'id': 'last-refresh'
                                                },
                                                'text': current_time
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
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'warning',
                                            'variant': 'tonal',
                                            'text': '请注意: 配置只能通过浏览器插件API接口修改，此页面仅用于查看当前配置'
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
                                            'class': 'auto-refresh-info'
                                        },
                                        'text': f'配置内容每10秒自动刷新一次，无需手动刷新页面。后台每{self._sync_interval}秒自动从API同步一次配置。'
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
                                        'component': 'VSpacer',
                                        'props': {
                                            'style': 'height: 16px'
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
                                        'component': 'VCardText',
                                        'props': {
                                            'class': 'pa-2'
                                        },
                                        'content': [
                                            {
                                                'component': 'pre',
                                                'props': {
                                                    'id': 'config-content',
                                                    'class': 'code-block'
                                                },
                                                'text': file_config
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
        
        logger.info("配置页面生成完成")
        
        # 返回表单数据，包含同步间隔设置
        return form, {
            "sync_interval": self._sync_interval
        }

    def get_page(self) -> List[dict]:
        """
        详情页面 - 使用AJAX更新而非整页刷新
        """
        try:
            logger.info("生成验证码页面...")
            
            # 在生成页面前先同步一次配置
            self._sync_from_file()
            
            # 当前时间字符串，确保初始显示正确
            current_time = time.strftime("%H:%M:%S", time.localtime())
            
            # 添加样式
            style_text = """
            .otp-code {
                white-space: nowrap;
                font-family: monospace;
                letter-spacing: 1px;
                font-weight: 700;
                display: block;
                width: 100%;
                text-align: center;
                font-size: 1.5rem;
                overflow: visible;
            }
            
            .copy-button:active {
                transform: scale(0.98);
            }
            
            .totp-card {
                min-width: 120px;
            }
            """
            
            # 构建内容
            return [
                {
                    'component': 'div',
                    'props': {
                        'id': 'totp-container',
                        'style': 'width: 100%;'
                    },
                    'content': [
                        {
                            'component': 'style',
                            'text': style_text
                        },
                        {
                            'component': 'script',
                            'text': """
                            // 使用AJAX自动刷新验证码
                            function refreshTOTPCodes() {
                                // 创建AJAX请求
                                var xhr = new XMLHttpRequest();
                                xhr.open('GET', '/api/v1/plugin/twofahelper/get_codes', true);
                                
                                // 获取当前token
                                var token = localStorage.getItem('token');
                                if (token) {
                                    xhr.setRequestHeader('Authorization', 'Bearer ' + token);
                                }
                                
                                xhr.onload = function() {
                                    if (xhr.status === 200) {
                                        try {
                                            var response = JSON.parse(xhr.responseText);
                                            console.log('获取验证码响应:', response);
                                            
                                            var codes = null;
                                            if (response.data) {
                                                codes = response.data;
                                            } else if (response.code === 0 && response.data) {
                                                codes = response.data;
                                            }
                                            
                                            if (codes) {
                                                updateTOTPCards(codes);
                                            }
                                        } catch (e) {
                                            console.error('解析验证码失败:', e);
                                        }
                                    }
                                };
                                
                                xhr.send();
                                
                                // 5秒后再次刷新
                                setTimeout(refreshTOTPCodes, 5000);
                            }
                            
                            // 更新TOTP卡片
                            function updateTOTPCards(codes) {
                                // 获取当前时间
                                var now = Math.floor(Date.now() / 1000);
                                var timeStep = 30;
                                var nextStep = (Math.floor(now / timeStep) + 1) * timeStep;
                                var remainingSeconds = nextStep - now;
                                var progressPercent = ((timeStep - remainingSeconds) / timeStep) * 100;
                                
                                // 更新倒计时文本和进度条
                                var timeTexts = document.querySelectorAll('.time-text');
                                var progressBars = document.querySelectorAll('.progress-bar');
                                
                                timeTexts.forEach(function(el) {
                                    el.textContent = remainingSeconds + '秒';
                                });
                                
                                progressBars.forEach(function(el) {
                                    el.style.width = progressPercent + '%';
                                });
                                
                                // 更新验证码
                                for (var siteName in codes) {
                                    if (codes.hasOwnProperty(siteName)) {
                                        var codeEl = document.getElementById('code-' + siteName);
                                        if (codeEl) {
                                            codeEl.textContent = codes[siteName].code;
                                        }
                                    }
                                }
                                
                                // 更新刷新时间和站点数量
                                var lastRefreshEl = document.getElementById('last-refresh-time');
                                if (lastRefreshEl) {
                                    lastRefreshEl.textContent = new Date().toLocaleTimeString();
                                }
                                
                                var sitesCountEl = document.getElementById('sites-count');
                                if (sitesCountEl) {
                                    sitesCountEl.textContent = Object.keys(codes).length;
                                }
                            }
                            
                            // 页面加载完成后开始自动刷新
                            document.addEventListener('DOMContentLoaded', function() {
                                // 立即开始第一次刷新
                                setTimeout(refreshTOTPCodes, 1000);
                            });
                            """
                        },
                        {
                            'component': 'VAlert',
                            'props': {
                                'type': 'info',
                                'variant': 'tonal',
                                'class': 'mb-2',
                                'density': 'compact'
                            },
                            'content': [
                                {
                                    'component': 'div',
                                    'props': {
                                        'style': 'display: flex; justify-content: space-between; align-items: center;'
                                    },
                                    'content': [
                                        {
                                            'component': 'span',
                                            'content': [
                                                {
                                                    'component': 'span',
                                                    'text': '当前共有 '
                                                },
                                                {
                                                    'component': 'span',
                                                    'props': {
                                                        'id': 'sites-count'
                                                    },
                                                    'text': str(len(self._sites))
                                                },
                                                {
                                                    'component': 'span',
                                                    'text': ' 个站点'
                                                }
                                            ]
                                        },
                                        {
                                            'component': 'span',
                                            'content': [
                                                {
                                                    'component': 'span',
                                                    'text': '上次刷新: '
                                                },
                                                {
                                                    'component': 'span',
                                                    'props': {
                                                        'id': 'last-refresh-time'
                                                    },
                                                    'text': current_time
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            'component': 'VRow',
                            'props': {
                                'dense': True
                            },
                            'content': self._generate_cards_for_page()
                        }
                    ]
                }
            ]
                
        except Exception as e:
            logger.error(f"生成验证码页面失败: {e}")
            return [{
                'component': 'VAlert',
                'props': {
                    'type': 'error',
                    'text': f'生成验证码失败: {e}',
                    'variant': 'tonal'
                }
            }]
    
    def _generate_cards_for_page(self) -> List[dict]:
        """
        为详情页面生成验证码卡片，支持AJAX更新
        """
        if not self._sites:
            return [
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
                                'text': '暂无配置的站点',
                                'variant': 'tonal'
                            }
                        }
                    ]
                }
            ]
        
        cards = []
        
        current_time = int(time.time())
        time_step = 30
        
        # 计算下一个完整周期的时间
        next_valid_time = (current_time // time_step + 1) * time_step
        remaining_seconds = next_valid_time - current_time
        
        # 计算进度百分比
        progress_percent = 100 - ((remaining_seconds / time_step) * 100)
        
        # 为每个站点生成一个卡片
        card_index = 0
        for site, data in self._sites.items():
            try:
                totp = pyotp.TOTP(data.get("secret"))
                now_code = totp.now()
                card_index += 1
                
                # 根据卡片序号选择不同的颜色
                colors = ['primary', 'success', 'warning']
                color = colors[card_index % len(colors)]
                
                # 构建简单卡片，添加ID以便AJAX更新
                cards.append({
                    'component': 'VCol',
                    'props': {
                        'cols': 12,
                        'sm': 6,
                        'md': 4,
                        'lg': 3
                    },
                    'content': [{
                        'component': 'VCard',
                        'props': {
                            'variant': 'outlined',
                            'class': 'ma-1 totp-card'
                        },
                        'content': [
                            {
                                'component': 'VCardTitle',
                                'props': {
                                    'class': 'py-1 text-caption'
                                },
                                'text': site
                            },
                            {
                                'component': 'VCardText',
                                'props': {
                                    'class': 'text-center py-1'
                                },
                                'content': [{
                                    'component': 'span',
                                    'props': {
                                        'class': 'otp-code text-h6',
                                        'id': f'code-{site}'
                                    },
                                    'text': now_code
                                }]
                            },
                            {
                                'component': 'VCardText',
                                'props': {
                                    'class': 'py-1'
                                },
                                'content': [
                                    {
                                        'component': 'VProgressLinear',
                                        'props': {
                                            'model-value': progress_percent,
                                            'color': color,
                                            'height': 2,
                                            'class': 'progress-bar'
                                        }
                                    },
                                    {
                                        'component': 'div',
                                        'props': {
                                            'class': 'text-caption text-center mt-1 time-text'
                                        },
                                        'text': f'{remaining_seconds}秒'
                                    }
                                ]
                            },
                            {
                                'component': 'VCardActions',
                                'props': {
                                    'class': 'py-0 px-2 d-flex justify-center'
                                },
                                'content': [
                                    {
                                        'component': 'VBtn',
                                        'props': {
                                            'size': 'small',
                                            'variant': 'text',
                                            'color': color,
                                            'class': 'copy-button',
                                            'block': True,
                                            'onclick': f"""
                                            var code = document.getElementById('code-{site}').textContent;
                                            navigator.clipboard.writeText(code).then(() => {{
                                              this.textContent = '已复制';
                                              setTimeout(() => {{ this.textContent = '复制'; }}, 1000);
                                            }}).catch(() => {{
                                              // 如果navigator.clipboard不可用，使用传统方法
                                              var textArea = document.createElement('textarea');
                                              textArea.value = code;
                                              textArea.style.position = 'fixed';
                                              document.body.appendChild(textArea);
                                              textArea.focus();
                                              textArea.select();
                                              try {{
                                                document.execCommand('copy');
                                                this.textContent = '已复制';
                                                setTimeout(() => {{ this.textContent = '复制'; }}, 1000);
                                              }} catch (err) {{
                                                console.error('无法复制');
                                              }}
                                              document.body.removeChild(textArea);
                                            }});
                                            """
                                        },
                                        'text': '复制'
                                    }
                                ]
                            }
                        ]
                    }]
                })
            except Exception as e:
                logger.error(f"生成站点 {site} 的验证码失败: {e}")
        
        return cards

    def stop_service(self):
        """
        退出插件
        """
        logger.info("两步验证助手插件停止服务")
        # 停止自动同步任务
        self._stop_auto_sync()

    def _sync_from_file(self):
        """
        从配置文件同步到内存 - 增强版，添加更详细的日志
        """
        if os.path.exists(self.config_file):
            try:
                # 读取文件修改时间
                file_mtime = os.path.getmtime(self.config_file)
                file_mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(file_mtime))
                
                # 读取文件内容
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                
                content_length = len(file_content)
                logger.info(f"读取配置文件成功，内容长度: {content_length}，最后修改时间: {file_mtime_str}")
                
                # 解析JSON
                new_sites = json.loads(file_content)
                new_sites_count = len(new_sites)
                new_site_names = list(new_sites.keys())
                
                # 检查配置是否有变化
                old_sites_count = len(self._sites) if self._sites else 0
                old_site_names = list(self._sites.keys()) if self._sites else []
                
                if new_sites_count != old_sites_count or set(new_site_names) != set(old_site_names):
                    logger.info(f"检测到配置变化: 站点数量 {old_sites_count} -> {new_sites_count}")
                    
                    # 查找新增的站点
                    added_sites = [site for site in new_site_names if site not in old_site_names]
                    if added_sites:
                        logger.info(f"新增站点: {added_sites}")
                    
                    # 查找移除的站点
                    removed_sites = [site for site in old_site_names if site not in new_site_names]
                    if removed_sites:
                        logger.info(f"移除站点: {removed_sites}")
                    
                    # 更新内存中的配置
                    self._sites = new_sites
                    logger.info(f"配置文件解析成功并更新到内存，共 {new_sites_count} 个站点: {new_site_names}")
                else:
                    logger.info(f"配置无变化，共 {new_sites_count} 个站点")
                    # 仍然更新内存中的配置，确保内存中的配置与文件一致
                    self._sites = new_sites
                
                return True
            except json.JSONDecodeError as e:
                logger.error(f"配置文件JSON格式解析失败: {str(e)}")
                # 保持内存中的现有配置不变
                return False
            except Exception as e:
                logger.error(f"读取配置文件失败: {str(e)}")
                # 保持内存中的现有配置不变
                return False
        else:
            logger.warning(f"配置文件不存在: {self.config_file}")
            # 清空内存中的配置
            if self._sites:
                logger.info("清空内存中的配置")
                self._sites = {}
            return False

    def _generate_cards_for_dashboard(self) -> List[dict]:
        """
        为仪表盘生成验证码卡片，支持AJAX更新
        """
        if not self._sites:
            return []
        
        cards = []
        
        current_time = int(time.time())
        time_step = 30
        
        # 计算下一个完整周期的时间
        next_valid_time = (current_time // time_step + 1) * time_step
        remaining_seconds = next_valid_time - current_time
        
        # 计算进度百分比
        progress_percent = 100 - ((remaining_seconds / time_step) * 100)
        
        # 为每个站点生成一个卡片
        card_index = 0
        for site, data in self._sites.items():
            try:
                totp = pyotp.TOTP(data.get("secret"))
                now_code = totp.now()
                card_index += 1
                
                # 根据卡片序号选择不同的颜色
                colors = ['primary', 'success', 'warning']
                color = colors[card_index % len(colors)]
                
                # 构建简单卡片，添加ID以便AJAX更新
                cards.append({
                    'component': 'VCol',
                    'props': {
                        'cols': 12,
                        'sm': 6,
                        'md': 4,
                        'lg': 3
                    },
                    'content': [{
                        'component': 'VCard',
                        'props': {
                            'variant': 'outlined',
                            'class': 'ma-1 totp-card'
                        },
                        'content': [
                            {
                                'component': 'VCardTitle',
                                'props': {
                                    'class': 'py-1 text-caption'
                                },
                                'text': site
                            },
                            {
                                'component': 'VCardText',
                                'props': {
                                    'class': 'text-center py-1'
                                },
                                'content': [{
                                    'component': 'span',
                                    'props': {
                                        'class': 'otp-code text-h6',
                                        'id': f'code-{site}'
                                    },
                                    'text': now_code
                                }]
                            },
                            {
                                'component': 'VCardText',
                                'props': {
                                    'class': 'py-1'
                                },
                                'content': [
                                    {
                                        'component': 'VProgressLinear',
                                        'props': {
                                            'model-value': progress_percent,
                                            'color': color,
                                            'height': 2,
                                            'class': 'progress-bar'
                                        }
                                    },
                                    {
                                        'component': 'div',
                                        'props': {
                                            'class': 'text-caption text-center mt-1 time-text'
                                        },
                                        'text': f'{remaining_seconds}秒'
                                    }
                                ]
                            },
                            {
                                'component': 'VCardActions',
                                'props': {
                                    'class': 'py-0 px-2 d-flex justify-center'
                                },
                                'content': [
                                    {
                                        'component': 'VBtn',
                                        'props': {
                                            'size': 'small',
                                            'variant': 'text',
                                            'color': color,
                                            'class': 'copy-button',
                                            'block': True,
                                            'onclick': f"""
                                            var code = document.getElementById('code-{site}').textContent;
                                            navigator.clipboard.writeText(code).then(() => {{
                                              this.textContent = '已复制';
                                              setTimeout(() => {{ this.textContent = '复制'; }}, 1000);
                                            }}).catch(() => {{
                                              // 如果navigator.clipboard不可用，使用传统方法
                                              var textArea = document.createElement('textarea');
                                              textArea.value = code;
                                              textArea.style.position = 'fixed';
                                              document.body.appendChild(textArea);
                                              textArea.focus();
                                              textArea.select();
                                              try {{
                                                document.execCommand('copy');
                                                this.textContent = '已复制';
                                                setTimeout(() => {{ this.textContent = '复制'; }}, 1000);
                                              }} catch (err) {{
                                                console.error('无法复制');
                                              }}
                                              document.body.removeChild(textArea);
                                            }});
                                            """
                                        },
                                        'text': '复制'
                                    }
                                ]
                            }
                        ]
                    }]
                })
            except Exception as e:
                logger.error(f"生成站点 {site} 的验证码失败: {e}")
        
        return cards

    def get_all_codes(self):
        """
        获取所有站点的验证码
        """
        codes = {}
        current_time = int(time.time())
        time_step = 30
        remaining_seconds = time_step - (current_time % time_step)
        
        for site, data in self._sites.items():
            try:
                totp = pyotp.TOTP(data.get("secret"))
                codes[site] = {
                    "code": totp.now(),
                    "urls": data.get("urls", []),
                    "remaining_seconds": remaining_seconds,
                    "progress_percent": (remaining_seconds / time_step) * 100
                }
            except Exception as e:
                logger.error(f"生成站点 {site} 的验证码失败: {str(e)}")
        
        return codes

    def api_sync_now(self, **kwargs):
        """
        API接口：立即执行同步
        """
        logger.info("接收到手动同步请求")
        try:
            # 从文件同步到内存
            success = self._sync_from_file()
            if success:
                logger.info("手动同步成功")
                return {"code": 0, "message": "同步成功：已将文件配置同步到内存", "sites_count": len(self._sites), "sites": list(self._sites.keys())}
            else:
                logger.warning("手动同步失败")
                return {"code": 500, "message": "同步失败，请查看日志"}
        except Exception as e:
            logger.error(f"手动同步出错: {str(e)}")
            return {"code": 500, "message": f"同步出错: {str(e)}"}
            
    def api_set_sync_interval(self, **kwargs):
        """
        API接口：设置同步间隔
        """
        interval = kwargs.get("interval")
        if not interval:
            return {"code": 400, "message": "缺少interval参数"}
            
        try:
            interval = int(interval)
            if interval < 60:
                return {"code": 400, "message": "同步间隔不能小于60秒"}
                
            # 更新同步间隔
            self._sync_interval = interval
            logger.info(f"同步间隔已更新为: {interval}秒")
            
            return {"code": 0, "message": f"同步间隔已设置为{interval}秒"}
        except Exception as e:
            logger.error(f"设置同步间隔出错: {str(e)}")
            return {"code": 500, "message": f"设置同步间隔出错: {str(e)}"}

    def submit_params(self, params: Dict[str, Any]):
        """
        处理用户提交的参数
        """
        logger.info(f"接收到用户提交的参数: {params}")
        
        # 如果提交了同步间隔参数，更新设置
        if 'sync_interval' in params:
            try:
                interval = int(params.get('sync_interval', 300))
                if interval < 60:
                    logger.warning(f"同步间隔过小: {interval}秒，已调整为最小值60秒")
                    interval = 60
                    
                self._sync_interval = interval
                logger.info(f"同步间隔已更新为: {interval}秒")
                
                # 如果已经在运行，重启同步任务以应用新设置
                if self._sync_running:
                    self._stop_auto_sync()
                    self._start_auto_sync()
            except Exception as e:
                logger.error(f"更新同步间隔设置失败: {str(e)}")
                
        return {"code": 0, "message": "设置已保存"}

    def api_get_status(self, **kwargs):
        """
        API接口：获取插件状态信息
        """
        # 获取配置文件修改时间
        file_mtime = "文件不存在"
        if os.path.exists(self.config_file):
            file_mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(self.config_file)))
            
        # 构建状态信息
        status_info = {
            "plugin_version": self.plugin_version,
            "sites_count": len(self._sites) if self._sites else 0,
            "sites_list": list(self._sites.keys()) if self._sites else [],
            "config_file": self.config_file,
            "config_file_mtime": file_mtime,
            "sync_interval": self._sync_interval,
            "sync_running": self._sync_running,
            "host_setting": settings.HOST,
            "api_url": f"{settings.HOST}/api/v1/plugin/twofahelper",
            "system_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        }
        
        return {"code": 0, "message": "成功", "data": status_info}

    def api_test(self, **kwargs):
        """
        API接口：测试连接
        """
        return {
            "code": 0, 
            "message": "API连接正常", 
            "data": {
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "sites_count": len(self._sites) if self._sites else 0,
                "plugin_version": self.plugin_version
            }
        }

    def api_dump_sites(self, **kwargs):
        """
        API接口：转储内存中的站点配置用于调试
        """
        logger.info("接收到转储站点请求")
        try:
            # 获取内存配置
            memory_sites = self._sites.copy() if self._sites else {}
            memory_sites_count = len(memory_sites)
            memory_sites_list = list(memory_sites.keys())
            
            # 读取文件配置
            file_sites = {}
            file_sites_count = 0
            file_sites_list = []
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        file_sites = json.load(f)
                    file_sites_count = len(file_sites)
                    file_sites_list = list(file_sites.keys())
                except Exception as e:
                    logger.error(f"读取配置文件失败: {str(e)}")
            
            # 比较差异
            only_in_memory = [site for site in memory_sites_list if site not in file_sites_list]
            only_in_file = [site for site in file_sites_list if site not in memory_sites_list]
            
            return {
                "code": 0,
                "message": "成功",
                "data": {
                    "memory": {
                        "sites_count": memory_sites_count,
                        "sites_list": memory_sites_list,
                        "sites_data": memory_sites
                    },
                    "file": {
                        "sites_count": file_sites_count,
                        "sites_list": file_sites_list,
                        "sites_data": file_sites
                    },
                    "diff": {
                        "only_in_memory": only_in_memory,
                        "only_in_file": only_in_file,
                        "is_identical": memory_sites == file_sites
                    }
                }
            }
        except Exception as e:
            logger.error(f"转储站点配置失败: {str(e)}")
            return {"code": 500, "message": f"转储站点配置失败: {str(e)}"}


# 插件类导出
plugin_class = twofahelper 