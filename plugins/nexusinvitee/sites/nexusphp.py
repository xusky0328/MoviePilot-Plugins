"""
标准NexusPHP站点处理
"""
import re
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.log import logger
from plugins.nexusinvitee.sites import _ISiteHandler


class NexusPhpHandler(_ISiteHandler):
    """
    标准NexusPHP站点处理类
    """
    # 站点类型标识
    site_schema = "nexusphp"
    
    @classmethod
    def match(cls, site_url: str) -> bool:
        """
        判断是否匹配NexusPHP站点
        :param site_url: 站点URL
        :return: 是否匹配
        """
        # 排除已知的特殊站点
        special_sites = ["m-team", "totheglory", "hdchina", "butterfly", "dmhy", "蝶粉"]
        if any(site in site_url.lower() for site in special_sites):
            return False
            
        # 标准NexusPHP站点的URL特征
        nexus_features = [
            "php",                  # 大多数NexusPHP站点URL包含php
            "nexus",                # 部分站点URL中包含nexus
            "agsvpt",               # 红豆饭

            "audiences",            # 观众
            "hdpt",                 # HD盘他
            "wintersakura",         # 冬樱

            "hdmayi",               # 蚂蚁
            "u2.dmhy",              # U2
            "hddolby",              # 杜比
            "hdarea",               # 高清地带
            "pt.soulvoice",         # 聆音

            "ptsbao",               # PT书包
            "hdhome",               # HD家园
            "hdatmos",              # 阿童木
            "1ptba",                # 1PT
            "keepfrds",             # 朋友
            "moecat",               # 萌猫
            "springsunday"          # 春天
        ]
        
        # 如果URL中包含任何一个NexusPHP特征，则认为是NexusPHP站点
        site_url_lower = site_url.lower()
        for feature in nexus_features:
            if feature in site_url_lower:
                logger.info(f"匹配到NexusPHP站点特征: {feature}")
                return True
                
        # 如果没有匹配到特征，但URL中包含PHP，也视为可能的NexusPHP站点
        if "php" in site_url_lower:
            logger.info(f"URL中包含PHP，可能是NexusPHP站点: {site_url}")
            return True
            
        return False
    
    def parse_invite_page(self, site_info: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
        """
        解析NexusPHP站点邀请页面
        :param site_info: 站点信息
        :param session: 已配置好的请求会话
        :return: 解析结果
        """
        site_name = site_info.get("name", "")
        site_url = site_info.get("url", "")
        
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
            # 获取用户ID
            user_id = self._get_user_id(session, site_url)
            if not user_id:
                logger.error(f"站点 {site_name} 无法获取用户ID")
                result["invite_status"]["reason"] = "无法获取用户ID，请检查站点Cookie是否有效"
                return result
            
            # 获取邀请页面
            invite_url = urljoin(site_url, f"invite.php?id={user_id}")
            response = session.get(invite_url, timeout=(10, 30))
            response.raise_for_status()
            
            # 解析邀请页面
            invite_result = self._parse_nexusphp_invite_page(site_name, response.text)
            
            # 访问发送邀请页面，这是判断权限的关键
            send_invite_url = urljoin(site_url, f"invite.php?id={user_id}&type=new")
            try:
                send_response = session.get(send_invite_url, timeout=(10, 30))
                send_response.raise_for_status()
                
                # 解析发送邀请页面
                send_soup = BeautifulSoup(send_response.text, 'html.parser')
                
                # 检查是否有takeinvite.php表单 - 最直接的权限判断
                invite_form = send_soup.select('form[action*="takeinvite.php"]')
                if invite_form:
                    # 确认有表单，权限正常
                    invite_result["invite_status"]["can_invite"] = True
                    invite_result["invite_status"]["reason"] = "可以发送邀请"
                    logger.info(f"站点 {site_name} 可以发送邀请，确认有takeinvite表单")
                else:
                    # 没有表单，检查是否有错误消息
                    sorry_text = send_soup.find(text=re.compile(r'对不起|sorry'))
                    if sorry_text:
                        parent_element = None
                        for parent in sorry_text.parents:
                            if parent.name in ['td', 'div', 'p', 'h2']:
                                parent_element = parent
                                break
                        
                        if parent_element:
                            # 获取整个限制文本
                            restriction_text = ""
                            for parent in parent_element.parents:
                                if parent.name in ['table']:
                                    restriction_text = parent.get_text().strip()
                                    break
                            
                            if not restriction_text:
                                restriction_text = parent_element.get_text().strip()
                            
                            invite_result["invite_status"]["can_invite"] = False
                            invite_result["invite_status"]["reason"] = restriction_text
                            logger.info(f"站点 {site_name} 有邀请限制: {restriction_text}")
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"访问站点发送邀请页面失败，使用默认权限判断: {str(e)}")
            
            return invite_result
            
        except Exception as e:
            logger.error(f"解析站点 {site_name} 邀请页面失败: {str(e)}")
            result["invite_status"]["reason"] = f"解析邀请页面失败: {str(e)}"
            return result
    
    def _parse_nexusphp_invite_page(self, site_name: str, html_content: str) -> Dict[str, Any]:
        """
        解析NexusPHP邀请页面HTML内容
        :param site_name: 站点名称
        :param html_content: HTML内容
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
        
        # 初始化BeautifulSoup对象
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 检查是否有特殊标题，如"我的后宫"或"邀請系統"等
        special_title = False
        title_elem = soup.select_one('h1')
        if title_elem:
            title_text = title_elem.get_text().strip()
            if '后宫' in title_text or '後宮' in title_text or '邀請系統' in title_text or '邀请系统' in title_text:
                logger.info(f"站点 {site_name} 检测到特殊标题: {title_text}")
                special_title = True
        
        # 先检查info_block中的邀请信息
        info_block = soup.select_one('#info_block')
        if info_block:
            info_text = info_block.get_text()
            logger.info(f"站点 {site_name} 获取到info_block信息")
            
            # 识别邀请数量 - 查找邀请链接并获取数量
            invite_link = info_block.select_one('a[href*="invite.php"]')
            if invite_link:
                # 获取invite链接周围的文本
                parent_text = invite_link.parent.get_text() if invite_link.parent else ""
                
                # 尝试匹配常见格式: 数字(数字) 或 单个数字
                invite_pattern = re.compile(r'(?:邀请|探视权|invite).*?:?\s*(\d+)(?:\s*\((\d+)\))?', re.IGNORECASE)
                invite_match = invite_pattern.search(parent_text)
                
                if invite_match:
                    # 获取永久邀请数量
                    if invite_match.group(1):
                        result["invite_status"]["permanent_count"] = int(invite_match.group(1))
                    
                    # 如果有临时邀请数量
                    if len(invite_match.groups()) > 1 and invite_match.group(2):
                        result["invite_status"]["temporary_count"] = int(invite_match.group(2))
                    
                    logger.info(f"站点 {site_name} 解析到邀请数量: 永久={result['invite_status']['permanent_count']}, 临时={result['invite_status']['temporary_count']}")
                    
                    # 如果有邀请名额，初步判断为可邀请
                    if result["invite_status"]["permanent_count"] > 0 or result["invite_status"]["temporary_count"] > 0:
                        result["invite_status"]["can_invite"] = True
                        result["invite_status"]["reason"] = f"可用邀请数: 永久={result['invite_status']['permanent_count']}, 临时={result['invite_status']['temporary_count']}"
                else:
                    # 尝试在邀请链接后面的文本中查找数字
                    after_text = ""
                    next_sibling = invite_link.next_sibling
                    while next_sibling and not after_text.strip():
                        if isinstance(next_sibling, str):
                            after_text = next_sibling
                        next_sibling = next_sibling.next_sibling if hasattr(next_sibling, 'next_sibling') else None
                    
                    if after_text:
                        nums = re.findall(r'\d+', after_text)
                        if nums and len(nums) >= 1:
                            result["invite_status"]["permanent_count"] = int(nums[0])
                            if len(nums) >= 2:
                                result["invite_status"]["temporary_count"] = int(nums[1])
                            
                            logger.info(f"站点 {site_name} 从后续文本解析到邀请数量: 永久={result['invite_status']['permanent_count']}, 临时={result['invite_status']['temporary_count']}")
                            
                            # 如果有邀请名额，初步判断为可邀请
                            if result["invite_status"]["permanent_count"] > 0 or result["invite_status"]["temporary_count"] > 0:
                                result["invite_status"]["can_invite"] = True
                                result["invite_status"]["reason"] = f"可用邀请数: 永久={result['invite_status']['permanent_count']}, 临时={result['invite_status']['temporary_count']}"
        
        # 检查是否有标准的NexusPHP邀请页面结构
        invite_tables = soup.select('table.main > tbody > tr > td > table')
        
        # 如果页面没有invite_tables可能是未登录或者错误页面
        if not invite_tables:
            # 检查是否有其他表格
            any_tables = soup.select('table')
            if not any_tables:
                result["invite_status"]["reason"] = "页面解析错误，可能未登录或者站点结构特殊"
                logger.error(f"站点 {site_name} 邀请页面解析失败：没有找到任何表格")
                return result
            else:
                # 使用任意表格继续尝试
                invite_tables = any_tables
        
        # 检查是否存在"没有邀请权限"或"当前没有可用邀请名额"等提示
        error_patterns = [
            r"没有邀请权限",
            r"不能使用邀请",
            r"当前没有可用邀请名额",
            r"低于要求的等级",
            r"需要更高的用户等级",
            r"无法进行邀请注册",
            r"当前账户上限数已到",
            r"抱歉，目前没有开放注册",
            r"当前邀请注册人数已达上限",
            r"对不起",
            r"只有.*等级才能发送邀请",
            r"及以上.*才能发送邀请",
            r"\w+\s*or above can send invites"
        ]
        
        # 解析邀请权限状态
        page_text = soup.get_text()
        
        # 查找是否有邀请限制文本
        has_restriction = False
        restriction_reason = ""
        
        for pattern in error_patterns:
            matches = re.search(pattern, page_text, re.IGNORECASE)
            if matches:
                has_restriction = True
                restriction_reason = matches.group(0)
                result["invite_status"]["can_invite"] = False
                result["invite_status"]["reason"] = f"无法发送邀请: {restriction_reason}"
                logger.info(f"站点 {site_name} 发现邀请限制: {restriction_reason}")
                break
        
        # 检查是否存在发送邀请表单，这是最直接的判断依据
        invite_form = soup.select('form[action*="takeinvite.php"]')
        if invite_form:
            if not has_restriction:
                result["invite_status"]["can_invite"] = True
                if not result["invite_status"]["reason"]:
                    result["invite_status"]["reason"] = "存在邀请表单，可以发送邀请"
                logger.info(f"站点 {site_name} 存在邀请表单，可以发送邀请")
        
        # 优先查找带有border属性的表格，这通常是用户列表表格
        invitee_tables = soup.select('table[border="1"]')
        
        # 如果没找到，再尝试标准表格结构
        if not invitee_tables:
            invitee_tables = soup.select('table.main table.torrents')
            
            # 如果还没找到，尝试查找任何可能包含用户数据的表格
            if not invitee_tables:
                all_tables = soup.select('table')
                # 过滤掉小表格
                invitee_tables = [table for table in all_tables 
                                 if len(table.select('tr')) > 2]
        
        # 处理找到的表格
        for table in invitee_tables:
            # 获取表头
            header_row = table.select_one('tr')
            if not header_row:
                continue
                
            headers = []
            header_cells = header_row.select('td.colhead, th.colhead, td, th')
            for cell in header_cells:
                headers.append(cell.get_text(strip=True))
                
            # 检查是否是用户表格 - 查找关键列头
            if not any(keyword in ' '.join(headers).lower() for keyword in 
                      ['用户名', '邮箱', 'email', '分享率', 'ratio', 'username']):
                continue
                
            logger.info(f"站点 {site_name} 找到后宫用户表，表头: {headers}")
            
            # 解析表格行
            rows = table.select('tr:not(:first-child)')
            for row in rows:
                cells = row.select('td')
                if not cells or len(cells) < 3:  # 至少需要3列才可能是有效数据
                    continue
                    
                invitee = {}
                
                # 检查行类和禁用标记
                row_classes = row.get('class', [])
                is_banned = any(cls in ['rowbanned', 'banned', 'disabled'] 
                               for cls in row_classes)
                
                # 查找禁用图标
                disabled_img = row.select_one('img.disabled, img[alt="Disabled"]')
                if disabled_img:
                    is_banned = True
                
                # 解析各列数据
                for idx, cell in enumerate(cells):
                    if idx >= len(headers):
                        break
                        
                    header = headers[idx].lower()
                    cell_text = cell.get_text(strip=True)
                    
                    # 用户名和链接
                    if any(keyword in header for keyword in ['用户名', 'username', '名字', 'user']):
                        username_link = cell.select_one('a')
                        if username_link:
                            invitee["username"] = username_link.get_text(strip=True)
                            href = username_link.get('href', '')
                            invitee["profile_url"] = urljoin(soup.url if hasattr(soup, 'url') else "", href) if href else ""
                        else:
                            invitee["username"] = cell_text
                    
                    # 邮箱
                    elif any(keyword in header for keyword in ['邮箱', 'email', '电子邮件', 'mail']):
                        invitee["email"] = cell_text
                    
                    # 启用状态 - 直接检查yes/no
                    elif any(keyword in header for keyword in ['启用', '狀態', 'enabled', 'status']):
                        status_text = cell_text.lower()
                        if status_text == 'no' or '禁' in status_text or 'disabled' in status_text or 'banned' in status_text:
                            invitee["enabled"] = "No"
                            is_banned = True
                        else:
                            invitee["enabled"] = "Yes"
                    
                    # 上传量
                    elif any(keyword in header for keyword in ['上传', '上傳', 'uploaded', 'upload']):
                        invitee["uploaded"] = cell_text
                    
                    # 下载量
                    elif any(keyword in header for keyword in ['下载', '下載', 'downloaded', 'download']):
                        invitee["downloaded"] = cell_text
                    
                    # 分享率 - 特别处理∞、Inf.等情况
                    elif any(keyword in header for keyword in ['分享率', '分享', 'ratio']):
                        # 标准化分享率表示
                        ratio_text = cell_text
                        if ratio_text == '---' or not ratio_text:
                            ratio_text = '0'
                        elif ratio_text.lower() in ['inf.', 'inf', '无限']:
                            ratio_text = '∞'
                            
                        invitee["ratio"] = ratio_text
                        
                        # 计算分享率数值
                        try:
                            if ratio_text == '∞':
                                invitee["ratio_value"] = 1e20
                            else:
                                # 替换逗号为点
                                normalized_ratio = ratio_text.replace(',', '.')
                                invitee["ratio_value"] = float(normalized_ratio)
                        except (ValueError, TypeError):
                            invitee["ratio_value"] = 0
                            logger.warning(f"无法解析分享率: {ratio_text}")
                    
                    # 做种数
                    elif any(keyword in header for keyword in ['做种数', '做種數', 'seeding', 'seed']):
                        invitee["seeding"] = cell_text
                    
                    # 做种体积
                    elif any(keyword in header for keyword in ['做种体积', '做種體積', 'seeding size']):
                        invitee["seeding_size"] = cell_text
                    
                    # 做种时间/魔力值
                    elif any(keyword in header for keyword in ['做种时间', '做種時間', 'seed time']):
                        invitee["seed_time"] = cell_text
                    
                    # 做种时魔/当前纯做种时魔 - 这是我们需要特别解析的字段
                    elif any(keyword in header for keyword in ['做种时魔', '纯做种时魔', '当前纯做种时魔', '做种积分', 'seed bonus', 'seed magic']):
                        invitee["seed_magic"] = cell_text
                    
                    # 后宫加成 - 新增字段
                    elif any(keyword in header for keyword in ['后宫加成', '後宮加成', 'invitee bonus', 'bonus']):
                        # 统一字段名为seed_bonus，与butterfly处理器保持一致
                        invitee["seed_bonus"] = cell_text
                    
                    # 最后做种汇报时间/最后做种报告 - 新增字段
                    elif any(keyword in header for keyword in ['最后做种汇报', '最后做种报告', '最后做种', '最後做種報告', 'last seed report']):
                        invitee["last_seed_report"] = cell_text
                    
                    # 做种魔力/积分/加成
                    elif any(keyword in header for keyword in ['魔力', 'magic', '积分', 'bonus', '加成', 'leeched']):
                        header_lower = header.lower()
                        if '魔力' in header_lower or 'magic' in header_lower:
                            invitee["magic"] = cell_text
                        elif '加成' in header_lower or 'bonus' in header_lower:
                            invitee["bonus"] = cell_text
                        elif '积分' in header_lower or 'credit' in header_lower:
                            invitee["credit"] = cell_text
                        elif 'leeched' in header_lower:
                            invitee["leeched"] = cell_text
                    
                    # 其他字段处理...
                
                # 如果尚未设置enabled状态，根据行类或图标判断
                if "enabled" not in invitee:
                    invitee["enabled"] = "No" if is_banned else "Yes"
                
                # 设置状态字段(如果尚未设置)
                if "status" not in invitee:
                    invitee["status"] = "已禁用" if is_banned else "已确认"
                
                # 计算分享率健康状态
                if "ratio_value" in invitee:
                    if invitee["ratio_value"] >= 1e20:
                        invitee["ratio_health"] = "excellent"
                    elif invitee["ratio_value"] >= 1.0:
                        invitee["ratio_health"] = "good"
                    elif invitee["ratio_value"] >= 0.5:
                        invitee["ratio_health"] = "warning"
                    else:
                        invitee["ratio_health"] = "danger"
                
                # 设置分享率标签
                if invitee["ratio_value"] < 0:
                    invitee["ratio_label"] = ["危险", "red"]
                elif invitee["ratio_value"] < 1.0:
                    invitee["ratio_label"] = ["较低", "orange"]
                elif invitee["ratio_value"] >= 1.0:
                    invitee["ratio_label"] = ["良好", "green"]
                
                # 将解析到的用户添加到列表中
                if invitee.get("username"):
                    result["invitees"].append(invitee)
            
            # 如果已找到用户数据，跳出循环
            if result["invitees"]:
                logger.info(f"站点 {site_name} 已解析 {len(result['invitees'])} 个后宫成员")
                break
        
        return result 