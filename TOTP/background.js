// 简化版background.js - 只保留核心功能，移除所有Service Worker和缓存机制

// 监听来自插件页面和content script的消息
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('收到消息:', message);
    
    // 处理对象类型的消息
    if (typeof message === 'object') {
        switch(message.action) {
            case 'testConnection':
                testConnection(message.baseUrl, message.apiKey)
                    .then(success => {
                        sendResponse({ success });
                    })
                    .catch(error => {
                        sendResponse({ success: false, error: error.message });
                    });
                break;
            case 'fetchCodes':
                fetchCodes(message.baseUrl, message.apiKey)
                    .then(data => {
                        sendResponse({ success: true, data });
                    })
                    .catch(error => {
                        sendResponse({ success: false, error: error.message });
                    });
                break;
            case 'updateConfig':
                // 处理配置更新请求
                if (message.config) {
                    // 直接返回成功，因为我们只需在前端保存配置
                    sendResponse({ success: true, message: '配置已更新' });
                } else {
                    sendResponse({ success: false, message: '无效的配置数据' });
                }
                break;
            default:
                console.log('未知消息类型:', message.action);
                sendResponse({ success: false, message: '未知操作' });
        }
    }
    
    return true; // 保持消息通道开放以进行异步响应
});

/**
 * 测试连接并验证API Key
 * @param {string} baseUrl 
 * @param {string} apiKey 
 * @returns {Promise<boolean>}
 */
async function testConnection(baseUrl, apiKey) {
    try {
        // 使用get_codes接口进行连接测试
        const response = await fetch(`${baseUrl}/api/v1/plugin/twofahelper/get_codes?apikey=${apiKey}`);
        if (!response.ok) {
            console.error(`API连接测试失败: ${response.status} ${response.statusText}`);
            return false;
        }
        
        const data = await response.json();
        // 检查返回的数据结构是否符合预期
        if (data.code === 0 || data.code === undefined) {
            console.log('API连接测试成功');
            return true;
        } else {
            console.error(`API连接测试返回错误: ${data.message || '未知错误'}`);
            return false;
        }
    } catch (error) {
        console.error(`API连接测试异常: ${error.message}`);
        return false;
    }
}

/**
 * 从API获取验证码
 * @param {string} baseUrl 
 * @param {string} apiKey 
 * @returns {Promise<Object>}
 */
async function fetchCodes(baseUrl, apiKey) {
    try {
        if (!baseUrl || !apiKey) {
            throw new Error('未设置API连接信息');
        }

        const response = await fetch(`${baseUrl}/api/v1/plugin/twofahelper/get_codes?apikey=${apiKey}`);
        if (!response.ok) {
            if (response.status === 401 || response.status === 403) {
                throw new Error('授权失败，请重新配置');
            }
            throw new Error(`服务器错误: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();
        return data.data || data;
    } catch (error) {
        console.error('获取验证码失败:', error);
        throw error;
    }
}
