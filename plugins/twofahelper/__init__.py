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
from app.schemas import Response


class twofahelper(_PluginBase):
    # 插件名称
    plugin_name = "两步验证助手"
    # 插件描述
    plugin_desc = "管理两步验证码"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/madrays/MoviePilot-Plugins/main/icons/2fa.png"
    # 插件版本
    plugin_version = "1.2"
    # 插件作者
    plugin_author = "madrays"
    # 作者主页
    author_url = "https://github.com/madrays"
    # 插件配置项ID前缀
    plugin_config_prefix = "twofahelper_"
    # 加载顺序
    plugin_order = 20
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _sites = {}
    
    # 配置文件路径
    config_file = None

    def init_plugin(self, config: dict = None):
        """
        插件初始化 - 简化版，不再需要同步任务
        """
        # 直接使用settings获取配置路径
        data_path = self.get_data_path()
        
        # 确保目录存在
        if not os.path.exists(data_path):
            try:
                os.makedirs(data_path)
            except Exception as e:
                logger.error(f"创建数据目录失败: {str(e)}")
        
        self.config_file = os.path.join(data_path, "twofahelper_sites.json")
        
        # 初始化时从文件加载配置到内存
        self._sync_from_file()
        
        # 如果内存中没有配置，添加预设站点配置
        if not self._sites:
            # 生成预设站点配置
            self._sites = self._generate_default_sites()
            # 写入配置文件
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self._sites, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"写入配置文件失败: {str(e)}")
        
        logger.info(f"两步验证码助手初始化完成，已加载 {len(self._sites)} 个站点")
            
    def _generate_default_sites(self):
        """
        生成预设站点配置，用于新用户初始化
        
        :return: 预设站点配置字典
        """
        # 当前时间戳，用于确保新生成的秘钥每次都不同
        timestamp = int(time.time())
        
        # Google图标的Base64编码
        google_icon = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAAflBMVEVHcEw+qUb/3AAikf//yAD/ywD/3QAikv8vqERHr1b/3QBHr1Yikf//3ABHr1f///9Hr1b/zAD/3AAjkf//3QArn3hHr1YikaRHr1cik//tzwajyTMbpE3/ygAUo1j/0QAik6T/1QD/3gAjkqMikqT/4AD/2QD/1wD/0gD/zwAVaIySAAAAJnRSTlMA+r8grxA2/kb6d0b/////////////////RkaP//+v//+PRkf/r89PIHoAAAHbSURBVHgBfZPploMgDIUxUVyqdsO61Na27cL7P+AAgoC253j7+e4QSAD4j4OHk6LrHk6u/QM878cOk5NvPED7mT6ETr7tAfyVTYSuSoA/khsAd6YLoVsTcAZyL4AupOjqHuAcxhOBJgX/Bt7ozQms4aQA1vBmBOGE5fk8Q9gnQDbmZzfmVwIyIu8CdqNZBOStwBDvAvJN4IoXZJdidgdAXjJwjRngKgPE9Qp0z+se6ARAXDHgVuvc3Q2OiwJMsxZwc10rjQrfEnDvA6YhA6bsoYrXzFhdBs4EpJ5QFu5J5a4Jq2TgwkB0DyqX3FPnzWsG1gy4Ni1CTXbH/dTl8b4BLgzMpq1CTXKjwpZNXQ6rhYGV55LuDcnlwGUrgBUD/M5RkBwLm3MIeA9Q/RrQNcVHAHgUoPoVxdUPAAoB4yIGVEU+ALw6/DnZ0wG1Ae9aQe2nXmTAG4i8f8XPBKzXAuTvqYBJAPMvA6pvBpzXANXXoGyeBYYG2IaAzVcDLg1Q3QBuUwLuhGzXAKuvBrxLAa8bYOtGgPcJ2JWAeRoH9DfQgPk4YBgCAoBtUh0DzJMKmKc1UE5roJzWIGA8BIDlCGCbNMAyCTCPI2CZBhbGcQS8/wF7S25Y6uGfkAAAAABJRU5ErkJggg=="
        
        # GitHub图标的Base64编码
        github_icon = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAMAAACdt4HsAAAAflBMVEVHcEw2Njb///81NTU0NDQ2NjY1NTU4ODgzMzM3Nzf///8AAAD///////////////8fHx////////////////////8nJyf///////////////////////////////8xMTH///////////8sLCz///////////////////////8hISEzMzNJa6KsAAAAKXRSTlMA/rAQ79CEIEDPn2C/X++vcN+PQJ/fMFAgv8+PcM+AcO9gz4AgIP5wIJQ4PZsAAAKnSURBVFjD7ZbblqowDIZR5CAHUUTkIIpy0vd/wE2atrCcsVZm9pr5LhQ+m+ZP0xD9j8vN7avaxX8JQUR7dtPcrhEB73ucYX8nQJMF1jg7LoBa69wnfIYL9KrUWpMJ4gJwa7WqCG8LAW/VrZUE3AQ/VreWBIC3z77UCyrw56+x7gX4Vl2r3i1EoVK5g6gX6q3Ne41F8Npw3usOEuB9xzuZVeytw63MBYDCO905wFvgnAoHfq5zHRxQKZizYYD39EwJA2ZlUjpjQB4XMGZWiYYBs0KZYMCsFP1tCNBK0S8GzGp+6g1Y4NRWdQbQcwE/JrVV1VHWKbT+NJi9YytGZQdUQILsEdvj+yGZIu8QcGaALJhfYCzYV8C5xIA6FWBHJnrZQwAZKcDeBPDRRAXYjQDcnYoAMlHAfhNgRl0G8HsiQHfeBPDRRAGmFwAzGpIRoPs9FQAxJgO6IwOYKDAWbDLRPh0FUDfKgn2LbJY9GbwNM+AOPzuAtDTQOWkdAFg4mxfObw6/h80G/PzAABiPJy6BZA9x5Ckg+2dAD4Bz2TwGVgH3YwCswnlVcD9mZQHiDCCAbNgqhPOtbR4Yvx4GXl+cnyegCuGQb54FX6+vCQC4cFsKw2Gg+34I4CvKfTZ7MRSgZ62fC2/2BYDh5wV8fXzJILB+EID8WQDr+wFPCIcAj54DSL8WwGMgsXKnCk4WANIXAL4CUDQPISYDAOsLANsfANQ8hGgIwPo4Bejr3/MQogSA9QGwPnw9DyEiDkh9HMDRWPV+e+hxPx7YwTfDIz1G3JJ+8vLWEp72EwnPZkkC4jYQQEh7GyCkfRAgxOwRVYz2XYCQkyICyTYa4lHw2Y7+dLOEiCq7Pxvxfru5P8QQXNWb2/UH8iRFXS8ZbkgAAAAASUVORK5CYII="
        
        # 微软图标的Base64编码
        microsoft_icon = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAAaVBMVEVHcEzjQjTlbGPiMiHjRzriMyPiMyLjQzXlbGPiMyLkWE3jRDbiMyLkW1DiMyLjQjTiMyLkWU7iMyLjQjTlbGPiMyLiMyLiMyLjRDbjRDbjQzXjQzXkWE3kWU7kW1DkXFHlamHlbGPmbmTg5zXPAAAAGHRSTlMAfw8/H1/vzzB/z0+vT39vb59Pj49vv28Lgj2WAAAA1ElEQVR4AbXQV3LDMAxF0QdRLKJkW3JJ75n9bzKZiQM7GRbB+R9wQQB/NStrmVVjjqVTSqVYmixNsWv0nWS6FrjLo9TFRWT9URJO51Rsbq4uVRE8B1hYpSgCZx8WBSG4QCAIDkKnEzg4CCenk12Mg9lBYLdJcLcL2dkMkfQmREaLdVgU4WRlPmRnVycTq5RhYSu8SWxCFOmVmhhZMKNrNRUzgzfSam5meBu0mZ9ZOkQWc8PLdnXh8B7KZz3Az/T7/ZFPdKRvl0/Ht/zF+QY4pgaeeukKLQAAAABJRU5ErkJggg=="
        
        # 默认站点配置 - 使用常见的网站作为示例
        default_sites = {
            "Google": {
                "secret": f"JBSWY3DPEHPK3PXP{timestamp}",  # 使用标准TOTP测试密钥加时间戳
                "urls": ["https://accounts.google.com"],
                "icon": google_icon  # 使用Base64编码的图标
            },
            "GitHub": {
                "secret": f"NBSWY3DPEHPK3PXQ{timestamp}",
                "urls": ["https://github.com"],
                "icon": github_icon
            },
            "Microsoft": {
                "secret": f"HBSWY3DPEHPK3PXT{timestamp}",
                "urls": ["https://account.microsoft.com"],
                "icon": microsoft_icon
            }
        }
        
        return default_sites
    
    def _sync_from_file(self):
        """
        从配置文件同步到内存 - 精简版，移除多余日志
        """
        if not os.path.exists(self.config_file):
            # 清空内存中的配置
            if self._sites:
                self._sites = {}
            return False

        try:
            # 读取文件内容
            with open(self.config_file, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # 解析JSON
            new_sites = json.loads(file_content)
            
            # 更新内存中的配置
            self._sites = new_sites
            return True
        except json.JSONDecodeError as e:
            logger.error(f"配置文件JSON格式解析失败: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"读取配置文件失败: {str(e)}")
            return False

    def _sync_to_file(self):
        """
        将内存中的配置同步到文件 - 精简版
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._sites, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"将内存配置同步到文件失败: {str(e)}")
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

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        """
        获取插件仪表盘元信息
        返回示例：
            [{
                "key": "dashboard1", // 仪表盘的key，在当前插件范围唯一
                "name": "仪表盘1" // 仪表盘的名称
            }]
        """
        logger.info("获取仪表盘元信息")
        return [{
            "key": "totp_codes",
            "name": "两步验证码"
        }]

    def get_dashboard(self, key: str, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        """
        获取插件仪表盘页面，需要返回：1、仪表板col配置字典；2、全局配置（自动刷新等）；3、仪表板页面元素配置json（含数据）
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
        
        # 获取验证码
        codes = self.get_all_codes()
        
        # 列配置 - 优化布局，每行显示4个卡片，整体宽度限制为50%
        col_config = {
            "cols": 16,  # 增加总列数
            "md": 4,     # 每行4个
            "sm": 8,     # 小屏幕每行2个

        }
        
        # 全局配置
        global_config = {
            "refresh": 5,  # 5秒自动刷新
            "title": "两步验证码",
            "subtitle": f"共 {len(codes)} 个站点",
            "border": True,
            "style": "max-width: 850px; margin: 0 auto;" # 限制最大宽度并居中
        }
        
        # 页面元素
        elements = []
        
        if not codes:
            # 无验证码时显示提示信息
            elements.append({
                "component": "VAlert",
                "props": {
                    "type": "warning",
                    "text": "未配置任何站点或配置无效，请先添加站点配置。"
                }
            })
            return col_config, global_config, elements
        
        # 使用VRow和VCol创建网格布局
        row_content = []
        
        # 颜色循环，为每个卡片分配不同颜色
        colors = ["primary", "success", "info", "warning", "error", "secondary"]
        color_index = 0
        
        for site, code_info in codes.items():
            code = code_info.get("code", "")
            remaining_seconds = code_info.get("remaining_seconds", 0)
            urls = code_info.get("urls", [])
            
            # 获取站点URL用于点击跳转
            site_url = ""
            if urls and isinstance(urls, list) and len(urls) > 0:
                site_url = urls[0]
            
            # 循环使用颜色
            color = colors[color_index % len(colors)]
            color_index += 1
            
            # 获取站点图标
            favicon_info = self._get_favicon_url(urls, site)
            
            # 为每个站点创建一个卡片，保证内容完整显示
            card = {
                "component": "VCol",
                "props": {
                    "cols": 16,  # 匹配总列数
                    "sm": 8,     # 小屏幕每行2个
                    "md": 4,     # 每行4个
                    "lg": 4,     # 大屏幕每行4个
                    "class": "pa-1"  # 减小内边距
                },
                "content": [
                    {
                    "component": "VCard",
                    "props": {
                            "class": "mx-auto",
                            "elevation": 1,
                            "height": "160px",  # 增加高度确保显示完整
                            "variant": "outlined"
                        },
                        "content": [
                            {
                                "component": "VCardItem",
                                "props": {
                                    "class": "pa-1"  # 减小内边距
                    },
                    "content": [
                        {
                            "component": "VCardTitle",
                            "props": {
                                            "class": "d-flex align-center py-0"  # 减小顶部内边距
                                        },
                                        "content": [
                                            # 替换为自定义图标容器，避免CDN失败
                                            {
                                                "component": "div",
                                                "props": {
                                                    "class": "mr-2 d-flex align-center justify-center",
                                                    "style": f"width: 16px; height: 16px; border-radius: 2px; background-color: {self._get_color_for_site(site)}; overflow: hidden;"
                                                },
                                                "content": [
                                                    {
                                                        "component": "span",
                                                        "props": {
                                                            "style": "color: white; font-size: 10px; font-weight: bold;"
                                                        },
                                                        "text": site[0].upper() if site else "?"
                                                    },
                                                    # 添加脚本处理图标加载
                                                    {
                                                        "component": "script",
                                                        "text": f'''
                                                        (() => {{
                                                          const loadImage = (url, callback) => {{
                                                            const img = new Image();
                                                            img.onload = () => callback(img, true);
                                                            img.onerror = () => callback(img, false);
                                                            img.src = url;
                                                          }};
                                                          
                                                          const container = document.currentScript.parentNode;
                                                          container.removeChild(document.currentScript);
                                                          
                                                          // 尝试 favicon.ico
                                                          loadImage("{favicon_info.get('ico', '')}", (img, success) => {{
                                                            if (success) {{
                                                              container.innerHTML = '';
                                                              img.style.width = '100%';
                                                              img.style.height = '100%';
                                                              container.appendChild(img);
                                                            }} else {{
                                                              // 尝试 favicon.png
                                                              loadImage("{favicon_info.get('png', '')}", (img, success) => {{
                                                                if (success) {{
                                                                  container.innerHTML = '';
                                                                  img.style.width = '100%';
                                                                  img.style.height = '100%';
                                                                  container.appendChild(img);
                                                                }} else {{
                                                                  // 尝试 Google Favicon
                                                                  loadImage("{favicon_info.get('google', '')}", (img, success) => {{
                                                                    if (success) {{
                                                                      container.innerHTML = '';
                                                                      img.style.width = '100%';
                                                                      img.style.height = '100%';
                                                                      container.appendChild(img);
                                                                    }} else {{
                                                                      // 尝试 DuckDuckGo
                                                                      loadImage("{favicon_info.get('ddg', '')}", (img, success) => {{
                                                                        if (success) {{
                                                                          container.innerHTML = '';
                                                                          img.style.width = '100%';
                                                                          img.style.height = '100%';
                                                                          container.appendChild(img);
                                                                        }}
                                                                      }});
                                                                    }}
                                                                  }});
                                                                }}
                                                              }});
                                                            }}
                                                          }});
                                                        }})();
                                                        '''
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "a",
                                                "props": {
                                                    "href": site_url,
                                                    "target": "_blank",
                                                    "class": "text-decoration-none text-caption text-truncate flex-grow-1",  # 使用更小的文字
                                                    "style": "max-width: 100%; color: inherit;",
                                                    "title": f"访问 {site}"
                                                },
                                                "text": site
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "component": "VDivider"
                        },
                        {
                            "component": "VCardText",
                            "props": {
                                    "class": "text-center py-1 px-2"  # 减小内边距
                            },
                            "content": [
                                {
                                    "component": "div",
                                    "props": {
                                            "class": "otp-code font-weight-bold",
                                            "id": f"code-{site}",
                                            "style": "white-space: pre; overflow: visible; font-family: monospace; letter-spacing: 2px; font-size: 1.6rem;"  # 增大字体和间距
                                    },
                                        "text": code
                                },
                                {
                                    "component": "VProgressLinear",
                                    "props": {
                                            "model-value": remaining_seconds / 30 * 100,
                                            "color": color,
                                            "height": 2,
                                            "class": "mt-1 mb-0",  # 减小间距
                                            "rounded": True
                                    }
                                },
                                {
                                    "component": "div",
                                    "props": {
                                            "class": "text-caption"
                                    },
                                        "text": f"{remaining_seconds}秒"
                                }
                            ]
                        },
                        {
                            "component": "VCardActions",
                            "props": {
                                    "class": "py-0 px-2 d-flex justify-center"  # 减小内边距
                            },
                            "content": [
                                {
                                    "component": "VBtn",
                                    "props": {
                                        "size": "small",  # 增大按钮尺寸
                                            "variant": "tonal",
                                            "color": color,
                                            "class": "copy-button",
                                            "block": True,
                                            "onclick": f"""
                                            var code = document.getElementById('code-{site}').textContent.trim();
                                            navigator.clipboard.writeText(code).then(() => {{
                                              this.textContent = '已复制';
                                              setTimeout(() => {{ this.textContent = '复制'; }}, 1000);
                                            }}).catch(() => {{
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
                                    "text": "复制"
                                }
                            ]
                        }
                    ]
                    }
                ]
            }
            
            row_content.append(card)
        
        # 创建一个VRow包含所有卡片
        elements.append({
            "component": "VRow",
            "props": {
                "class": "pa-1",  # 减小内边距
                "dense": True     # 使行更密集
            },
            "content": row_content
        })
        
        # 添加自定义样式
        elements.append({
            "component": "style",
            "text": """
            .copy-button {
                min-width: 60px !important;
                letter-spacing: 0 !important;
                height: 28px !important;
                font-size: 0.875rem !important;
            }
            .otp-code {
                white-space: pre !important;
                font-family: 'Roboto Mono', monospace !important;
                letter-spacing: 2px !important;
                font-weight: 700 !important;
                display: block !important;
                width: 100% !important;
                text-align: center !important;
                font-size: 1.6rem !important;  /* 增大字体 */
                line-height: 1.4 !important;   /* 增加行高 */
                overflow: visible !important;
                padding: 6px 0 !important;
                margin: 0 !important;
                user-select: all !important;  /* 允许一键全选 */
            }
            .time-text {
                font-size: 0.75rem !important;
                margin-top: 4px !important;
            }
            """
        })
        
        logger.info(f"仪表盘页面：生成了 {len(codes)} 个站点的卡片")
        
        return col_config, global_config, elements

    def _get_favicon_url(self, urls, site_name):
        """
        从站点URL获取网站图标，使用三重获取机制
        
        :param urls: 站点URL列表
        :param site_name: 站点名称
        :return: 图标URL或图标选项
        """
        # 默认图标 - 使用站点名称首字母替代
        default_icon = ""
        
        if not urls or not isinstance(urls, list) or len(urls) == 0:
            return default_icon
        
        try:
            # 获取第一个URL
            url = urls[0]
            
            # 解析域名
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            
            if not domain:
                return default_icon
            
            # 方法1: 直接尝试网站的favicon.ico
            favicon_ico = f"https://{domain}/favicon.ico"
            
            # 方法2: 尝试favicon.png
            favicon_png = f"https://{domain}/favicon.png"
            
            # 方法3: 使用Google的favicon服务获取图标
            google_favicon = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
            
            # 方法4: 使用DuckDuckGo的图标服务
            ddg_favicon = f"https://icons.duckduckgo.com/ip3/{domain}.ico"
            
            # 返回所有可能的图标URL，让前端按顺序尝试
            return {
                "ico": favicon_ico,
                "png": favicon_png,
                "google": google_favicon,
                "ddg": ddg_favicon,
                "domain": domain,
                "site_name": site_name,
                "first_letter": site_name[0].upper() if site_name else "?"
            }
            
        except Exception as e:
            # 出错时返回空字符串
            return default_icon

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API
        """
        return [{
            "path": "/config",
            "endpoint": self.get_config,
            "methods": ["GET"],
            "summary": "获取配置",
            "description": "获取2FA配置数据",
        }, {
            "path": "/update_config",
            "endpoint": self.update_config,
            "methods": ["POST"],
            "summary": "更新配置",
            "description": "更新2FA配置数据",
        }, {
            "path": "/get_codes",
            "endpoint": self.get_totp_codes,
            "methods": ["GET"],
            "summary": "获取所有TOTP验证码",
            "description": "获取所有站点的TOTP验证码",
        }]

    def get_config(self, apikey: str) -> Response:
        """
        获取配置文件内容
        """
        if apikey != settings.API_TOKEN:
            return Response(success=False, message="API令牌错误!")
        
        try:
            # 读取配置文件
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                return Response(success=True, message="获取成功", data=config_data)
            else:
                return Response(success=True, message="配置文件不存在", data={})
        except Exception as e:
            logger.error(f"读取配置文件失败: {str(e)}")
            return Response(success=False, message=f"读取配置失败: {str(e)}")

    def update_config(self, apikey: str, request: dict) -> Response:
        """
        更新配置文件内容
        """
        if apikey != settings.API_TOKEN:
            return Response(success=False, message="API令牌错误!")
            
        try:
            # 更新内存中的配置
            self._sites = request
            
            # 写入配置文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(request, f, ensure_ascii=False, indent=2)
                
            return Response(success=True, message="更新成功")
        except Exception as e:
            logger.error(f"更新配置文件失败: {str(e)}")
            return Response(success=False, message=f"更新配置失败: {str(e)}")

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        配置页面 - 简化版，只显示当前配置
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
        
        # 构造表单 - 只读模式，简化版
        form = [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'style',
                        'text': """
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
                                            'density': 'compact'
                                        },
                                        'content': [
                                            {
                                                'component': 'div',
                                                'text': f'两步验证助手 - 共 {sites_count} 个站点'
                                            },
                                            {
                                                'component': 'div',
                                                'props': {
                                                    'class': 'mt-2',
                                                    'style': 'border: 1px solid #e0f7fa; padding: 8px; border-radius: 4px; background-color: #e1f5fe;'
                                                },
                                                'content': [
                                                    {
                                                        'component': 'div',
                                                        'props': {
                                                            'class': 'font-weight-bold mb-1'
                                                        },
                                                        'text': '📌 浏览器扩展'
                                                    },
                                                    {
                                                        'component': 'div',
                                                        'props': {
                                                            'class': 'text-body-2'
                                                        },
                                                        'text': '本插件必须安装配套的浏览器扩展配合：'
                                                    },
                                                    {
                                                        'component': 'div',
                                                        'props': {
                                                            'class': 'mt-1 d-flex align-center flex-wrap'
                                                        },
                                                        'content': [
                                                            {
                                                                'component': 'a',
                                                                'props': {
                                                                    'href': 'https://github.com/madrays/MoviePilot-Plugins/raw/main/TOTP-Extension.zip',
                                                                    'target': '_blank',
                                                                    'class': 'text-decoration-none mr-3 mb-1',
                                                                    'style': 'color: #1976d2; display: inline-flex; align-items: center;'
                                                                },
                                                                'content': [
                                                                    {
                                                                        'component': 'v-icon',
                                                                        'props': {
                                                                            'icon': 'mdi-download',
                                                                            'size': 'small',
                                                                            'class': 'mr-1'
                                                                        }
                                                                    },
                                                                    {
                                                                        'component': 'span',
                                                                        'text': '下载扩展'
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                'component': 'a',
                                                                'props': {
                                                                    'href': 'https://github.com/madrays/MoviePilot-Plugins/blob/main/README.md#totp浏览器扩展说明',
                                                                    'target': '_blank',
                                                                    'class': 'text-decoration-none mb-1',
                                                                    'style': 'color: #1976d2; display: inline-flex; align-items: center;'
                                                                },
                                                                'content': [
                                                                    {
                                                                        'component': 'v-icon',
                                                                        'props': {
                                                                            'icon': 'mdi-information-outline',
                                                                            'size': 'small',
                                                                            'class': 'mr-1'
                                                                        }
                                                                    },
                                                                    {
                                                                        'component': 'span',
                                                                        'text': '安装说明'
                                                                    }
                                                                ]
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        'component': 'div',
                                                        'props': {
                                                            'class': 'text-caption mt-1',
                                                            'style': 'color: #546e7a;'
                                                        },
                                                        'text': '使用方法：下载后解压，在浏览器扩展管理页面选择"加载已解压的扩展程序"并选择解压后的文件夹。'
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
        
        # 返回表单数据
        return form, {}

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
        
        # 使用整数时间戳，确保与 Google Authenticator 同步
        current_time = int(time.time())
        time_step = 30
        
        # 计算下一个完整周期的时间
        next_valid_time = (current_time // time_step + 1) * time_step
        remaining_seconds = next_valid_time - current_time
        
        # 计算进度百分比
        progress_percent = 100 - ((remaining_seconds / time_step) * 100)
        
        # 为每个站点生成一个卡片
        card_index = 0
        colors = ['primary', 'success', 'info', 'warning', 'error', 'secondary']
        
        # 创建一个临时验证码字典
        verification_codes = {}
        
        for site, data in self._sites.items():
            try:
                # 获取密钥并确保正确的格式
                secret = data.get("secret", "").strip().upper()
                # 移除所有空格和破折号
                secret = secret.replace(" ", "").replace("-", "")
                
                # 确保密钥是有效的 Base32
                try:
                    import base64
                    # 添加填充
                    padding_length = (8 - (len(secret) % 8)) % 8
                    secret += '=' * padding_length
                    # 验证是否为有效的 Base32
                    base64.b32decode(secret, casefold=True)
                except Exception as e:
                    logger.error(f"站点 {site} 的密钥格式无效: {str(e)}")
                    continue

                # 计算当前时间戳对应的计数器值
                counter = current_time // 30

                # 使用标准 TOTP 参数
                totp = pyotp.TOTP(
                    secret,
                    digits=6,           # 标准 6 位验证码
                    interval=30,        # 30 秒更新间隔
                    digest=hashlib.sha1 # SHA1 哈希算法（RFC 6238 标准）
                )
                
                # 使用计数器值生成验证码
                now_code = totp.generate_otp(counter)  # 直接使用计数器生成验证码
                
                # 保存验证码到临时字典中
                verification_codes[site] = {
                    "code": now_code,
                    "site_name": site,
                    "urls": data.get("urls", []),
                    "remaining_seconds": remaining_seconds,
                    "progress_percent": int(((time_step - remaining_seconds) / time_step) * 100)
                }
                
                logger.info(f"站点 {site} 生成验证码成功: counter={counter}, remaining={remaining_seconds}s")
                
                # 根据卡片序号选择不同的颜色
                color = colors[card_index % len(colors)]
                card_index += 1
                
                # 获取站点URL和图标
                urls = data.get("urls", [])
                site_url = ""
                if urls and isinstance(urls, list) and len(urls) > 0:
                    site_url = urls[0]
                
                favicon_info = self._get_favicon_url(urls, site)
                
                # 构建美观卡片，确保验证码完整显示
                cards.append({
                    'component': 'VCol',
                    'props': {
                        'cols': 16,  # 匹配总列数
                        'sm': 8,     # 小屏幕每行2个
                        'md': 4,     # 每行4个
                        'lg': 4,     # 大屏幕每行4个
                        'class': 'pa-1'  # 减小内边距
                    },
                    'content': [{
                        'component': 'VCard',
                        'props': {
                            'variant': 'outlined',
                            'class': 'ma-0 totp-card',  # 减小外边距
                            'elevation': 1,             # 减小阴影
                            'min-height': '160px'       # 增加最小高度确保显示完整
                        },
                        'content': [
                            {
                                'component': 'VCardTitle',
                                'props': {
                                    'class': 'd-flex align-center py-0'  # 减小顶部内边距
                                },
                                'content': [
                                    {
                                        'component': 'div',
                                        'props': {
                                            'class': 'mr-2 d-flex align-center justify-center',
                                            'style': f"width: 16px; height: 16px; border-radius: 2px; background-color: {self._get_color_for_site(site)}; overflow: hidden;"
                                        },
                                        'content': [
                                            {
                                                'component': 'span',
                                                'props': {
                                                    'style': 'color: white; font-size: 10px; font-weight: bold;'
                                                },
                                                'text': site[0].upper() if site else "?"
                                            },
                                            # 添加脚本处理图标加载
                                            {
                                                'component': 'script',
                                                'text': f'''
                                                (() => {{
                                                  const loadImage = (url, callback) => {{
                                                    const img = new Image();
                                                    img.onload = () => callback(img, true);
                                                    img.onerror = () => callback(img, false);
                                                    img.src = url;
                                                  }};
                                                  
                                                  const container = document.currentScript.parentNode;
                                                  container.removeChild(document.currentScript);
                                                  
                                                  // 尝试 favicon.ico
                                                  loadImage("{favicon_info.get('ico', '')}", (img, success) => {{
                                                    if (success) {{
                                                      container.innerHTML = '';
                                                      img.style.width = '100%';
                                                      img.style.height = '100%';
                                                      container.appendChild(img);
                                                    }} else {{
                                                      // 尝试 favicon.png
                                                      loadImage("{favicon_info.get('png', '')}", (img, success) => {{
                                                        if (success) {{
                                                          container.innerHTML = '';
                                                          img.style.width = '100%';
                                                          img.style.height = '100%';
                                                          container.appendChild(img);
                                                        }} else {{
                                                          // 尝试 Google Favicon
                                                          loadImage("{favicon_info.get('google', '')}", (img, success) => {{
                                                            if (success) {{
                                                              container.innerHTML = '';
                                                              img.style.width = '100%';
                                                              img.style.height = '100%';
                                                              container.appendChild(img);
                                                            }} else {{
                                                              // 尝试 DuckDuckGo
                                                              loadImage("{favicon_info.get('ddg', '')}", (img, success) => {{
                                                                if (success) {{
                                                                  container.innerHTML = '';
                                                                  img.style.width = '100%';
                                                                  img.style.height = '100%';
                                                                  container.appendChild(img);
                                                                }}
                                                              }});
                                                            }}
                                                          }});
                                                        }}
                                                      }});
                                                    }}
                                                  }});
                                                }})();
                                                '''
                                            }
                                        ]
                                    },
                                    {
                                        'component': 'a',
                                        'props': {
                                            'href': site_url,
                                            'target': '_blank',
                                            'class': 'text-decoration-none text-caption text-truncate flex-grow-1',  # 使用更小的文字
                                            'style': 'max-width: 100%; color: inherit;',
                                            'title': f'访问 {site}'
                                        },
                                        'text': site
                                    }
                                ]
                            },
                            {
                                'component': 'VDivider'
                            },
                            {
                                'component': 'VCardText',
                                'props': {
                                    'class': 'text-center py-1 px-2'  # 减小内边距
                                },
                                'content': [{
                                    'component': 'div',
                                    'props': {
                                        'class': 'otp-code font-weight-bold',
                                        'id': f'code-{site}',
                                        'style': 'white-space: pre; overflow: visible; font-family: monospace; letter-spacing: 2px; font-size: 1.6rem;'  # 增大字体和间距
                                    },
                                    'text': now_code
                                }]
                            },
                            {
                                'component': 'VCardText',
                                'props': {
                                    'class': 'py-1 px-2'  # 减小内边距
                                },
                                'content': [
                                    {
                                        'component': 'VProgressLinear',
                                        'props': {
                                            'model-value': progress_percent,
                                            'color': color,
                                            'height': 2,  # 减小进度条高度
                                            'class': 'progress-bar',
                                            'rounded': True
                                        }
                                    },
                                    {
                                        'component': 'div',
                                        'props': {
                                            'class': 'text-caption text-center mt-1 time-text'  # 使用更小的字体
                                        },
                                        'text': f'{remaining_seconds}秒'
                                    }
                                ]
                            },
                            {
                                'component': 'VCardActions',
                                'props': {
                                    'class': 'py-0 px-2 d-flex justify-center'  # 减小内边距
                                },
                                'content': [
                                    {
                                        'component': 'VBtn',
                                        'props': {
                                            'size': 'small',  # 增大按钮尺寸
                                            'variant': 'tonal',
                                            'color': color,
                                            'class': 'copy-button',
                                            'block': True,
                                            'onclick': f"""
                                            var code = document.getElementById('code-{site}').textContent.trim();
                                            navigator.clipboard.writeText(code).then(() => {{
                                              this.textContent = '已复制';
                                              setTimeout(() => {{ this.textContent = '复制'; }}, 1000);
                                            }}).catch(() => {{
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
        # 不再需要停止同步任务
        pass

    def get_all_codes(self):
        """
        获取所有站点的TOTP验证码
        """
        logger.info(f"获取验证码：当前内存中有 {len(self._sites)} 个站点")
        
        codes = {}
        # 使用整数时间戳，确保与 Google Authenticator 同步
        current_time = int(time.time())
        time_step = 30
        remaining_seconds = time_step - (current_time % time_step)
        
        for site, data in self._sites.items():
            try:
                # 获取密钥并确保正确的格式
                secret = data.get("secret", "").strip().upper()
                # 移除所有空格和破折号
                secret = secret.replace(" ", "").replace("-", "")
                
                # 确保密钥是有效的 Base32
                try:
                    import base64
                    # 添加填充
                    padding_length = (8 - (len(secret) % 8)) % 8
                    secret += '=' * padding_length
                    # 验证是否为有效的 Base32
                    base64.b32decode(secret, casefold=True)
                except Exception as e:
                    logger.error(f"站点 {site} 的密钥格式无效: {str(e)}")
                    continue

                # 计算当前时间戳对应的计数器值
                counter = current_time // 30

                # 使用标准 TOTP 参数
                totp = pyotp.TOTP(
                    secret,
                    digits=6,           # 标准 6 位验证码
                    interval=30,        # 30 秒更新间隔
                    digest=hashlib.sha1 # SHA1 哈希算法（RFC 6238 标准）
                )
                
                # 使用计数器值生成验证码
                now_code = totp.generate_otp(counter)  # 直接使用计数器生成验证码
                
                # 创建或更新站点的验证码信息
                if site in codes and 'progress_percent' in codes[site]:
                    codes[site]["progress_percent"] = int(codes[site]["progress_percent"])  # 转换为整数
                else:
                    codes[site] = {
                        "code": now_code,
                        "site_name": site,
                        "urls": data.get("urls", []),
                        "remaining_seconds": remaining_seconds,
                        "progress_percent": int(((time_step - remaining_seconds) / time_step) * 100)
                    }
                
                logger.info(f"站点 {site} 生成验证码成功: counter={counter}, remaining={remaining_seconds}s")
            except Exception as e:
                logger.error(f"生成站点 {site} 的验证码失败: {e}")
        
        logger.info(f"生成验证码成功，共 {len(codes)} 个站点")
        return codes

    def submit_params(self, params: Dict[str, Any]):
        """
        处理用户提交的参数 - 简化版，不再需要处理同步间隔
        """
        logger.info(f"接收到用户提交的参数: {params}")
        return {"code": 0, "message": "设置已保存"}

    def get_totp_codes(self, apikey: str = None):
        """
        API接口: 获取所有TOTP验证码
        """
        if apikey and apikey != settings.API_TOKEN:
            return {"code": 2, "message": "API令牌错误!"}
            
        try:
            # 确保首先加载最新配置
            self._sync_from_file()
            
            # 获取验证码列表
            codes = self.get_all_codes()
            
            # 增强输出内容
            for site, data in codes.items():
                # 添加额外信息
                data["site_name"] = site
                
                # 处理图标 - 优先使用配置中的base64图标
                if "icon" in data and data["icon"] and data["icon"].startswith("data:image"):
                    # 已经是base64图标，保持不变
                    pass
                # 如果没有图标但有URL，尝试获取favicon
                elif "urls" in data and data["urls"]:
                    favicon_info = self._get_favicon_url(data["urls"], site)
                    if isinstance(favicon_info, dict):
                        data["favicon_options"] = favicon_info
                        # 保留原始图标url以保持兼容性
                        data["icon"] = favicon_info.get("ico", "") 
                    else:
                        data["icon"] = favicon_info
            
            return {
                "code": 0,
                "message": "成功",
                "data": codes
            }
        except Exception as e:
            logger.error(f"获取TOTP验证码失败: {str(e)}")
            return {
                "code": 1,
                "message": f"获取TOTP验证码失败: {str(e)}"
            }

    def _get_color_for_site(self, site_name):
        """
        根据站点名称生成一致的颜色
        
        :param site_name: 站点名称
        :return: HSL颜色字符串
        """
        # 使用站点名称生成一个哈希值，确保相同的站点名称总是产生相同的颜色
        hash_value = 0
        for char in site_name:
            hash_value += ord(char)
        
        # 生成HSL颜色，让颜色分布更均匀
        hue = hash_value % 360
        saturation = 70
        lightness = 60
        
        return f"hsl({hue}, {saturation}%, {lightness}%)"


# 插件类导出
plugin_class = twofahelper 