"""
M-Team站点处理
"""
import re
import json
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

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
            "kp.m-team"
        ]
        
        site_url_lower = site_url.lower()
        for feature in mteam_features:
            if feature in site_url_lower:
                logger.info(f"匹配到M-Team站点特征: {feature}")
                return True
        
        return False
    
    def parse_invite_page(self, site_info: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
        """
        解析M-Team站点邀请页面
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
            return self._parse_mteam_invite_page(response.text)
            
        except Exception as e:
            logger.error(f"解析站点 {site_name} 邀请页面失败: {str(e)}")
            result["invite_status"]["reason"] = f"解析邀请页面失败: {str(e)}"
            return result
    
    def _parse_mteam_invite_page(self, html_content: str, stats_data: dict = None) -> Dict[str, Any]:
        """
        解析M-Team邀请页面HTML内容
        :param html_content: HTML内容
        :param stats_data: 统计数据
        :return: 解析结果
        """
        try:
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

            # 尝试从页面中提取JSON数据
            json_match = re.search(
                r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html_content)
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

                    # 解析被邀请人列表
                    if "invitees" in data:
                        for invitee in data["invitees"]:
                            result["invitees"].append({
                                "username": invitee.get("username", ""),
                                "email": invitee.get("email", ""),
                                "uploaded": self._format_size(invitee.get("uploaded", 0)),
                                "downloaded": self._format_size(invitee.get("downloaded", 0)),
                                # 转换为字符串
                                "ratio": str(round(float(invitee.get("ratio", 0)), 2)),
                                "ratio_value": float(invitee.get("ratio", 0)),
                                "ratio_health": self._get_ratio_health(float(invitee.get("ratio", 0))),
                                "status": invitee.get("status", ""),
                                "enabled": "Yes" if invitee.get("status") != "disabled" else "No",
                                "profile_url": f"/profile/detail/{invitee.get('uid', '')}",
                                # 添加后宫加成字段，设置默认值
                                "seed_bonus": invitee.get("inviteeBonus", "0.000"),
                                "seeding": invitee.get("seedingCount", "0"),
                                "seeding_size": self._format_size(invitee.get("seedingSize", 0)),
                                "seed_magic": invitee.get("seedMagic", "0.000"),
                                "last_seed_report": invitee.get("lastSeedReport", ""),
                                # 设置分享率标签和健康度
                                "ratio_label": self._get_ratio_label(float(invitee.get("ratio", 0))),
                                "ratio_health": self._get_ratio_health(float(invitee.get("ratio", 0)))
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

                except json.JSONDecodeError:
                    logger.error("解析M-Team页面JSON数据失败")

            return result

        except Exception as e:
            logger.error(f"解析M-Team邀请页面失败: {str(e)}")
            return {}

    def _format_size(self, size_bytes: int) -> str:
        """
        格式化文件大小
        :param size_bytes: 字节数
        :return: 格式化后的大小字符串
        """
        try:
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.2f} {unit}"
                size_bytes /= 1024.0
            return f"{size_bytes:.2f} PB"
        except:
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