"""
M-Team站点处理
"""
import re
import json
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin
import time

import requests
from bs4 import BeautifulSoup

from app.log import logger
from plugins.nexusinvitee.sites import _ISiteHandler


class MTeamHandler(_ISiteHandler):
    """
    M-Team站点处理类
    """
    # 站点类型标识
    site_schema = "mteam"
    
    @classmethod
    def match(cls, site_url: str) -> bool:
        """
        判断是否匹配M-Team站点
        :param site_url: 站点URL
        :return: 是否匹配
        """
        # M-Team站点的特征
        mteam_features = [
            "m-team",
            "pt.m-team",
            "kp.m-team",
            "zp.m-team"
        ]
        
        site_url_lower = site_url.lower()
        for feature in mteam_features:
            if feature in site_url_lower:
                logger.info(f"匹配到M-Team站点特征: {feature}")
                return True
        
        return False
    
    def parse_invite_page(self, site_info: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
        """
        使用API方式解析M-Team站点邀请数据
        :param site_info: 站点信息
        :param session: 已配置好的请求会话
        :return: 解析结果
        """
        site_name = site_info.get("name", "")
        site_url = site_info.get("url", "")
        api_key = site_info.get("apikey", "")
        authorization = site_info.get("token", "") # 使用token字段作为Authorization
        user_id = site_info.get("userid", "")
        
        # 记录站点配置信息（隐藏敏感内容）
        logger.info(f"站点 {site_name} 配置信息: URL={site_url}, API Key设置={bool(api_key)}, Token设置={bool(authorization)}, 用户ID设置={bool(user_id)}")
        
        result = {
            "invite_status": {
                "can_invite": False,
                "reason": "",
                "permanent_count": 0,
                "temporary_count": 0
            },
            "invitees": []
        }
        
        try:
            # 检查API认证信息
            if not api_key or not authorization:
                logger.error(f"站点 {site_name} API认证信息不完整")
                result["invite_status"]["reason"] = "API认证信息不完整，请在站点设置中配置API Key和Authorization"
                return result
            
            # 提取主域名
            domain = self._extract_domain(site_url)
            logger.info(f"站点 {site_name} 从URL {site_url} 提取到域名: {domain}")
            
            # 使用正确的API URL格式：https://api.域名/api/路径
            api_base_url = f"https://api.{domain}/api"
            logger.info(f"站点 {site_name} 使用API基础URL: {api_base_url}")
            
            # 打印测试DNS解析结果
            try:
                import socket
                api_domain = f"api.{domain}"
                logger.info(f"尝试进行DNS解析: {api_domain}")
                ip_address = socket.gethostbyname(api_domain)
                logger.info(f"DNS解析结果: {api_domain} -> {ip_address}")
            except Exception as dns_error:
                logger.error(f"DNS解析失败: {str(dns_error)}")
            
            # 准备API请求头 - 更新为与示例代码相同的格式
            headers = {
                "Content-Type": "application/json",
                "User-Agent": site_info.get("ua", "Mozilla/5.0"),
                "Accept": "application/json, text/plain, */*",
                "Authorization": authorization,
                "x-api-key": api_key,  # 使用x-api-key代替API-Key
                "ts": str(int(time.time()))  # 添加时间戳
            }
            logger.debug(f"站点 {site_name} 请求头设置: Content-Type={headers['Content-Type']}, User-Agent={headers['User-Agent'][:15]}..., x-api-key设置={bool(headers.get('x-api-key'))}, ts={headers['ts']}")
            
            # 重置会话并添加API认证头
            session.headers.clear()
            session.headers.update(headers)
            
            # 首先验证登录状态并获取用户ID
            if not user_id:
                # 尝试获取用户ID
                logger.info(f"站点 {site_name} 未配置用户ID，尝试从API获取")
                user_id = self._get_user_id(api_base_url, session, site_name)
                
            # 即使无法获取用户ID也继续尝试获取后宫数据
            if not user_id:
                logger.warning(f"站点 {site_name} 无法获取用户ID，但继续尝试获取后宫数据")
                # 给出警告，但不提前返回结果
                result["invite_status"]["reason"] = "用户ID未知，部分功能可能受限"
                
            # 1. 获取用户邀请信息(名额)
            invite_info_url = f"{api_base_url}/invite/getUserInviteInfo"
            logger.info(f"站点 {site_name} 获取邀请信息: {invite_info_url}")
            
            response = None
            try:
                # 如果有用户ID，使用参数；如果没有，尝试直接请求
                params = {"uid": user_id} if user_id else {}
                logger.info(f"站点 {site_name} 邀请信息请求参数: {params}")
                
                # 使用POST方法而不是GET
                response = session.post(invite_info_url, params=params, timeout=(10, 30))
                if response.status_code != 200:
                    logger.error(f"站点 {site_name} 获取邀请信息失败，状态码: {response.status_code}")
                    # 记录错误，但继续执行其他API请求
                    if not result["invite_status"]["reason"]:
                        result["invite_status"]["reason"] = f"获取邀请信息失败，状态码: {response.status_code}"
                else:
                    invite_info = response.json()
                    logger.debug(f"站点 {site_name} 邀请信息响应: {invite_info}")
                    
                    if invite_info.get("code") == 0 and invite_info.get("data"):
                        data = invite_info.get("data", {})
                        # 解析永久和临时邀请名额
                        perm_count = data.get("permanent", 0)
                        temp_count = data.get("temporary", 0)
                        
                        logger.info(f"站点 {site_name} API获取到邀请数量: 永久={perm_count}, 临时={temp_count}")
                        
                        result["invite_status"].update({
                            "permanent_count": perm_count,
                            "temporary_count": temp_count,
                            "can_invite": perm_count > 0 or temp_count > 0
                        })
                        
                        if perm_count > 0 or temp_count > 0:
                            result["invite_status"]["reason"] = f"可用邀请数: 永久={perm_count}, 临时={temp_count}"
                        elif not result["invite_status"]["reason"]:
                            result["invite_status"]["reason"] = "没有可用的邀请名额"
                    else:
                        error_msg = invite_info.get("message", "未知错误")
                        logger.error(f"站点 {site_name} 获取邀请信息API返回错误: {error_msg}")
                        if not result["invite_status"]["reason"]:
                            result["invite_status"]["reason"] = f"获取邀请信息API返回错误: {error_msg}"
            except Exception as e:
                logger.error(f"站点 {site_name} 获取邀请信息异常: {str(e)}")
                if not result["invite_status"]["reason"]:
                    result["invite_status"]["reason"] = f"获取邀请信息异常: {str(e)}"
            
            # 2. 获取用户邀请历史(被邀请人)
            invite_history_url = f"{api_base_url}/invite/getUserInviteHistory"
            logger.info(f"站点 {site_name} 获取邀请历史: {invite_history_url}")
            
            try:
                # 如果有用户ID，使用参数；如果没有，尝试直接请求
                params = {"uid": user_id} if user_id else {}
                logger.info(f"站点 {site_name} 邀请历史请求参数: {params}")
                
                # 使用POST方法
                response = session.post(invite_history_url, params=params, timeout=(10, 30))
                if response.status_code != 200:
                    logger.error(f"站点 {site_name} 获取邀请历史失败，状态码: {response.status_code}")
                else:
                    invite_history = response.json()
                    logger.debug(f"站点 {site_name} 邀请历史响应: {invite_history}")
                    
                    if invite_history.get("code") == 0 and invite_history.get("data"):
                        data = invite_history.get("data", {})
                        # 解析被邀请人列表
                        invitees_list = data.get("invitees", [])
                        
                        if invitees_list:
                            logger.info(f"站点 {site_name} API获取到 {len(invitees_list)} 个后宫成员")
                            
                            for invitee in invitees_list:
                                if not isinstance(invitee, dict):
                                    continue
                                    
                                # 处理分享率
                                ratio_value = 0
                                try:
                                    uploaded = invitee.get("uploaded", 0)
                                    downloaded = invitee.get("downloaded", 0)
                                    if downloaded > 0:
                                        ratio_value = uploaded / downloaded
                                    else:
                                        ratio_value = float('inf')
                                except (ZeroDivisionError, TypeError):
                                    pass
                                    
                                ratio_str = str(round(ratio_value, 2)) if ratio_value != float('inf') else "∞"
                                
                                # 检查用户状态
                                status = invitee.get("status", "正常")
                                is_disabled = status == "disabled" or invitee.get("enabled") is False
                                
                                # 创建邀请用户记录
                                user = {
                                    "username": invitee.get("username", ""),
                                    "email": invitee.get("email", ""),
                                    "uploaded": self._format_size(invitee.get("uploaded", 0)),
                                    "downloaded": self._format_size(invitee.get("downloaded", 0)),
                                    "ratio": ratio_str,
                                    "status": status,
                                    "enabled": "No" if is_disabled else "Yes",
                                    # 添加后宫加成字段
                                    "seed_bonus": str(invitee.get("inviteeBonus", 0)),
                                    "seeding": str(invitee.get("seedingCount", 0)),
                                    "seeding_size": self._format_size(invitee.get("seedingSize", 0)),
                                    "seed_magic": str(invitee.get("seedMagic", 0)),
                                    "last_seed_report": invitee.get("lastSeedReport", "")
                                }
                                result["invitees"].append(user)
                        else:
                            logger.info(f"站点 {site_name} 无后宫成员")
                    else:
                        error_msg = invite_history.get("message", "未知错误")
                        logger.error(f"站点 {site_name} 获取邀请历史API返回错误: {error_msg}")
            except Exception as e:
                logger.error(f"站点 {site_name} 获取邀请历史异常: {str(e)}")
            
            # 3. 如果已经获取了数据，更新最后访问时间
            try:
                # 删除x-api-key，只使用Authorization进行更新
                update_headers = headers.copy()
                if "x-api-key" in update_headers:
                    del update_headers["x-api-key"]
                
                session.headers.clear()
                session.headers.update(update_headers)
                
                # 更新最后访问时间
                update_url = f"{api_base_url}/member/updateLastBrowse"
                logger.info(f"站点 {site_name} 更新最后访问时间: {update_url}")
                
                update_response = session.post(update_url, timeout=(10, 30))
                if update_response and update_response.status_code == 200:
                    update_info = update_response.json() or {}
                    if "code" in update_info and int(update_info["code"]) == 0:
                        logger.info(f"站点 {site_name} 成功更新最后访问时间")
                    else:
                        logger.warning(f"站点 {site_name} 更新最后访问时间失败: {update_info.get('message', '未知错误')}")
                else:
                    logger.warning(f"站点 {site_name} 更新最后访问时间请求失败，状态码: {update_response.status_code if update_response else 'None'}")
            except Exception as e:
                logger.warning(f"站点 {site_name} 更新最后访问时间异常: {str(e)}")
            
            # 如果API请求的后宫数据为空且域名解析失败，尝试使用HTML解析方式
            if not result["invitees"]:
                logger.info(f"站点 {site_name} API获取后宫数据为空，尝试使用HTML解析方式")
                try:
                    # 重置会话头
                    session.headers.clear()
                    session.headers.update({
                        "User-Agent": site_info.get("ua", "Mozilla/5.0"),
                        "Cookie": site_info.get("cookie", "")
                    })
                    
                    # 获取邀请页面
                    invite_page_url = f"https://{domain}/invite.php"
                    logger.info(f"站点 {site_name} 获取邀请页面: {invite_page_url}")
                    
                    html_response = session.get(invite_page_url, timeout=(10, 30))
                    if html_response.status_code == 200:
                        html_content = html_response.text
                        # 使用HTML解析方式获取数据
                        html_result = self._parse_mteam_invite_page(site_name, html_content)
                        
                        # 更新结果
                        if html_result["invitees"]:
                            logger.info(f"站点 {site_name} HTML解析到 {len(html_result['invitees'])} 个后宫成员")
                            result["invitees"] = html_result["invitees"]
                        
                        # 如果API没有获取到邀请信息，使用HTML解析的结果
                        if result["invite_status"]["permanent_count"] == 0 and result["invite_status"]["temporary_count"] == 0:
                            result["invite_status"]["permanent_count"] = html_result["invite_status"]["permanent_count"]
                            result["invite_status"]["temporary_count"] = html_result["invite_status"]["temporary_count"]
                            result["invite_status"]["can_invite"] = html_result["invite_status"]["can_invite"]
                            
                            # 更新原因
                            if html_result["invite_status"]["reason"]:
                                result["invite_status"]["reason"] = html_result["invite_status"]["reason"]
                except Exception as e:
                    logger.error(f"站点 {site_name} HTML解析获取后宫数据异常: {str(e)}")
            
            return result
            
        except Exception as e:
            logger.error(f"解析站点 {site_name} 邀请页面失败: {str(e)}")
            result["invite_status"]["reason"] = f"解析邀请页面失败: {str(e)}"
            return result
            
    def _get_user_id(self, api_base_url: str, session: requests.Session, site_name: str) -> str:
        """
        从API获取用户ID，只在站点配置中未提供用户ID时使用
        :param api_base_url: API基础URL
        :param session: 请求会话
        :param site_name: 站点名称
        :return: 用户ID
        """
        try:
            # 记录当前会话头信息
            logger.debug(f"站点 {site_name} 请求会话头信息: {list(session.headers.keys())}")
            
            # 尝试不同的API接口获取用户ID
            apis_to_try = [
                {"path": "/member/profile", "method": "POST", "desc": "个人资料"},
                {"path": "/member/getUserInfo", "method": "POST", "desc": "用户信息"},
                {"path": "/member/updateLastBrowse", "method": "POST", "desc": "更新浏览时间"}
            ]
            
            for api in apis_to_try:
                try:
                    url = f"{api_base_url}{api['path']}"
                    method = api['method']
                    desc = api['desc']
                    
                    logger.info(f"站点 {site_name} 尝试通过{desc}获取用户ID: {url} (方法: {method})")
                    
                    # 执行请求
                    if method == "POST":
                        response = session.post(url, timeout=(10, 30))
                    else:
                        response = session.get(url, timeout=(10, 30))
                        
                    logger.info(f"站点 {site_name} {desc}请求状态码: {response.status_code}")
                    
                    if response.status_code != 200:
                        logger.error(f"站点 {site_name} 获取{desc}失败，状态码: {response.status_code}")
                        continue
                        
                    # 解析响应
                    response_data = response.json()
                    logger.debug(f"站点 {site_name} {desc}响应: {json.dumps(response_data)[:200]}...")
                    
                    if response_data.get("code") == 0 and response_data.get("data"):
                        data = response_data.get("data", {})
                        # 尝试不同的可能字段名
                        for id_field in ["id", "uid", "userId", "user_id"]:
                            user_id = data.get(id_field)
                            if user_id:
                                logger.info(f"站点 {site_name} 从{desc}中获取到用户ID: {user_id} (字段: {id_field})")
                                return str(user_id)
                        
                        # 如果没有直接找到ID字段，尝试检查数据中的其他嵌套对象
                        logger.debug(f"站点 {site_name} 在{desc}中未找到ID字段，尝试检查嵌套数据")
                        for key, value in data.items():
                            if isinstance(value, dict) and ("id" in value or "uid" in value):
                                nested_id = value.get("id") or value.get("uid")
                                if nested_id:
                                    logger.info(f"站点 {site_name} 从{desc}嵌套数据中获取到用户ID: {nested_id} (嵌套字段: {key})")
                                    return str(nested_id)
                except Exception as api_error:
                    logger.error(f"站点 {site_name} 通过{desc}获取用户ID异常: {str(api_error)}")
                    
            # 所有方法都失败
            logger.error(f"站点 {site_name} 所有API方法均未能获取用户ID")
            
        except Exception as e:
            logger.error(f"站点 {site_name} 获取用户ID异常: {str(e)}")
            # 记录异常栈跟踪
            import traceback
            logger.debug(f"站点 {site_name} 获取用户ID异常栈跟踪: {traceback.format_exc()}")
            
        return ""
    
    def _extract_domain(self, url: str) -> str:
        """
        从URL中提取主域名
        :param url: 站点URL
        :return: 主域名
        """
        if not url:
            logger.warning("URL为空，使用默认域名: m-team.cc")
            return "m-team.cc"
            
        # 尝试提取完整域名（包括子域名）
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            hostname = parsed_url.netloc
            
            # 如果解析出了域名，直接返回
            if hostname:
                logger.debug(f"从URL {url} 提取到完整域名: {hostname}")
                # 检查域名是否包含子域名
                domain_parts = hostname.split('.')
                if len(domain_parts) > 2 and domain_parts[0] != 'www':
                    # 如果有子域名(非www)，只保留主域名部分
                    main_domain = '.'.join(domain_parts[-2:]) if domain_parts[-1] else '.'.join(domain_parts[-3:-1])
                    logger.info(f"处理后的主域名: {main_domain}")
                    return main_domain
                return hostname
                
            # 备用正则方法
            hostname_match = re.search(r'//([^/]+)', url)
            if hostname_match:
                hostname = hostname_match.group(1)
                logger.debug(f"通过正则从URL {url} 提取到域名: {hostname}")
                return hostname
        except Exception as e:
            logger.warning(f"解析URL域名失败: {str(e)}，尝试备用方法")
        
        # 尝试m-team特定的正则匹配
        domain_match = re.search(r'//(?:[\w-]+\.)*?(m-team\.[\w.]+)', url, re.IGNORECASE)
        if domain_match:
            domain = domain_match.group(1)
            logger.info(f"通过m-team特定正则提取到域名: {domain}")
            return domain
            
        # 无法解析，返回原始域名
        logger.warning(f"无法从URL {url} 提取域名，使用默认域名: m-team.cc")
        return "m-team.cc"  # 默认域名
    
    def _parse_mteam_invite_page(self, site_name: str, html_content: str) -> Dict[str, Any]:
        """
        解析M-Team邀请页面HTML内容
        :param site_name: 站点名称
        :param html_content: HTML内容
        :return: 解析结果
        """
        try:
            result = {
                "invitees": [],
                "invite_status": {
                    "can_invite": False,
                    "permanent_count": 0,
                    "temporary_count": 0,
                    "reason": ""
                }
            }

            # 记录HTML内容长度，用于调试
            logger.debug(f"站点 {site_name} 收到HTML内容长度: {len(html_content)}")
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 特殊处理: 直接提取邀请名额和状态
            # 1. 永久和临时邀请数量
            perm_invite_match = re.search(r'永久邀請\s*\((\d+)\)', html_content)
            temp_invite_match = re.search(r'限時邀請\s*\((\d+)\)', html_content)
            
            if perm_invite_match:
                perm_count = int(perm_invite_match.group(1))
                result["invite_status"]["permanent_count"] = perm_count
                logger.info(f"站点 {site_name} HTML解析到永久邀请数量: {perm_count}")
                
            if temp_invite_match:
                temp_count = int(temp_invite_match.group(1))
                result["invite_status"]["temporary_count"] = temp_count
                logger.info(f"站点 {site_name} HTML解析到临时邀请数量: {temp_count}")
                
            # 更新邀请状态
            perm_count = result["invite_status"]["permanent_count"]
            temp_count = result["invite_status"]["temporary_count"]
            
            if perm_count > 0 or temp_count > 0:
                result["invite_status"]["can_invite"] = True
                result["invite_status"]["reason"] = f"可用邀请数: 永久={perm_count}, 临时={temp_count}"
            else:
                result["invite_status"]["reason"] = "没有可用的邀请名额"
            
            # 2. 提取已邀请用户
            # 查找所有包含用户信息的卡片
            all_cards = soup.select('.ant-card')
            logger.info(f"站点 {site_name} 找到 {len(all_cards)} 个卡片")
            
            user_card = None
            # 查找包含"被邀者當前狀態"标题的卡片
            for card in all_cards:
                card_title = card.select_one('.ant-card-head-title')
                if card_title and ("被邀者" in card_title.text or "当前状态" in card_title.text or "後宮" in card_title.text):
                    user_card = card
                    logger.info(f"站点 {site_name} 找到用户卡片，标题: {card_title.text}")
                    break
            
            if user_card:
                # 尝试从卡片中提取表格
                tables = user_card.select('table')
                logger.info(f"站点 {site_name} 在用户卡片中找到 {len(tables)} 个表格")
                
                if tables:
                    for table in tables:
                        # 处理表格
                        self._process_invitee_table(table, result)
                else:
                    # 如果卡片中没有表格，尝试直接从HTML中提取用户数据
                    self._extract_user_data_from_html(user_card, result)
            
            # 3. 如果上面方法没有找到用户，尝试使用正则表达式直接从HTML中提取
            if not result["invitees"]:
                self._extract_users_with_regex(html_content, result)
            
            # 4. 尝试从脚本块中提取JSON数据
            if not result["invitees"]:
                self._extract_users_from_scripts(html_content, result, site_name)
            
            # 5. 最后尝试使用一般方法
            if not result["invitees"]:
                # 尝试找到所有表格并处理
                all_tables = soup.select('table')
                logger.info(f"站点 {site_name} 找到 {len(all_tables)} 个表格")
                
                for table in all_tables:
                    headers = table.select('th')
                    if headers:
                        header_texts = [h.get_text().strip() for h in headers]
                        # 查找包含特定列的表格
                        if any(("用户名" in h or "用戶名" in h) for h in header_texts) and \
                          any(("邮箱" in h or "郵箱" in h) for h in header_texts):
                            logger.info(f"站点 {site_name} 找到可能的用户表格: {header_texts}")
                            self._process_invitee_table(table, result)
            
            # 6. 直接处理表格体
            if not result["invitees"]:
                tbody_elements = soup.select('.ant-table-tbody')
                for tbody in tbody_elements:
                    rows = tbody.select('tr')
                    if rows:
                        logger.info(f"站点 {site_name} 找到表格体，包含 {len(rows)} 行")
                        for row in rows:
                            self._process_invitee_row(row, result)
            
            # 7. 特殊处理：找到所有包含类似用户名和邮箱的行
            if not result["invitees"]:
                # 尝试查找所有可能包含用户信息的行
                self._find_user_elements(soup, result)
            
            # 记录解析结果
            if result["invitees"]:
                logger.info(f"站点 {site_name} 最终解析到 {len(result['invitees'])} 个后宫成员")
            else:
                # 手动创建示例数据，用于测试
                self._create_sample_data(html_content, result)
                if result["invitees"]:
                    logger.info(f"站点 {site_name} 从HTML中提取出 {len(result['invitees'])} 个示例后宫成员")
                else:
                    logger.warning(f"站点 {site_name} 未能从HTML解析到后宫成员数据")

            return result

        except Exception as e:
            logger.error(f"解析M-Team邀请页面失败: {str(e)}")
            return {
                "invite_status": {
                    "can_invite": False,
                    "reason": f"解析邀请页面失败: {str(e)}",
                    "permanent_count": 0,
                    "temporary_count": 0
                },
                "invitees": []
            }
    
    def _extract_user_data_from_html(self, element, result):
        """
        从HTML元素中直接提取用户数据
        :param element: BeautifulSoup元素
        :param result: 结果字典
        """
        try:
            # 查找所有包含用户名的元素
            user_elements = element.select('a[href*="/profile/detail/"]')
            logger.info(f"找到 {len(user_elements)} 个用户链接")
            
            for user_elem in user_elements:
                username = user_elem.get_text().strip()
                if not username:
                    continue
                
                # 尝试找到用户所在的行或单元格
                parent_row = user_elem.find_parent('tr')
                if parent_row:
                    cells = parent_row.select('td')
                    if len(cells) >= 2:
                        # 提取邮箱和其他信息
                        email = cells[1].get_text().strip() if len(cells) > 1 else ""
                        uploaded = cells[2].get_text().strip() if len(cells) > 2 else "0 B"
                        downloaded = cells[3].get_text().strip() if len(cells) > 3 else "0 B"
                        ratio = cells[4].get_text().strip() if len(cells) > 4 else "0"
                        status = cells[5].get_text().strip() if len(cells) > 5 else "已确认"
                        
                        # 创建用户记录
                        user = {
                            "username": username,
                            "email": email,
                            "uploaded": uploaded,
                            "downloaded": downloaded,
                            "ratio": ratio,
                            "status": status,
                            "enabled": "No" if "禁用" in status else "Yes",
                            "seed_bonus": "0",
                            "seeding": "0",
                            "seeding_size": "0 B",
                            "seed_magic": "0",
                            "last_seed_report": ""
                        }
                        result["invitees"].append(user)
        except Exception as e:
            logger.warning(f"从HTML提取用户数据失败: {str(e)}")
    
    def _extract_users_with_regex(self, html_content, result):
        """
        使用正则表达式从HTML中提取用户数据
        :param html_content: HTML内容
        :param result: 结果字典
        """
        try:
            # 查找所有用户链接和邮箱组合
            user_pattern = r'href="/profile/detail/\d+">.*?<strong>(.*?)</strong>.*?</td>\s*<td[^>]*>([\w\.-]+@[\w\.-]+\.\w+)'
            matches = re.findall(user_pattern, html_content, re.DOTALL)
            
            if matches:
                logger.info(f"通过正则表达式找到 {len(matches)} 个用户")
                
                for username, email in matches:
                    # 创建用户记录
                    user = {
                        "username": username.strip(),
                        "email": email.strip(),
                        "uploaded": "未知",
                        "downloaded": "未知",
                        "ratio": "未知",
                        "status": "已确认",
                        "enabled": "Yes",
                        "seed_bonus": "0",
                        "seeding": "0",
                        "seeding_size": "0 B",
                        "seed_magic": "0",
                        "last_seed_report": ""
                    }
                    result["invitees"].append(user)
        except Exception as e:
            logger.warning(f"使用正则表达式提取用户失败: {str(e)}")
    
    def _extract_users_from_scripts(self, html_content, result, site_name):
        """
        从脚本块中提取用户数据
        :param html_content: HTML内容
        :param result: 结果字典
        :param site_name: 站点名称
        """
        try:
            # 尝试查找包含用户数据的脚本块
            script_patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*({[\s\S]*?});',
                r'window\.__NEXT_DATA__\s*=\s*({[\s\S]*?});',
                r'var\s+userData\s*=\s*({[\s\S]*?});',
                r'var\s+invitees\s*=\s*(\[[\s\S]*?\]);'
            ]
            
            for pattern in script_patterns:
                script_match = re.search(pattern, html_content)
                if script_match:
                    try:
                        json_data = json.loads(script_match.group(1))
                        logger.info(f"站点 {site_name} 从脚本中提取到JSON数据")
                        
                        # 查找用户数据
                        if isinstance(json_data, dict):
                            # 直接查找invitees字段
                            if "invitees" in json_data and isinstance(json_data["invitees"], list):
                                for invitee in json_data["invitees"]:
                                    if isinstance(invitee, dict) and "username" in invitee and "email" in invitee:
                                        # 处理用户数据
                                        user = {
                                            "username": invitee.get("username", ""),
                                            "email": invitee.get("email", ""),
                                            "uploaded": self._format_size(invitee.get("uploaded", 0)) if isinstance(invitee.get("uploaded"), (int, float)) else str(invitee.get("uploaded", "未知")),
                                            "downloaded": self._format_size(invitee.get("downloaded", 0)) if isinstance(invitee.get("downloaded"), (int, float)) else str(invitee.get("downloaded", "未知")),
                                            "ratio": str(invitee.get("ratio", "未知")),
                                            "status": invitee.get("status", "已确认"),
                                            "enabled": "No" if invitee.get("status") == "disabled" else "Yes",
                                            "seed_bonus": str(invitee.get("inviteeBonus", "0")),
                                            "seeding": str(invitee.get("seedingCount", "0")),
                                            "seeding_size": self._format_size(invitee.get("seedingSize", 0)),
                                            "seed_magic": str(invitee.get("seedMagic", "0")),
                                            "last_seed_report": str(invitee.get("lastSeedReport", ""))
                                        }
                                        result["invitees"].append(user)
                                
                                logger.info(f"站点 {site_name} 从JSON中提取到 {len(result['invitees'])} 个用户")
                            
                            # 查找可能嵌套的数据
                            if not result["invitees"]:
                                self._search_nested_json(json_data, result)
                    except json.JSONDecodeError:
                        logger.warning(f"站点 {site_name} 解析脚本中的JSON数据失败")
        except Exception as e:
            logger.warning(f"从脚本提取用户数据失败: {str(e)}")
    
    def _search_nested_json(self, data, result, max_depth=3, current_depth=0):
        """
        递归搜索嵌套的JSON数据
        :param data: JSON数据
        :param result: 结果字典
        :param max_depth: 最大递归深度
        :param current_depth: 当前递归深度
        """
        if current_depth > max_depth:
            return
            
        if isinstance(data, dict):
            # 直接查找invitees字段
            if "invitees" in data and isinstance(data["invitees"], list):
                for invitee in data["invitees"]:
                    if isinstance(invitee, dict) and "username" in invitee and "email" in invitee:
                        # 处理用户数据
                        user = {
                            "username": invitee.get("username", ""),
                            "email": invitee.get("email", ""),
                            "uploaded": self._format_size(invitee.get("uploaded", 0)) if isinstance(invitee.get("uploaded"), (int, float)) else str(invitee.get("uploaded", "未知")),
                            "downloaded": self._format_size(invitee.get("downloaded", 0)) if isinstance(invitee.get("downloaded"), (int, float)) else str(invitee.get("downloaded", "未知")),
                            "ratio": str(invitee.get("ratio", "未知")),
                            "status": invitee.get("status", "已确认"),
                            "enabled": "No" if invitee.get("status") == "disabled" else "Yes",
                            "seed_bonus": str(invitee.get("inviteeBonus", "0")),
                            "seeding": str(invitee.get("seedingCount", "0")),
                            "seeding_size": self._format_size(invitee.get("seedingSize", 0)),
                            "seed_magic": str(invitee.get("seedMagic", "0")),
                            "last_seed_report": str(invitee.get("lastSeedReport", ""))
                        }
                        result["invitees"].append(user)
            
            # 递归查找
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    self._search_nested_json(value, result, max_depth, current_depth + 1)
        
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    self._search_nested_json(item, result, max_depth, current_depth + 1)
    
    def _find_user_elements(self, soup, result):
        """
        寻找所有可能包含用户信息的元素
        :param soup: BeautifulSoup对象
        :param result: 结果字典
        """
        try:
            # 查找所有用户链接
            user_links = soup.select('a[href*="/profile/detail/"]')
            logger.info(f"找到 {len(user_links)} 个用户链接")
            
            for user_link in user_links:
                username = ""
                strong_elem = user_link.select_one('strong')
                if strong_elem:
                    username = strong_elem.get_text().strip()
                else:
                    username = user_link.get_text().strip()
                
                if not username:
                    continue
                
                # 查找最近的邮箱
                parent_row = user_link.find_parent('tr')
                if parent_row:
                    # 查找同一行中的所有单元格
                    cells = parent_row.select('td')
                    if len(cells) >= 2:
                        # 尝试在单元格中找到邮箱
                        for cell in cells:
                            cell_text = cell.get_text().strip()
                            if '@' in cell_text and '.' in cell_text and len(cell_text) > 5:
                                # 可能是邮箱
                                email = cell_text
                                
                                # 创建用户记录
                                user = {
                                    "username": username,
                                    "email": email,
                                    "uploaded": "未知",
                                    "downloaded": "未知",
                                    "ratio": "未知",
                                    "status": "已确认",
                                    "enabled": "Yes",
                                    "seed_bonus": "0",
                                    "seeding": "0",
                                    "seeding_size": "0 B",
                                    "seed_magic": "0",
                                    "last_seed_report": ""
                                }
                                result["invitees"].append(user)
                                break
        except Exception as e:
            logger.warning(f"查找用户元素失败: {str(e)}")
    
    def _create_sample_data(self, html_content, result):
        """
        从HTML源码创建示例用户数据
        :param html_content: HTML内容
        :param result: 结果字典
        """
        try:
            # 查找所有可能的用户名和邮箱
            username_pattern = r'<strong>([\w\.-]+)</strong>'
            email_pattern = r'([\w\.-]+@[\w\.-]+\.\w+)'
            
            usernames = re.findall(username_pattern, html_content)
            emails = re.findall(email_pattern, html_content)
            
            # 限制最多处理10个用户
            max_users = min(len(usernames), len(emails), 10)
            
            if max_users > 0:
                logger.info(f"从HTML中提取出 {max_users} 个潜在用户")
                
                for i in range(max_users):
                    username = usernames[i]
                    email = emails[i]
                    
                    # 跳过明显不是用户名或邮箱的情况
                    if len(username) < 3 or '.' not in email or '@' not in email:
                        continue
                    
                    # 创建示例用户记录
                    user = {
                        "username": username,
                        "email": email,
                        "uploaded": "未知",
                        "downloaded": "未知",
                        "ratio": "未知",
                        "status": "已确认",
                        "enabled": "Yes",
                        "seed_bonus": "0",
                        "seeding": "0",
                        "seeding_size": "0 B",
                        "seed_magic": "0",
                        "last_seed_report": ""
                    }
                    result["invitees"].append(user)
        except Exception as e:
            logger.warning(f"创建示例数据失败: {str(e)}")

    def _process_invitee_table(self, table, result):
        """
        处理邀请成员表格
        :param table: BeautifulSoup表格元素
        :param result: 结果字典
        """
        try:
            # 获取表头
            headers = table.select('th')
            header_texts = [h.get_text().strip() for h in headers]
            
            # 定位列索引
            username_idx = next((i for i, h in enumerate(header_texts) if "用户名" in h or "用戶名" in h), 0)
            email_idx = next((i for i, h in enumerate(header_texts) if "邮箱" in h or "郵箱" in h), 1)
            upload_idx = next((i for i, h in enumerate(header_texts) if "上传" in h or "上傳" in h), 2)
            download_idx = next((i for i, h in enumerate(header_texts) if "下载" in h or "下載" in h), 3)
            ratio_idx = next((i for i, h in enumerate(header_texts) if "分享率" in h), 4)
            status_idx = next((i for i, h in enumerate(header_texts) if "状态" in h or "狀態" in h), 5)
            
            # 处理表格行
            rows = table.select('tbody tr')
            for row in rows:
                cells = row.select('td')
                if len(cells) > max(username_idx, email_idx, upload_idx, download_idx, ratio_idx, status_idx):
                    # 提取用户名
                    username_cell = cells[username_idx]
                    username = ""
                    username_elem = username_cell.select_one('strong')
                    if username_elem:
                        username = username_elem.get_text().strip()
                    else:
                        # 尝试其他方式提取用户名
                        username = username_cell.get_text().strip()
                        
                    # 提取其他信息
                    email = cells[email_idx].get_text().strip()
                    uploaded = cells[upload_idx].get_text().strip()
                    downloaded = cells[download_idx].get_text().strip()
                    ratio = cells[ratio_idx].get_text().strip()
                    status = cells[status_idx].get_text().strip()
                    
                    # 判断状态
                    enabled = "Yes"
                    if "禁用" in status or "disabled" in status.lower():
                        enabled = "No"
                    
                    # 创建用户记录
                    user = {
                        "username": username,
                        "email": email,
                        "uploaded": uploaded,
                        "downloaded": downloaded,
                        "ratio": ratio,
                        "status": status,
                        "enabled": enabled,
                        # 添加后宫加成字段
                        "seed_bonus": "0",
                        "seeding": "0",
                        "seeding_size": "0 B",
                        "seed_magic": "0",
                        "last_seed_report": ""
                    }
                    result["invitees"].append(user)
        except Exception as e:
            logger.warning(f"处理邀请成员表格失败: {str(e)}")
            
    def _process_invitee_row(self, row, result):
        """
        处理单个邀请成员行
        :param row: BeautifulSoup行元素
        :param result: 结果字典
        """
        try:
            cells = row.select('td')
            if len(cells) >= 5:  # 至少需要用户名、邮箱、上传、下载、分享率
                # 尝试提取用户名
                username = ""
                username_cell = cells[0]
                strong_elem = username_cell.select_one('strong')
                if strong_elem:
                    username = strong_elem.get_text().strip()
                else:
                    # 尝试其他方式提取用户名
                    a_elem = username_cell.select_one('a')
                    if a_elem:
                        username = a_elem.get_text().strip()
                    else:
                        username = username_cell.get_text().strip()
                
                # 提取邮箱和其他数据
                email = cells[1].get_text().strip() if len(cells) > 1 else ""
                uploaded = cells[2].get_text().strip() if len(cells) > 2 else "0 B"
                downloaded = cells[3].get_text().strip() if len(cells) > 3 else "0 B"
                ratio = cells[4].get_text().strip() if len(cells) > 4 else "0"
                status = cells[5].get_text().strip() if len(cells) > 5 else "未知"
                
                # 判断状态
                enabled = "Yes"
                if "禁用" in status or "disabled" in status.lower():
                    enabled = "No"
                
                # 创建用户记录
                user = {
                    "username": username,
                    "email": email,
                    "uploaded": uploaded,
                    "downloaded": downloaded,
                    "ratio": ratio,
                    "status": status,
                    "enabled": enabled,
                    # 默认值
                    "seed_bonus": "0",
                    "seeding": "0",
                    "seeding_size": "0 B",
                    "seed_magic": "0",
                    "last_seed_report": ""
                }
                result["invitees"].append(user)
        except Exception as e:
            logger.warning(f"处理邀请成员行失败: {str(e)}")

    def _format_size(self, size_bytes: int) -> str:
        """
        格式化文件大小
        :param size_bytes: 字节数
        :return: 格式化后的大小字符串
        """
        try:
            if not isinstance(size_bytes, (int, float)):
                return str(size_bytes)
                
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.2f} {unit}"
                size_bytes /= 1024.0
            return f"{size_bytes:.2f} PB"
        except Exception as e:
            logger.warning(f"格式化大小失败: {str(e)}")
            return "0 B"
    
    def _get_ratio_health(self, ratio: float) -> str:
        """
        根据分享率计算健康状态
        :param ratio: 分享率
        :return: 健康状态
        """
        if ratio >= 1e20:
            return "excellent"
        elif ratio >= 1.0:
            return "good"
        elif ratio < 1.0:
            return "warning"
        else:
            return "danger"

    def _get_ratio_label(self, ratio: float) -> List[str]:
        """
        根据分享率获取分享率标签
        :param ratio: 分享率
        :return: 分享率标签
        """
        if ratio < 0:
            return ["危险", "red"]
        elif ratio < 1.0:
            return ["较低", "orange"]
        elif ratio >= 1.0:
            return ["良好", "green"]
        else:
            return ["未知", "gray"] 