"""
蝶粉站点处理
"""
import re
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.log import logger
from plugins.nexusinvitee.sites import _ISiteHandler


class ButterflyHandler(_ISiteHandler):
    """
    蝶粉站点处理类
    """
    # 站点类型标识
    site_schema = "butterfly"
    
    @classmethod
    def match(cls, site_url: str) -> bool:
        """
        判断是否匹配蝶粉站点
        :param site_url: 站点URL
        :return: 是否匹配
        """
        # 蝶粉站点的特征 - 域名中包含butterfly或者站点名称为蝶粉
        butterfly_features = [
            "butterfly",  # 域名特征
            "discfan",    # 蝶粉官方域名
            "dmhy"        # 蝶粉可能的域名特征
        ]
        
        site_url_lower = site_url.lower()
        for feature in butterfly_features:
            if feature in site_url_lower:
                logger.info(f"匹配到蝶粉站点特征: {feature}")
                return True
        
        return False
    
    def parse_invite_page(self, site_name: str, site_url: str, content: str) -> Dict[str, Any]:
        """
        解析邀请页面
        :param site_name: 站点名称
        :param site_url: 站点URL
        :param content: 页面内容
        :return: 解析结果
        """
        try:
            # 创建会话并设置 Cookie
            session = self.create_session(site_url, self.site_cookie)
            
            # 获取所有邀请页面数据
            page_url = site_url
            if not page_url.endswith('/myrequests.php') and not page_url.endswith('/invite.php'):
                # 尝试不同的邀请页面路径
                test_paths = ['/myrequests.php', '/invite.php']
                for path in test_paths:
                    test_url = urljoin(site_url, path)
                    try:
                        resp = session.get(test_url, timeout=10)
                        if resp.status_code == 200:
                            page_url = test_url
                            break
                    except Exception as e:
                        logger.debug(f"站点 {site_name} 测试路径 {path} 失败: {str(e)}")
            
            logger.info(f"站点 {site_name} 使用邀请页面: {page_url}")
            
            # 开始递归获取所有页面
            result = {}
            self._fetch_all_invite_pages(site_name, site_url, page_url, session, result, page_num=1)
            
            return result
        except Exception as e:
            logger.error(f"站点 {site_name} 解析邀请页面失败: {str(e)}")
            logger.exception(e)
            return {}
    
    def _fetch_all_invite_pages(self, site_name: str, site_url: str, page_url: str, session: requests.Session, result: Dict[str, Any], page_num: int = 1, max_pages: int = 20):
        """
        递归获取所有邀请页面数据
        :param site_name: 站点名称
        :param site_url: 站点基础URL
        :param page_url: 当前页面URL
        :param session: 会话
        :param result: 累积的结果字典
        :param page_num: 当前页码，用于日志
        :param max_pages: 最大页数限制，防止无限循环
        """
        if page_num > max_pages:
            logger.warning(f"站点 {site_name} 达到最大页数限制 {max_pages}，停止获取")
            return
            
        try:
            logger.info(f"站点 {site_name} 正在获取第 {page_num} 页数据: {page_url}")
            response = session.get(page_url, timeout=(10, 30))
            response.raise_for_status()
            
            # 解析当前页面内容
            current_page_result = self._parse_butterfly_invite_page(site_name, response.text)
            
            # 合并邀请者数据
            if "invitees" in current_page_result and current_page_result["invitees"]:
                if page_num == 1:
                    # 第一页，直接使用解析结果中的邀请状态和邀请者
                    result.update(current_page_result)
                else:
                    # 后续页，只合并邀请者列表
                    result["invitees"].extend(current_page_result["invitees"])
                
                logger.info(f"站点 {site_name} 第 {page_num} 页解析到 {len(current_page_result['invitees'])} 个后宫成员")
            
            # 查找下一页链接 - 支持多种分页样式
            soup = BeautifulSoup(response.text, 'html.parser')
            has_next_page = False
            next_url = None
            
            # 蝶粉站点分页样式多样，尝试各种可能的选择器
            # 1. 标准分页类
            pagination_selectors = [
                '.nexus-pagination', '.pagenavi', '.page-link', '.pages', 
                'div.pages', 'div.page', 'div.pagenav', 'p.pagelink'
            ]
            
            for selector in pagination_selectors:
                pagination = soup.select_one(selector)
                if pagination:
                    # 检查"下一页"链接是否可用
                    next_page_candidates = []
                    
                    # 查找标题有分页提示的链接
                    for title_attr in ['Alt+Pagedown', 'page=next', 'next page', '下一页']:
                        link = pagination.select_one(f'a[title="{title_attr}"]')
                        if link and not any(cls in link.parent.get('class', []) for cls in ['gray', 'disabled']):
                            next_page_candidates.append(link)
                    
                    # 查找包含下一页文本的链接
                    for link in pagination.select('a'):
                        link_text = link.get_text().strip().lower()
                        next_indicators = ['下一页', '下一頁', 'next', '&gt;&gt;', '&gt;', '>>', '>']
                        if any(text in link_text for text in next_indicators):
                            if not any(cls in link.parent.get('class', []) for cls in ['gray', 'disabled']):
                                next_page_candidates.append(link)
                    
                    # 使用第一个找到的有效链接
                    if next_page_candidates:
                        next_url = urljoin(site_url, next_page_candidates[0].get('href'))
                        has_next_page = True
                        logger.info(f"站点 {site_name} 在 {selector} 中找到下一页: {next_url}")
                        break
            
            # 2. 如果没有找到标准分页，查找页面中所有可能的"下一页"链接
            if not has_next_page:
                # 查找所有<a>标签中包含下一页文本的链接
                next_indicators = ['下一页', '下一頁', 'next', '&gt;&gt;', '&gt;', '>>', '>']
                for link in soup.select('a'):
                    link_text = link.get_text().strip().lower()
                    if any(text in link_text for text in next_indicators):
                        # 检查链接是否看起来是分页链接
                        href = link.get('href', '')
                        if href and ('page=' in href or 'p=' in href or 'pg=' in href or re.search(r'/\d+$', href)):
                            if not any(cls in link.parent.get('class', []) for cls in ['gray', 'disabled']):
                                next_url = urljoin(site_url, href)
                                has_next_page = True
                                logger.info(f"站点 {site_name} 在页面中找到下一页链接: {next_url}")
                                break
            
            # 3. 检查URL中的分页参数并构建下一页URL
            if not has_next_page:
                # 检查当前页面URL中的分页参数
                current_page_param = None
                next_page_value = None
                
                # 检查常见的分页参数
                page_param_patterns = [
                    (r'[?&]page=(\d+)', 'page'),
                    (r'[?&]p=(\d+)', 'p'),
                    (r'[?&]pg=(\d+)', 'pg'),
                    (r'[?&]pagenum=(\d+)', 'pagenum'),
                    (r'[?&]pagenumber=(\d+)', 'pagenumber'),
                    (r'/page/(\d+)', '/page/')
                ]
                
                for pattern, param_name in page_param_patterns:
                    match = re.search(pattern, page_url)
                    if match:
                        current_page_param = param_name
                        current_page_value = int(match.group(1))
                        next_page_value = current_page_value + 1
                        break
                
                # 如果找到了分页参数，构建下一页URL
                if current_page_param and next_page_value:
                    # 特殊处理路径形式的分页
                    if current_page_param == '/page/':
                        next_url = re.sub(
                            f'/page/\\d+',
                            f'/page/{next_page_value}',
                            page_url
                        )
                    else:
                        # 替换URL中的分页参数
                        next_url = re.sub(
                            f'[?&]{current_page_param}=\\d+',
                            f'{current_page_param}={next_page_value}',
                            page_url
                        )
                    
                    if next_url != page_url:
                        has_next_page = True
                        logger.info(f"站点 {site_name} 通过参数递增发现下一页: {next_url}")
                
                # 检查页面文本中的分页信息
                elif page_num == 1:
                    # 查找形如"1-10 of 25"或"1-10 共25"的文本
                    page_info_patterns = [
                        r'(\d+)\s*-\s*(\d+).*?of\s*(\d+)',
                        r'(\d+)\s*-\s*(\d+).*?共\s*(\d+)',
                        r'显示第\s*(\d+)\s*到第\s*(\d+)\s*条记录，共\s*(\d+)\s*条',
                        r'(\d+)\s*results\s*found.*?page\s*(\d+)\s*of\s*(\d+)'
                    ]
                    
                    page_text = soup.get_text()
                    for pattern in page_info_patterns:
                        page_info = re.search(pattern, page_text)
                        if page_info:
                            total_pages = int(page_info.group(3))
                            if page_num < total_pages:
                                # 有下一页，尝试不同的分页参数
                                for param in ['page', 'p', 'pg', 'pagenum']:
                                    if '?' in page_url:
                                        test_url = f"{page_url}&{param}=2"
                                    else:
                                        test_url = f"{page_url}?{param}=2"
                                        
                                    next_url = test_url
                                    has_next_page = True
                                    logger.info(f"站点 {site_name} 根据分页信息推断下一页: {next_url}")
                                    break
                            break
            
            # 如果找到下一页，递归获取
            if has_next_page and next_url and next_url != page_url:
                logger.info(f"站点 {site_name} 发现下一页: {next_url}")
                self._fetch_all_invite_pages(site_name, site_url, next_url, session, result, page_num + 1, max_pages)
            else:
                logger.info(f"站点 {site_name} 没有更多页面，总共获取了 {len(result.get('invitees', []))} 个后宫成员")
        
        except Exception as e:
            logger.error(f"站点 {site_name} 获取第 {page_num} 页数据失败: {str(e)}")
            logger.exception(e)
    
    def _parse_butterfly_invite_page(self, site_name: str, content: str) -> Dict[str, Any]:
        """
        解析蝶粉站点邀请页面内容
        :param site_name: 站点名称
        :param content: 页面内容
        :return: 解析结果
        """
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
            soup = BeautifulSoup(content, 'html.parser')
            
            # 解析邀请状态
            invite_info_table = None
            
            # 检查可能包含邀请信息的表格
            tables = soup.select("table.main")
            for table in tables:
                # 检查表格是否包含邀请相关信息
                if any(keyword in table.get_text().lower() for keyword in ["邀请", "邀請", "invite"]):
                    invite_info_table = table
                    break
            
            if invite_info_table:
                invite_text = invite_info_table.get_text()
                
                # 解析永久邀请数量
                permanent_match = re.search(r'(\d+)\s*个永久邀请', invite_text)
                if permanent_match:
                    result["invite_status"]["permanent_count"] = int(permanent_match.group(1))
                
                # 解析临时邀请数量
                temporary_match = re.search(r'(\d+)\s*个临时邀请', invite_text)
                if temporary_match:
                    result["invite_status"]["temporary_count"] = int(temporary_match.group(1))
                
                # 检查是否可以邀请
                if result["invite_status"]["permanent_count"] > 0 or result["invite_status"]["temporary_count"] > 0:
                    result["invite_status"]["can_invite"] = True
                else:
                    result["invite_status"]["can_invite"] = False
                    result["invite_status"]["reason"] = "没有可用的邀请名额"
            else:
                result["invite_status"]["reason"] = "无法找到邀请信息表格"
            
            # 解析邀请者列表
            invitee_table = None
            
            # 查找包含后宫数据的表格
            tables = soup.select("table.main, table.mainouter")
            for table in tables:
                # 检查表格是否包含后宫成员数据
                table_text = table.get_text().lower()
                if any(keyword in table_text for keyword in ["用户名", "username", "user"]) and \
                   any(keyword in table_text for keyword in ["邮箱", "email", "mail"]):
                    invitee_table = table
                    break
            
            if invitee_table:
                # 提取表头
                headers = []
                header_row = invitee_table.select_one("tr")
                if header_row:
                    for th in header_row.select("th"):
                        headers.append(th.get_text().strip().lower())
                
                # 如果没有找到表头，尝试从第一行获取
                if not headers:
                    first_row = invitee_table.select_one("tr")
                    if first_row:
                        for td in first_row.select("td"):
                            headers.append(td.get_text().strip().lower())
                
                # 映射列索引到字段名
                index_map = {}
                for i, header in enumerate(headers):
                    if any(name in header for name in ["用户名", "username", "user"]):
                        index_map["username"] = i
                    elif any(name in header for name in ["邮箱", "email", "mail"]):
                        index_map["email"] = i
                    elif any(name in header for name in ["上传", "上傳", "uploaded", "upload"]):
                        index_map["uploaded"] = i
                    elif any(name in header for name in ["下载", "下載", "downloaded", "download"]):
                        index_map["downloaded"] = i
                    elif any(name in header for name in ["分享率", "ratio", "share"]):
                        index_map["ratio"] = i
                    elif any(name in header for name in ["做种数", "seed", "seeding"]):
                        index_map["seeding"] = i
                    elif any(name in header for name in ["做种体积", "seed size", "total size"]):
                        index_map["seed_size"] = i
                    elif any(name in header for name in ["做种时间", "seed time", "time"]):
                        index_map["seed_time"] = i
                    elif any(name in header for name in ["加成", "加成率", "bonus", "harem"]):
                        index_map["bonus"] = i
                    elif any(name in header for name in ["最后做种", "最后", "last seed", "last"]):
                        index_map["last_seen"] = i
                    elif any(name in header for name in ["状态", "status"]):
                        index_map["status"] = i
                
                # 解析表格数据行
                rows = invitee_table.select("tr")[1:]  # 跳过表头行
                for row in rows:
                    cells = row.select("td")
                    if len(cells) >= 3:  # 至少有用户名、邮箱和一些状态信息
                        invitee = {}
                        
                        # 提取各个字段
                        for field, idx in index_map.items():
                            if idx < len(cells):
                                if field == "username":
                                    # 特殊处理用户名，提取链接和颜色
                                    username_cell = cells[idx]
                                    username_link = username_cell.select_one("a")
                                    if username_link:
                                        invitee["username"] = username_link.get_text().strip()
                                        # 获取用户ID
                                        href = username_link.get("href", "")
                                        user_id_match = re.search(r"id=(\d+)", href)
                                        if user_id_match:
                                            invitee["user_id"] = user_id_match.group(1)
                                        # 获取用户级别颜色
                                        style = username_link.get("style", "")
                                        color_match = re.search(r"color:\s*([^;]+)", style)
                                        if color_match:
                                            invitee["user_color"] = color_match.group(1)
                                        else:
                                            # 尝试从class获取颜色
                                            class_name = username_link.get("class", [])
                                            if class_name and any(c in class_name for c in ["user1", "user2", "user3", "user4", "user5"]):
                                                invitee["user_class"] = class_name[0]
                                    else:
                                        invitee["username"] = username_cell.get_text().strip()
                                else:
                                    # 处理其他字段
                                    invitee[field] = cells[idx].get_text().strip()
                        
                        # 如果成功获取了用户名和邮箱，添加到列表
                        if "username" in invitee and "email" in invitee:
                            # 计算分享率数字
                            if "ratio" in invitee:
                                ratio_text = invitee["ratio"]
                                try:
                                    if ratio_text.lower() == "inf" or ratio_text == "∞":
                                        invitee["ratio_value"] = float('inf')
                                    else:
                                        ratio_match = re.search(r"(\d+\.?\d*)", ratio_text)
                                        if ratio_match:
                                            invitee["ratio_value"] = float(ratio_match.group(1))
                                except:
                                    invitee["ratio_value"] = 0
                            
                            # 确定状态
                            if "status" in invitee:
                                status_text = invitee["status"].lower()
                                if any(s in status_text for s in ["banned", "封禁", "禁用"]):
                                    invitee["status_text"] = "已封禁"
                                    invitee["is_banned"] = True
                                elif any(s in status_text for s in ["pending", "待审", "等待"]):
                                    invitee["status_text"] = "待审核"
                                else:
                                    invitee["status_text"] = "正常"
                                    invitee["is_banned"] = False
                            
                            result["invitees"].append(invitee)
            
            logger.info(f"站点 {site_name} 解析到 {len(result['invitees'])} 个后宫成员")
            return result
        except Exception as e:
            logger.error(f"解析站点 {site_name} 邀请页面内容失败: {str(e)}")
            logger.exception(e)
            result["invite_status"]["reason"] = f"解析邀请页面内容失败: {str(e)}"
            return result

    def set_ua(self, ua: str):
        """
        设置User-Agent
        :param ua: User-Agent
        """
        self.user_agent = ua

    def get_invite_page_content(self, site_name: str, site_url: str, session: requests.Session) -> str:
        """
        获取邀请页面内容
        :param site_name: 站点名称
        :param site_url: 站点URL
        :param session: 会话
        :return: 页面内容
        """
        try:
            # 获取用户ID
            user_id = self._get_user_id(session, site_url)
            if not user_id:
                logger.error(f"站点 {site_name} 无法获取用户ID")
                return ""
            
            # 获取邀请页面
            invite_url = urljoin(site_url, f"invite.php?id={user_id}")
            logger.info(f"站点 {site_name} 获取邀请页面: {invite_url}")
            
            response = session.get(invite_url, timeout=(10, 30))
            response.raise_for_status()
            
            return response.text
        except Exception as e:
            logger.error(f"站点 {site_name} 获取邀请页面内容失败: {str(e)}")
            logger.exception(e)
            return "" 