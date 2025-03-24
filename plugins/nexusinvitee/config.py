"""
配置管理模块
"""
import os
import json
from typing import Dict, Any, Optional

from app.log import logger


class ConfigManager:
    """
    配置管理类
    """
    
    def __init__(self, data_path: str):
        """
        初始化配置管理
        :param data_path: 数据目录路径
        """
        self.data_path = data_path
        self.config_file = os.path.join(data_path, "config.json")
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        从文件加载配置
        :return: 配置字典
        """
        if not os.path.exists(self.config_file):
            return {}
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取配置文件失败: {str(e)}")
            return {}
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """
        保存配置到文件
        :param config: 配置字典
        :return: 是否成功
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            # 格式化保存为JSON
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                
            # 保存成功后更新内存配置
            self._config = config.copy()
            
            logger.debug(f"配置文件已保存: {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"保存配置到文件失败: {str(e)}")
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """
        获取当前配置
        :return: 配置字典
        """
        # 先重新从文件加载配置，确保返回最新的
        try:
            loaded_config = self._load_config()
            if loaded_config:
                self._config = loaded_config
        except Exception as e:
            logger.warning(f"重新加载配置文件失败: {str(e)}")
            
        return self._config
    
    def update_config(self, config: Dict[str, Any]) -> bool:
        """
        更新配置
        :param config: 新的配置字典
        :return: 是否成功
        """
        # 更新内存配置
        original_config = self._config.copy()
        self._config.update(config)
        
        # 保存到文件
        save_result = self.save_config(self._config)
        
        # 验证是否保存成功
        if save_result:
            # 重新加载配置以验证
            try:
                loaded_config = self._load_config()
                if loaded_config and ("onlyonce" in config and loaded_config.get("onlyonce") != config.get("onlyonce")):
                    logger.warning(f"配置保存不一致: 预期onlyonce={config.get('onlyonce')}, 实际={loaded_config.get('onlyonce')}")
                    # 强制再次保存
                    with open(self.config_file, 'w', encoding='utf-8') as f:
                        json.dump(self._config, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"验证配置保存失败: {str(e)}")
        else:
            # 保存失败，恢复原始配置
            self._config = original_config
            
        return save_result
    
    def get_value(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        :param key: 配置键
        :param default: 默认值
        :return: 配置值
        """
        return self._config.get(key, default) 