// API配置
let apiConfig = null;

// 最近获取的代码缓存
let codesCache = {
    data: null,
    timestamp: 0
};

// 配置加载状态
let configLoadAttempts = 0;
const MAX_LOAD_ATTEMPTS = 5;

// 设置周期性检查，确保配置正确加载
const CONFIG_CHECK_INTERVAL = 60000; // 每分钟检查一次
setInterval(async () => {
    if (!apiConfig) {
        if (configLoadAttempts < MAX_LOAD_ATTEMPTS) {
            console.log(`定期检查：配置未加载，第${configLoadAttempts + 1}次尝试重新加载...`);
            configLoadAttempts++;
            await loadApiConfig();
        }
    } else {
        // 配置已加载，重置尝试计数
        configLoadAttempts = 0;
    }
}, CONFIG_CHECK_INTERVAL);

// 在Service Worker激活时添加事件监听器
self.addEventListener('activate', (event) => {
    console.log('Service Worker 已激活');
    event.waitUntil(loadApiConfig());
});

// 添加空闲状态监听
chrome.idle && chrome.idle.onStateChanged.addListener((state) => {
    console.log('系统状态变化:', state);
    if (state === 'active') {
        // 系统从空闲状态恢复活动时，刷新配置
        loadApiConfig();
    }
});

// 在Service Worker启动时加载配置
loadApiConfig().then(() => {
    console.log('Service Worker已启动并加载配置');
});

// 初始化 - 从存储加载配置
chrome.runtime.onInstalled.addListener(async () => {
    await loadApiConfig();
    console.log('插件已安装或更新，已加载配置');
});

// 加载API配置
async function loadApiConfig() {
    try {
        const result = await chrome.storage.local.get(['apiConfig', 'connectionInfo']);
        if (result.apiConfig) {
            apiConfig = result.apiConfig;
            console.log('API配置已加载:', {
                baseUrl: apiConfig.baseUrl,
                apiKey: apiConfig.apiKey ? '已设置' : '未设置'
            });
        } else if (result.connectionInfo) {
            // 尝试从旧的connectionInfo迁移
            const connectionInfo = result.connectionInfo;
            apiConfig = {
                baseUrl: connectionInfo.serverUrl,
                apiKey: connectionInfo.apiKey
            };
            // 保存新格式
            await saveConfig(apiConfig);
            console.log('已从旧配置迁移');
        } else {
            console.log('未找到API配置');
        }
        return apiConfig;
    } catch (error) {
        console.error('加载配置失败:', error);
        return null;
    }
}

// 监听来自插件页面和content script的消息
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('收到消息:', message);
    
    // 处理字符串类型的消息
    if (typeof message === 'string') {
        if (message === 'fetchCodes') {
            fetchCodes().then(data => {
                sendResponse({ success: true, data });
            }).catch(error => {
                console.error('获取验证码失败:', error);
                sendResponse({ success: false, error: error.message });
            });
            return true;
        }
    }
    
    // 处理对象类型的消息
    if (typeof message === 'object') {
        switch(message.action) {
            case 'saveApiConfig':
                saveApiConfig(message.config, sendResponse);
                break;
            case 'resetApiConfig':
                resetApiConfig(message.config, sendResponse);
                break;
            case 'testConnection':
                testConnection(message.baseUrl, message.apiKey).then(result => {
                    sendResponse({ success: true });
                }).catch(error => {
                    sendResponse({ success: false, error: error.message });
                });
                break;
            case 'fetchCodes':
                fetchCodes().then(data => {
                    sendResponse({ success: true, data });
                }).catch(error => {
                    sendResponse({ success: false, error: error.message });
                });
                break;
            case 'fetchConfig':
                fetchConfig(sendResponse);
                break;
            case 'updateConfig':
                updateConfig(message.config, sendResponse);
                break;
            default:
                console.log('未知消息类型:', message.action);
                sendResponse({ success: false, message: '未知操作' });
        }
    }
    
    return true; // 保持消息通道开放以进行异步响应
});

// 保存API配置
async function saveApiConfig(config, sendResponse) {
    try {
        await saveConfig(config);
        sendResponse({ success: true });
    } catch (error) {
        console.error('保存API配置失败:', error);
        sendResponse({ success: false, message: error.message });
    }
}

// 保存配置
async function saveConfig(config) {
    if (!config || !config.baseUrl || !config.apiKey) {
        throw new Error('无效的配置信息');
    }

    try {
        // 更新内存中的配置
        apiConfig = config;
        
        // 保存到chrome.storage
        await chrome.storage.local.set({
            apiConfig: config,
            connectionInfo: {
                serverUrl: config.baseUrl,
                apiKey: config.apiKey,
                lastCheck: Date.now()
            }
        });
        
        console.log('配置已保存:', {
            baseUrl: config.baseUrl,
            apiKey: '已设置'
        });
    } catch (error) {
        console.error('保存配置失败:', error);
        throw error;
    }
}

// 从API获取验证码
async function fetchCodes() {
    try {
        // 如果没有配置，尝试重新加载
        if (!apiConfig) {
            console.log('配置未加载，尝试重新加载...');
            apiConfig = await loadApiConfig();
        }
        
        if (!apiConfig || !apiConfig.baseUrl || !apiConfig.apiKey) {
            throw new Error('未配置连接信息');
        }

        // 检查缓存
        const now = Date.now();
        if (codesCache.data && (now - codesCache.timestamp < 5000)) {
            console.log('使用缓存的验证码');
            return codesCache.data;
        }

        const response = await fetch(`${apiConfig.baseUrl}/api/v1/plugin/twofahelper/codes?apikey=${apiConfig.apiKey}`);
        if (!response.ok) {
            if (response.status === 401 || response.status === 403) {
                throw new Error('授权失败，请重新配置');
            }
            throw new Error(`服务器错误: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();
        
        // 更新缓存
        codesCache = {
            data: data.data || data,
            timestamp: now
        };

        return codesCache.data;
    } catch (error) {
        console.error('获取验证码失败:', error);
        throw error;
    }
}

// 测试连接
async function testConnection(baseUrl, apiKey) {
    try {
        const response = await fetch(`${baseUrl}/api/v1/plugin/twofahelper/test?apikey=${apiKey}`);
        if (!response.ok) {
            throw new Error(`连接测试失败: ${response.status} ${response.statusText}`);
        }
        
        // 测试成功，保存配置
        await saveConfig({ baseUrl, apiKey });
        
        return { success: true };
    } catch (error) {
        console.error('连接测试失败:', error);
        throw error;
    }
}

// 从API获取配置
async function fetchConfig(sendResponse) {
    try {
        // 如果没有配置，尝试重新加载
        if (!apiConfig) {
            console.log('配置未加载，尝试重新加载...');
            apiConfig = await loadApiConfig();
        }
        
        // 确保apiConfig不为null
        if (!apiConfig) {
            throw new Error('未配置连接信息');
        }
        
        // 检查配置是否有效
        if (!apiConfig.baseUrl) {
            throw new Error('未配置服务器地址');
        }
        
        if (!apiConfig.apiKey) {
            throw new Error('未设置API密钥');
        }
        
        // 构建API URL - 去除尾部斜杠
        let baseUrl = apiConfig.baseUrl;
        if (baseUrl.endsWith('/')) {
            baseUrl = baseUrl.slice(0, -1);
        }
        
        // 使用符合MP API格式的URL
        const configUrl = `${baseUrl}/api/v1/plugin/twofahelper/config?apikey=${apiConfig.apiKey}`;
        console.log('获取配置URL:', configUrl);
        
        const response = await fetch(configUrl, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        // 检查响应状态并输出详细信息
        console.log('配置API响应状态:', response.status, response.statusText);
        
        const responseText = await response.text();
        console.log('配置API响应内容:', responseText);
        
        if (!response.ok) {
            if (response.status === 404) {
                throw new Error('API不存在，请检查服务器地址或重启MP服务器');
            } else if (response.status === 401) {
                throw new Error('认证失败，请检查API密钥');
            } else if (response.status === 422) {
                throw new Error(`API参数格式错误: ${responseText}`);
            }
            
            throw new Error(`API请求失败 (${response.status}): ${responseText}`);
        }
        
        // 解析响应 - 确保是JSON格式
        let data;
        try {
            data = JSON.parse(responseText);
        } catch (error) {
            console.error('解析API响应失败:', error);
            throw new Error('无法解析API响应，非有效JSON格式');
        }
        
        console.log('获取配置成功，数据:', data);
        
        // 确保使用正确的数据结构
        const validData = data.data || data;
        
        // 发送响应
        if (sendResponse) {
            sendResponse({ success: true, data: validData });
        }
        
        return validData;
    } catch (error) {
        console.error('获取配置失败:', error);
        if (sendResponse) {
            sendResponse({ success: false, message: error.message });
        }
        throw error;
    }
}

// 更新配置
async function updateConfig(config, sendResponse) {
    try {
        // 如果没有配置，尝试重新加载
        if (!apiConfig) {
            console.log('配置未加载，尝试重新加载...');
            apiConfig = await loadApiConfig();
        }
        
        // 确保apiConfig不为null
        if (!apiConfig) {
            throw new Error('未配置连接信息');
        }
        
        // 检查配置是否有效
        if (!apiConfig.baseUrl) {
            throw new Error('未配置服务器地址');
        }
        
        if (!apiConfig.apiKey) {
            throw new Error('未设置API密钥');
        }
        
        // 构建API URL - 去除尾部斜杠
        let baseUrl = apiConfig.baseUrl;
        if (baseUrl.endsWith('/')) {
            baseUrl = baseUrl.slice(0, -1);
        }
        
        // 使用符合MP API格式的URL
        const updateUrl = `${baseUrl}/api/v1/plugin/twofahelper/update_config?apikey=${apiConfig.apiKey}`;
        console.log('更新配置URL:', updateUrl);
        
        const response = await fetch(updateUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(config)
        });
        
        // 检查响应状态并输出详细信息
        console.log('更新配置API响应状态:', response.status, response.statusText);
        
        const responseText = await response.text();
        console.log('更新配置API响应内容:', responseText);
        
        if (!response.ok) {
            if (response.status === 404) {
                throw new Error('API不存在，请检查服务器地址或重启MP服务器');
            } else if (response.status === 401) {
                throw new Error('认证失败，请检查API密钥');
            } else if (response.status === 422) {
                throw new Error(`API参数格式错误: ${responseText}`);
            }
            
            throw new Error(`API请求失败 (${response.status}): ${responseText}`);
        }
        
        // 解析响应 - 确保是JSON格式
        let data;
        try {
            data = JSON.parse(responseText);
        } catch (error) {
            console.error('解析API响应失败:', error);
            throw new Error('无法解析API响应，非有效JSON格式');
        }
        
        console.log('更新配置成功，数据:', data);
        
        // 清除代码缓存
        codesCache = {
            data: null,
            timestamp: 0
        };
        
        // 返回结果
        sendResponse({
            success: true,
            data: data.data || data
        });
    } catch (error) {
        console.error('更新配置失败:', error);
        sendResponse({
            success: false,
            message: error.message
        });
    }
}

// 重置API配置 (用于修复连接问题)
async function resetApiConfig(config, sendResponse) {
    try {
        console.log('正在重置API配置...');
        
        // 清空缓存
        apiConfig = null;
        codesCache = {
            data: null,
            timestamp: 0
        };
        
        // 重新保存配置
        if (config && config.baseUrl && config.apiKey) {
            await saveConfig(config);
            console.log('配置已重置并保存:', {
                baseUrl: config.baseUrl,
                apiKey: '已设置'
            });
            
            // 确保apiConfig被正确设置
            apiConfig = config;
            
            // 尝试测试连接
            try {
                await testConnection(config.baseUrl, config.apiKey);
                console.log('重置后连接测试成功');
                sendResponse({ success: true, message: '配置已重置并测试成功' });
            } catch (testError) {
                console.error('重置后连接测试失败:', testError);
                sendResponse({ success: false, message: `配置已重置但连接测试失败: ${testError.message}` });
            }
        } else {
            throw new Error('无效的配置信息');
        }
    } catch (error) {
        console.error('重置API配置失败:', error);
        sendResponse({ success: false, message: error.message });
    }
}
