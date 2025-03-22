"""
M-Team站点处理模块
"""
import json
import re
from typing import Dict, Any

import requests
from urllib.parse import urljoin

from app.log import logger
from plugins.nexusinvitee.sites import _ISiteHandler
from plugins.nexusinvitee.utils import SiteHelper


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
        return "m-team" in site_url.lower()
    
    def parse_invite_page(self, site_info: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
        """
        解析M-Team邀请页面
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
            "invitees": [],
            "sent_invites": []
        }
        
        try:
            # 获取API认证信息
            api_key = site_info.get("api_key")
            auth_header = site_info.get("authorization")
            
            if not api_key or not auth_header:
                logger.error(f"站点 {site_name} API认证信息不完整")
                result["invite_status"]["reason"] = "API认证信息不完整，请在站点设置中配置API Key和Authorization"
                return result
            
            # 更新请求头
            session.headers.update({
                'Authorization': auth_header,
                'API-Key': api_key
            })
            
            # 获取站点统计数据
            domain = site_url.split("//")[-1].split("/")[0]
            api_url = f"https://{domain}/api/v1/site/statistic/{domain}"
            
            try:
                stats_response = session.get(api_url, timeout=(10, 30))
                stats_response.raise_for_status()
                stats_data = stats_response.json()
                
                # 获取邀请页面数据
                invite_url = urljoin(site_url, "invite")
                invite_response = session.get(invite_url, timeout=(10, 30))
                invite_response.raise_for_status()
                
                # 解析邀请页面
                return self._parse_mteam_invite_page(invite_response.text, stats_data)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"访问M-Team API失败: {str(e)}")
                result["invite_status"]["reason"] = f"访问站点API失败: {str(e)}"
                return result
                
        except Exception as e:
            logger.error(f"解析站点 {site_name} 邀请页面失败: {str(e)}")
            result["invite_status"]["reason"] = f"解析邀请页面失败: {str(e)}"
            return result
    
    def _parse_mteam_invite_page(self, html_content: str, stats_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        解析M-Team邀请页面
        :param html_content: HTML内容
        :param stats_data: 统计数据
        :return: 解析结果
        """
        result = {
            "invitees": [],
            "sent_invites": [],
            "temp_invites": [],
            "invite_status": {
                "can_invite": False,
                "permanent_count": 0,
                "temporary_count": 0,
                "reason": "",
                "stats": stats_data or {}
            }
        }
        
        try:
            # 尝试从页面中提取JSON数据
            json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html_content)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    
                    # 解析邀请名额
                    if "inviteQuota" in data:
                        result["invite_status"].update({
                            "permanent_count": data["inviteQuota"].get("permanent", 0),
                            "temporary_count": data["inviteQuota"].get("temporary", 0),
                            "can_invite": data["inviteQuota"].get("permanent", 0) > 0 or 
                                         data["inviteQuota"].get("temporary", 0) > 0
                        })
                        
                        # 设置可邀请理由
                        if result["invite_status"]["can_invite"]:
                            result["invite_status"]["reason"] = f"可用邀请数: 永久={result['invite_status']['permanent_count']}, 临时={result['invite_status']['temporary_count']}"
                        else:
                            result["invite_status"]["reason"] = "没有可用邀请名额"
                    
                    # 解析被邀请人列表
                    if "invitees" in data:
                        for invitee in data["invitees"]:
                            upload_bytes = invitee.get("uploaded", 0)
                            download_bytes = invitee.get("downloaded", 0)
                            
                            # 计算分享率
                            ratio = 0
                            if download_bytes > 0:
                                ratio = upload_bytes / download_bytes
                            elif upload_bytes > 0:
                                ratio = float('inf')  # 无限大
                            
                            # 格式化大小
                            uploaded = SiteHelper.format_size(upload_bytes)
                            downloaded = SiteHelper.format_size(download_bytes)
                            
                            # 计算分享率健康状态
                            ratio_health = "danger"
                            if ratio == float('inf'):
                                ratio_value = 1e20
                                ratio_health = "excellent"
                            else:
                                ratio_value = ratio
                                if ratio >= 1.0:
                                    ratio_health = "good"
                                elif ratio >= 0.5:
                                    ratio_health = "warning"
                            
                            # 格式化分享率
                            ratio_str = "∞" if ratio == float('inf') else f"{ratio:.3f}"
                            
                            # 状态判断
                            status = invitee.get("status", "")
                            enabled = "Yes" if status.lower() != "banned" else "No"
                            
                            result["invitees"].append({
                                "username": invitee.get("username", ""),
                                "email": invitee.get("email", ""),
                                "uploaded": uploaded,
                                "downloaded": downloaded,
                                "ratio": ratio_str,
                                "ratio_value": ratio_value,
                                "ratio_health": ratio_health,
                                "status": status,
                                "enabled": enabled,
                                "profile_url": f"/profile/detail/{invitee.get('uid', '')}"
                            })
                    
                    # 解析已发送邀请
                    if "sentInvites" in data:
                        for invite in data["sentInvites"]:
                            result["sent_invites"].append({
                                "email": invite.get("email", ""),
                                "send_date": invite.get("created_at", ""),
                                "status": invite.get("status", ""),
                                "hash": invite.get("hash", "")
                            })
                
                except json.JSONDecodeError as e:
                    logger.error(f"解析M-Team页面JSON数据失败: {str(e)}")
            else:
                logger.error("没有找到M-Team邀请页面的JSON数据")
                result["invite_status"]["reason"] = "解析邀请页面失败，没有找到必要的数据"
            
            return result
            
        except Exception as e:
            logger.error(f"解析M-Team邀请页面失败: {str(e)}")
            result["invite_status"]["reason"] = f"解析邀请页面失败: {str(e)}"
            return result 