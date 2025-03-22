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
    
    def parse_invite_page(self, site_info: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
        """
        解析蝶粉站点邀请页面
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
            return self._parse_butterfly_invite_page(site_name, site_url, response.text)
            
        except Exception as e:
            logger.error(f"解析站点 {site_name} 邀请页面失败: {str(e)}")
            result["invite_status"]["reason"] = f"解析邀请页面失败: {str(e)}"
            return result
    
    def _parse_butterfly_invite_page(self, site_name: str, site_url: str, html_content: str) -> Dict[str, Any]:
        """
        解析蝶粉站点邀请页面HTML内容
        :param site_name: 站点名称
        :param site_url: 站点URL
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
        
        # 蝶粉站点特殊处理
        # 直接查找border="1"的表格，这通常是用户列表表格
        border_tables = soup.select('table[border="1"]')
        if border_tables:
            # 选取第一个border="1"表格
            table = border_tables[0]
            
            # 获取表头
            header_row = table.select_one('tr')
            if header_row:
                # 获取所有表头单元格
                header_cells = header_row.select('td.colhead, th.colhead, td, th')
                headers = [cell.get_text(strip=True).lower() for cell in header_cells]
                
                logger.info(f"站点 {site_name} 找到用户表格，表头: {headers}")
                
                # 找到所有数据行（跳过表头行）
                data_rows = table.select('tr.rowfollow')
                
                # 清空已有数据，避免重复
                result["invitees"] = []
                processed_usernames = set()  # 用于跟踪已处理的用户名，避免重复
                
                for row in data_rows:
                    cells = row.select('td')
                    if len(cells) < len(headers):
                        continue
                    
                    invitee = {}
                    username = ""
                    is_banned = False
                    
                    # 检查行类和禁用标记
                    row_classes = row.get('class', [])
                    if isinstance(row_classes, list) and any(cls in ['rowbanned', 'banned'] for cls in row_classes):
                        is_banned = True
                    
                    # 逐列解析数据
                    for idx, header in enumerate(headers):
                        if idx >= len(cells):
                            break
                        
                        cell = cells[idx]
                        cell_text = cell.get_text(strip=True)
                        
                        # 用户名列（通常是第一列）
                        if idx == 0 or any(kw in header for kw in ['用户名', '用戶名', 'username', 'user']):
                            username_link = cell.select_one('a')
                            disabled_img = cell.select_one('img.disabled, img[alt="Disabled"]')
                            
                            if disabled_img:
                                is_banned = True
                            
                            if username_link:
                                username = username_link.get_text(strip=True)
                                invitee["username"] = username
                                
                                # 处理可能在用户名中附带的Disabled文本
                                if "Disabled" in cell.get_text():
                                    is_banned = True
                                
                                # 获取用户个人页链接
                                href = username_link.get('href', '')
                                invitee["profile_url"] = urljoin(site_url, href) if href else ""
                            else:
                                username = cell_text
                                invitee["username"] = username
                        
                        # 邮箱列
                        elif any(kw in header for kw in ['郵箱', '邮箱', 'email', 'mail']):
                            invitee["email"] = cell_text
                        
                        # 启用状态列
                        elif any(kw in header for kw in ['啟用', '启用', 'enabled']):
                            status_text = cell_text.lower()
                            if status_text == 'no' or '禁' in status_text:
                                invitee["enabled"] = "No"
                                is_banned = True
                            else:
                                invitee["enabled"] = "Yes"
                        
                        # 上传量列
                        elif any(kw in header for kw in ['上傳', '上传', 'uploaded', 'upload']):
                            invitee["uploaded"] = cell_text
                        
                        # 下载量列
                        elif any(kw in header for kw in ['下載', '下载', 'downloaded', 'download']):
                            invitee["downloaded"] = cell_text
                        
                        # 分享率列 - 特别处理∞、Inf.等情况
                        elif any(kw in header for kw in ['分享率', '分享比率', 'ratio']):
                            ratio_text = cell_text
                            
                            # 处理特殊分享率表示
                            if ratio_text.lower() in ['inf.', 'inf', '∞', 'infinite', '无限']:
                                invitee["ratio"] = "∞"
                                invitee["ratio_value"] = 1e20
                            elif ratio_text == '---' or not ratio_text:
                                invitee["ratio"] = "0"
                                invitee["ratio_value"] = 0
                            else:
                                # 获取font标签内的文本，如果存在
                                font_tag = cell.select_one('font')
                                if font_tag:
                                    ratio_text = font_tag.get_text(strip=True)
                                
                                invitee["ratio"] = ratio_text
                                
                                # 尝试解析为浮点数
                                try:
                                    # 替换逗号为点
                                    normalized_ratio = ratio_text.replace(',', '.')
                                    invitee["ratio_value"] = float(normalized_ratio)
                                except (ValueError, TypeError):
                                    logger.warning(f"无法解析分享率: {ratio_text}")
                                    invitee["ratio_value"] = 0
                        
                        # 做种数列
                        elif any(kw in header for kw in ['做種數', '做种数', 'seeding', 'seeds']):
                            invitee["seeding"] = cell_text
                        
                        # 做种体积列
                        elif any(kw in header for kw in ['做種體積', '做种体积', 'seeding size', 'seed size']):
                            invitee["seeding_size"] = cell_text
                        
                        # 当前纯做种时魔列
                        elif any(kw in header for kw in ['純做種時魔', '当前纯做种时魔', '纯做种时魔', 'seed magic']):
                            invitee["seed_magic"] = cell_text
                        
                        # 后宫加成列
                        elif any(kw in header for kw in ['後宮加成', '后宫加成', 'bonus']):
                            invitee["seed_bonus"] = cell_text
                        
                        # 最后做种汇报时间列
                        elif any(kw in header for kw in ['最後做種匯報時間', '最后做种汇报时间', '最后做种报告', 'last seed']):
                            invitee["last_seed_report"] = cell_text
                        
                        # 状态列
                        elif any(kw in header for kw in ['狀態', '状态', 'status']):
                            invitee["status"] = cell_text
                            
                            # 根据状态判断是否禁用
                            status_lower = cell_text.lower()
                            if any(ban_word in status_lower for ban_word in ['banned', 'disabled', '禁止', '禁用', '封禁']):
                                is_banned = True
                    
                    # 如果用户名不为空且未处理过
                    if username and username not in processed_usernames:
                        processed_usernames.add(username)
                        
                        # 设置启用状态（如果尚未设置）
                        if "enabled" not in invitee:
                            invitee["enabled"] = "No" if is_banned else "Yes"
                        
                        # 设置状态（如果尚未设置）
                        if "status" not in invitee:
                            invitee["status"] = "已禁用" if is_banned else "已確認"
                        
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
                        
                        # 将用户数据添加到结果中
                        if invitee.get("username"):
                            result["invitees"].append(invitee.copy())
                
                # 记录解析结果
                if result["invitees"]:
                    logger.info(f"站点 {site_name} 从特殊格式表格解析到 {len(result['invitees'])} 个后宫成员")
        
        # 检查邀请权限
        form_disabled = soup.select_one('input[disabled][value*="貴賓 或以上等級才可以"]')
        if form_disabled:
            disabled_text = form_disabled.get('value', '')
            result["invite_status"]["can_invite"] = False
            result["invite_status"]["reason"] = disabled_text
            logger.info(f"站点 {site_name} 邀请按钮被禁用: {disabled_text}")

        return result 