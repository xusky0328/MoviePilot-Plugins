// 获取UI元素
document.addEventListener('DOMContentLoaded', function() {
    // 版本信息
    const CURRENT_VERSION = '1.1';
    const versionElement = document.getElementById('currentVersion');
    const updateNotice = document.getElementById('updateNotice');
    
    // 设置当前版本显示
    if (versionElement) {
        versionElement.textContent = `v${CURRENT_VERSION}`;
        
        // 为版本信息标签添加点击事件
        versionElement.style.cursor = 'pointer';
        versionElement.title = '点击查看版本信息';
        versionElement.addEventListener('click', function() {
            // 打开GitHub仓库release页面
            chrome.tabs.create({
                url: 'https://github.com/madrays/MoviePilot-Plugins/releases'
            });
        });
    }
    
    // 初始化时检查更新
    checkForUpdates();
    
    // 点击更新提示
    if (updateNotice) {
        updateNotice.addEventListener('click', function() {
            // 打开GitHub仓库或下载页面
            chrome.tabs.create({
                url: 'https://github.com/madrays/MoviePilot-Plugins/releases'
            });
        });
    }
    
    const baseUrlInput = document.getElementById('baseUrl');
    const apiKeyInput = document.getElementById('apiKey');
    const testConnectionBtn = document.getElementById('testConnection');
    const clearSettingsBtn = document.getElementById('clearSettings');
    const statusDiv = document.getElementById('status');
    const addSiteBtn = document.getElementById('addSite');
    const siteNameInput = document.getElementById('siteName');
    const secretInput = document.getElementById('secret');
    const urlsTextarea = document.getElementById('urls');
    const sitesListDiv = document.getElementById('sitesList');
    const exportConfigBtn = document.getElementById('exportConfig');
    const importConfigBtn = document.getElementById('importConfig');
    const importFileInput = document.getElementById('importFile');
    
    // 初始化自定义排序数组
    let customOrder = [];
    
    // 图标相关元素
    const iconPreview = document.getElementById('iconPreview');
    const iconFileInput = document.getElementById('iconFile');
    const selectIconButton = document.getElementById('selectIconButton');
    const removeIconButton = document.getElementById('removeIconButton');
    const autoFetchIconButton = document.getElementById('autoFetchIconButton');
    
    // 存储当前图标的数据URL
    let currentIconDataUrl = null;

    console.log('选项页面已加载，DOM元素获取状态:', {
        baseUrlInput: !!baseUrlInput,
        apiKeyInput: !!apiKeyInput,
        testConnectionBtn: !!testConnectionBtn
    });

    // 存储当前配置
    let currentConfig = {
        sites: {},
        baseUrl: '',
        apiKey: ''
    };

    // 初始化
    loadConfig();
    
    // 图标选择按钮点击事件
    if (selectIconButton) {
        selectIconButton.addEventListener('click', function() {
            iconFileInput.click();
        });
    }
    
    // 图标文件选择改变事件
    if (iconFileInput) {
        iconFileInput.addEventListener('change', handleIconFileSelected);
    }
    
    // 移除图标按钮点击事件
    if (removeIconButton) {
        removeIconButton.addEventListener('click', function() {
            currentIconDataUrl = null;
            updateIconPreview();
        });
    }
    
    // 自动获取图标按钮点击事件
    if (autoFetchIconButton) {
        autoFetchIconButton.addEventListener('click', function() {
            const urls = parseUrls(urlsTextarea.value);
            if (urls.length > 0) {
                autoFetchIcon(urls[0]);
            } else {
                showStatus('请至少输入一个站点URL', true);
            }
        });
    }
    
    // 当URL文本框失去焦点时自动尝试获取图标
    if (urlsTextarea) {
        urlsTextarea.addEventListener('blur', function() {
            const urls = parseUrls(urlsTextarea.value);
            if (urls.length > 0 && !currentIconDataUrl) {
                // 只有在没有图标的情况下才尝试自动获取
                autoFetchIcon(urls[0]);
            }
        });
    }
    
    // 解析URL文本框中的URL
    function parseUrls(urlsText) {
        return urlsText
            .split('\n')
            .map(url => url.trim())
            .filter(url => url.length > 0)
            .map(normalizeUrl);
    }
    
    // 自动获取图标
    function autoFetchIcon(url) {
        try {
            if (!url) return;
            
            // 显示正在获取图标
            iconPreview.innerHTML = '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;"><span style="font-size:10px;">加载中</span></div>';
            
            // 提取域名
            let domain = url;
            try {
                domain = new URL(url).hostname;
            } catch (e) {
                console.error('无法解析URL:', e);
            }
            
            // 首先尝试直接获取网站的favicon
            let faviconUrl = `https://${domain}/favicon.ico`;
            
            // 创建图像元素
            const img = new Image();
            
            // 图像加载成功回调
            img.onload = function() {
                // 创建canvas元素
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                canvas.width = img.width;
                canvas.height = img.height;
                
                // 将图像绘制到canvas上
                ctx.drawImage(img, 0, 0);
                
                // 将canvas内容转换为DataURL
                try {
                    currentIconDataUrl = canvas.toDataURL('image/png');
                    updateIconPreview();
                    console.log('自动获取图标成功');
                } catch (e) {
                    console.error('转换图标格式失败:', e);
                    tryFallbackIcon(domain);
                }
            };
            
            // 图像加载失败回调
            img.onerror = function() {
                console.error('无法直接加载favicon，尝试备用方案');
                tryFallbackIcon(domain);
            };
            
            // 设置跨域属性并加载图像
            img.crossOrigin = 'Anonymous';
            img.src = faviconUrl;
            
        } catch (error) {
            console.error('自动获取图标失败:', error);
            iconPreview.innerHTML = '';
        }
    }
    
    // 尝试备用图标获取方法
    function tryFallbackIcon(domain) {
        // 尝试Google Favicon服务
        const googleFaviconUrl = `https://www.google.com/s2/favicons?domain=${domain}&sz=64`;
                
                const fallbackImg = new Image();
                fallbackImg.onload = function() {
                    // 创建canvas元素
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    canvas.width = fallbackImg.width;
                    canvas.height = fallbackImg.height;
                    
                    // 将图像绘制到canvas上
                    ctx.drawImage(fallbackImg, 0, 0);
                    
                    // 将canvas内容转换为DataURL
                    try {
                        currentIconDataUrl = canvas.toDataURL('image/png');
                        updateIconPreview();
                console.log('使用Google服务获取图标成功');
                    } catch (e) {
                console.error('转换Google图标格式失败:', e);
                tryDuckDuckGoIcon(domain);
                    }
                };
                
                fallbackImg.onerror = function() {
            console.error('无法通过Google获取图标，尝试DuckDuckGo');
            tryDuckDuckGoIcon(domain);
                };
                
                // 设置跨域属性并加载图像
                fallbackImg.crossOrigin = 'Anonymous';
        fallbackImg.src = googleFaviconUrl;
    }
    
    // 尝试DuckDuckGo图标API
    function tryDuckDuckGoIcon(domain) {
        const ddgIconUrl = `https://icons.duckduckgo.com/ip3/${domain}.ico`;
        
        const ddgImg = new Image();
        ddgImg.onload = function() {
            // 创建canvas元素
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            canvas.width = ddgImg.width;
            canvas.height = ddgImg.height;
            
            // 将图像绘制到canvas上
            ctx.drawImage(ddgImg, 0, 0);
            
            // 将canvas内容转换为DataURL
            try {
                currentIconDataUrl = canvas.toDataURL('image/png');
                updateIconPreview();
                console.log('使用DuckDuckGo获取图标成功');
            } catch (e) {
                console.error('转换DuckDuckGo图标格式失败:', e);
            iconPreview.innerHTML = '';
        }
        };
        
        ddgImg.onerror = function() {
            console.error('无法获取网站图标');
            iconPreview.innerHTML = '';
        };
        
        // 设置跨域属性并加载图像
        ddgImg.crossOrigin = 'Anonymous';
        ddgImg.src = ddgIconUrl;
    }
    
    // 处理选择的图标文件
    function handleIconFileSelected(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        // 检查文件类型是否为图片
        if (!file.type.startsWith('image/')) {
            showStatus('请选择有效的图片文件', true);
            return;
        }
        
        // 检查文件大小 (最大100KB)
        if (file.size > 100 * 1024) {
            showStatus('图片文件过大，请选择小于100KB的图片', true);
            return;
        }
        
        // 读取文件为DataURL
        const reader = new FileReader();
        reader.onload = function(e) {
            currentIconDataUrl = e.target.result;
            updateIconPreview();
        };
        reader.readAsDataURL(file);
    }
    
    // 更新图标预览
    function updateIconPreview() {
        if (currentIconDataUrl) {
            // 显示图标预览
            iconPreview.innerHTML = `<img src="${currentIconDataUrl}" alt="站点图标">`;
            // 显示移除按钮
            if (removeIconButton) removeIconButton.style.display = 'block';
        } else {
            // 清空预览
            iconPreview.innerHTML = '';
            // 隐藏移除按钮
            if (removeIconButton) removeIconButton.style.display = 'none';
        }
    }

    // 显示状态消息
    function showStatus(message, isError = false) {
        statusDiv.innerText = message;
        statusDiv.className = isError ? 'status error' : 'status success';
        statusDiv.style.display = 'block';
        
        setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 5000);
    }

    // 从存储加载配置
    function loadConfig() {
        console.log('开始从存储加载配置...');
        
        chrome.storage.sync.get(['apiConfig', 'apiBaseUrl', 'apiKey'], result => {
            console.log('加载配置结果:', result);
            
            let configLoaded = false;
            
            // 尝试从apiConfig加载
            if (result.apiConfig) {
                const config = result.apiConfig;
                
                // 更新内存中的配置
                currentConfig = {
                    ...currentConfig,
                    baseUrl: config.baseUrl || '',
                    apiKey: config.apiKey || ''
                };
                
                // 更新UI
                baseUrlInput.value = currentConfig.baseUrl;
                apiKeyInput.value = currentConfig.apiKey;
                
                console.log('从apiConfig加载配置成功:', currentConfig);
                configLoaded = true;
            }
            // 尝试从单独的字段加载
            else if (result.apiBaseUrl && result.apiKey) {
                // 更新内存中的配置
                currentConfig = {
                    ...currentConfig,
                    baseUrl: result.apiBaseUrl,
                    apiKey: result.apiKey
                };
                
                // 更新UI
                baseUrlInput.value = currentConfig.baseUrl;
                apiKeyInput.value = currentConfig.apiKey;
                
                console.log('从单独字段加载配置成功:', currentConfig);
                configLoaded = true;
            }
            
            if (configLoaded) {
                // 加载站点列表
                console.log('配置加载完成，开始刷新站点列表');
                refreshSitesList();
            } else {
                console.log('未找到有效配置');
                
                // 确保sitesListDiv存在
                const sitesListDiv = document.getElementById('sites-list') || document.getElementById('sitesList');
                if (sitesListDiv) {
                    sitesListDiv.innerHTML = '<div class="help-text">请先配置服务器地址和API密钥</div>';
                }
            }
        });
    }

    // 加载站点列表的函数，作为refreshSitesList的别名
    async function loadSitesList() {
        await refreshSitesList();
    }

    // 保存配置
    function saveConfig() {
        // 更新内存中的配置
        chrome.storage.sync.set({ 
            apiConfig: currentConfig
        }, () => {
            console.log('配置已保存');
        });
    }

    // 标准化URL
    function normalizeUrl(url) {
        // 确保URL以http或https开头
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            url = 'http://' + url;
        }
        
        // 去除URL末尾的斜杠
        while (url.endsWith('/')) {
            url = url.slice(0, -1);
        }
        
        return url;
    }

    // 刷新站点列表
    async function refreshSitesList() {
        try {
            console.log('开始刷新站点列表...');
            
            // 先获取API配置
            const config = await loadApiConfig();
            console.log('获取API配置结果:', config);
            
            if (!config || !config.baseUrl || !config.apiKey) {
                console.log('未配置API连接信息，无法刷新站点列表');
                sitesListDiv.innerHTML = '<div class="help-text">请先配置服务器地址和API密钥</div>';
            return;
        }
        
            showStatus('正在获取站点列表...');
            
            // 直接从API获取配置
            const apiUrl = `${config.baseUrl}/api/v1/plugin/twofahelper/config?apikey=${config.apiKey}`;
            console.log('请求站点列表URL:', apiUrl);
            
            const response = await fetch(apiUrl);
            if (!response.ok) {
                throw new Error(`服务器返回错误 (${response.status}): ${response.statusText}`);
            }
            
            const data = await response.json();
            console.log('获取到的站点数据:', data);
            
            // 提取站点数据 - 灵活处理不同格式
            let sitesData;
            if (data.data) {
                // 新接口格式: { code: 0, data: {sites...} }
                sitesData = data.data;
            } else if (data.success && data.result) {
                // 另一种格式: { success: true, result: {sites...} }
                sitesData = data.result;
            } else {
                // 直接返回站点对象的格式
                sitesData = data;
            }
            
            if (!sitesData || typeof sitesData !== 'object') {
                console.error('无效的站点数据格式:', data);
                throw new Error('返回的站点数据格式无效');
            }
            
            // 更新当前配置中的站点
            currentConfig.sites = sitesData;
            
            // 渲染站点列表
            console.log('开始渲染站点列表, 站点数量:', Object.keys(sitesData).length);
            renderSitesList(sitesData);
            
            // 显示成功消息
            const sitesCount = Object.keys(sitesData).length;
            showStatus(`获取成功，找到 ${sitesCount} 个站点`);
            
            return sitesData;
        } catch (error) {
            console.error('获取站点列表失败:', error);
            showStatus(`获取站点列表失败: ${error.message}`, true);
            
            // 确保sitesListDiv存在
            const sitesListDiv = document.getElementById('sites-list') || document.getElementById('sitesList');
            if (sitesListDiv) {
                sitesListDiv.innerHTML = `<div class="error-message">获取站点列表失败: ${error.message}</div>`;
            }
        }
    }
    
    // 渲染站点列表
    function renderSitesList(sites) {
        const container = document.getElementById('sitesList');
        container.innerHTML = '';
        
        // 更新站点计数
        const sitesCount = Object.keys(sites).length;
        document.getElementById('sitesCount').textContent = `${sitesCount}个站点`;
        
        if (sitesCount === 0) {
            container.innerHTML = '<div class="help-text">尚未配置任何站点。点击"添加站点"来开始。</div>';
                return;
            }
            
        // 初始排序顺序：保持自定义顺序
        let sortOrder = 'custom';
        
        // 提供站点数据和排序方式
        renderSites(sites, sortOrder);
        
        // 启用拖拽排序
        enableDragSort(container);
    }
    
    // 渲染站点列表
    function renderSites(sites, sortOrder) {
        const container = document.getElementById('sitesList');
        container.innerHTML = '';
        
        let siteNames = Object.keys(sites);
        
        // 根据排序方式对站点名称进行排序
        if (sortOrder === 'alphabetical') {
            siteNames.sort();
        } else if (sortOrder === 'custom' && customOrder && customOrder.length > 0) {
            // 使用自定义排序
            siteNames.sort((a, b) => {
                const indexA = customOrder.indexOf(a);
                const indexB = customOrder.indexOf(b);
                
                // 如果两个站点都在自定义顺序中，按照自定义顺序排列
                if (indexA !== -1 && indexB !== -1) {
                    return indexA - indexB;
                }
                
                // 如果其中一个站点不在自定义顺序中，将其排在后面
                if (indexA === -1) return 1;
                if (indexB === -1) return -1;
                
                // 默认按字母排序
                return a.localeCompare(b);
            });
        }
        
        // 更新自定义排序数组
        customOrder = [...siteNames];
        
        // 遍历站点并创建卡片
        siteNames.forEach(siteName => {
            const site = sites[siteName];
            
            // 创建站点卡片
            const card = document.createElement('div');
            card.className = 'site-card';
            card.dataset.siteName = siteName;
            card.draggable = true; // 启用拖拽
            
            // 站点头部（图标和名称）
            const header = document.createElement('div');
            header.className = 'site-header';
            
            // 添加拖动手柄
            const dragHandle = document.createElement('div');
            dragHandle.className = 'drag-handle';
            dragHandle.innerHTML = '⋮';
            dragHandle.title = '拖动调整顺序';
            dragHandle.style.cursor = 'move';
            dragHandle.style.marginRight = '5px';
            header.appendChild(dragHandle);
            
            // 站点图标
            const iconContainer = document.createElement('div');
            iconContainer.className = 'site-icon-sm';
            
            if (site.icon && site.icon.startsWith('data:')) {
                const iconImg = document.createElement('img');
                iconImg.src = site.icon;
                iconImg.alt = siteName;
                iconContainer.appendChild(iconImg);
            } else {
                // 使用首字母作为占位符
                iconContainer.textContent = siteName.charAt(0).toUpperCase();
            }
            
            header.appendChild(iconContainer);
            
            // 站点名称
            const nameEl = document.createElement('div');
            nameEl.className = 'site-name-sm';
            nameEl.textContent = siteName;
            header.appendChild(nameEl);
            
            card.appendChild(header);
            
            // 密钥（默认隐藏）
            const secretEl = document.createElement('div');
            secretEl.className = 'site-secret-sm';
            secretEl.style.display = 'none'; // 默认隐藏密钥
            secretEl.textContent = site.secret;
            card.appendChild(secretEl);
            
            // URL列表
            if (site.urls && site.urls.length > 0) {
                const urlsEl = document.createElement('div');
                urlsEl.className = 'site-urls-sm';
                urlsEl.textContent = site.urls[0] + (site.urls.length > 1 ? ` +${site.urls.length - 1}个网址` : '');
                card.appendChild(urlsEl);
            }
            
            // 操作按钮
            const actions = document.createElement('div');
            actions.className = 'site-actions';
            
            // 编辑按钮
            const editBtn = document.createElement('button');
            editBtn.textContent = '编辑';
            editBtn.className = 'btn-secondary';
            editBtn.onclick = () => editSite(siteName);
            
            // 删除按钮
            const deleteBtn = document.createElement('button');
            deleteBtn.textContent = '删除';
            deleteBtn.className = 'delete-btn';
            deleteBtn.style.backgroundColor = '#f44336';
            deleteBtn.style.color = 'white';
            deleteBtn.onclick = () => deleteSite(siteName);
            
            actions.appendChild(editBtn);
            actions.appendChild(deleteBtn);
            card.appendChild(actions);
            
            // 添加到容器
            container.appendChild(card);
        });
    }
    
    // 启用拖拽排序
    function enableDragSort(container) {
        let draggedItem = null;
        
        // 添加拖拽事件监听器
        container.addEventListener('dragstart', function(e) {
            // 确保我们拖拽的是卡片元素
            draggedItem = e.target.closest('.site-card');
            if (!draggedItem) return;
            
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', ''); // 必须设置一些数据才能拖拽
            
            // 添加拖拽中的样式
            setTimeout(() => {
                draggedItem.classList.add('dragging');
                draggedItem.style.opacity = '0.5';
            }, 0);
        });
        
        container.addEventListener('dragend', function(e) {
            if (draggedItem) {
                // 移除拖拽中的样式
                draggedItem.classList.remove('dragging');
                draggedItem.style.opacity = '1';
                
                // 保存新的排序顺序
                saveCustomOrder();
                
                draggedItem = null;
            }
        });
        
        container.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            
            // 获取当前鼠标下的卡片
            const targetCard = e.target.closest('.site-card');
            if (!targetCard || targetCard === draggedItem) return;
            
            // 计算鼠标位置在卡片上半部分还是下半部分
            const targetRect = targetCard.getBoundingClientRect();
            const mouseY = e.clientY;
            const isInUpperHalf = mouseY < targetRect.top + targetRect.height / 2;
            
            // 清除所有卡片的边框样式
            const cards = container.querySelectorAll('.site-card');
            cards.forEach(card => {
                card.style.borderTop = '';
                card.style.borderBottom = '';
            });
            
            // 根据鼠标位置显示放置指示器
            if (isInUpperHalf) {
                targetCard.style.borderTop = '2px solid #1976d2';
            } else {
                targetCard.style.borderBottom = '2px solid #1976d2';
            }
        });
        
        container.addEventListener('dragleave', function(e) {
            // 当鼠标离开卡片时，清除边框样式
            const targetCard = e.target.closest('.site-card');
            if (targetCard) {
                targetCard.style.borderTop = '';
                targetCard.style.borderBottom = '';
            }
        });
        
        container.addEventListener('drop', function(e) {
            e.preventDefault();
            
            // 获取目标卡片
            const targetCard = e.target.closest('.site-card');
            if (!targetCard || !draggedItem || targetCard === draggedItem) return;
            
            // 清除所有卡片的边框样式
            const cards = container.querySelectorAll('.site-card');
            cards.forEach(card => {
                card.style.borderTop = '';
                card.style.borderBottom = '';
            });
            
            // 计算鼠标位置在卡片上半部分还是下半部分
            const targetRect = targetCard.getBoundingClientRect();
            const mouseY = e.clientY;
            const isInUpperHalf = mouseY < targetRect.top + targetRect.height / 2;
            
            // 插入拖拽的卡片到目标位置
            if (isInUpperHalf) {
                container.insertBefore(draggedItem, targetCard);
            } else {
                container.insertBefore(draggedItem, targetCard.nextSibling);
            }
            
            // 更新自定义排序数组
            updateCustomOrderFromDOM();
            
            // 保存新的排序顺序
            saveCustomOrder();
        });
    }
    
    // 从DOM中更新自定义排序数组
    function updateCustomOrderFromDOM() {
        const container = document.getElementById('sitesList');
        const cards = Array.from(container.querySelectorAll('.site-card'));
        
        // 创建新的排序数组
        customOrder = cards.map(card => card.dataset.siteName);
        console.log('Updated custom order:', customOrder);
    }
    
    // 保存自定义排序
    async function saveCustomOrder() {
        try {
            // 确保已更新自定义排序数组
            updateCustomOrderFromDOM();
            
            // 获取API配置
            const config = await loadApiConfig();
            if (!config || !config.baseUrl || !config.apiKey) {
                throw new Error('未配置API连接信息，无法保存排序');
            }
            
            console.log('正在保存自定义排序...');
            showStatus('正在保存排序...');
            
            // 获取所有站点
            if (!currentConfig.sites || Object.keys(currentConfig.sites).length === 0) {
                throw new Error('没有站点数据可供排序');
            }
            
            // 创建有序的站点对象
            const orderedSites = {};
            
            // 按照自定义顺序遍历站点名称
            customOrder.forEach(siteName => {
                if (currentConfig.sites[siteName]) {
                    orderedSites[siteName] = currentConfig.sites[siteName];
                }
            });
            
            // 直接调用API更新配置
            const response = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/update_config?apikey=${config.apiKey}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(orderedSites)
            });
            
            if (!response.ok) {
                throw new Error(`服务器返回错误 (${response.status}): ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // 检查返回数据
            if (data.code === 0 || data.code === undefined || data.success === true) {
                // 更新内存中的配置
                currentConfig.sites = orderedSites;
                console.log('自定义排序已保存');
                showStatus('排序已保存');
                return true;
            } else {
                throw new Error(data.message || '服务器返回错误');
            }
        } catch (error) {
            console.error('保存排序失败:', error);
            showStatus(`保存排序失败: ${error.message}`, true);
            return false;
        }
    }

    // 当URL文本框改变时自动获取图标
    if (urlsTextarea) {
        urlsTextarea.addEventListener('input', function() {
            const urls = parseUrls(urlsTextarea.value);
            if (urls.length > 0 && !currentIconDataUrl) {
                // 只有在没有图标的情况下才尝试自动获取
                autoFetchIcon(urls[0]);
            }
        });
    }

    // 测试连接
    async function testConnection() {
        try {
            const baseUrlInput = document.getElementById('baseUrl');
            const apiKeyInput = document.getElementById('apiKey');
            
            // 获取输入值
            let baseUrl = baseUrlInput.value.trim();
            const apiKey = apiKeyInput.value.trim();
            
            console.log('测试连接中...', baseUrl);
            console.log('测试连接使用的API密钥:', apiKey);
            
            // 验证输入
            if (!baseUrl || !apiKey) {
                showStatus('请输入服务器地址和API密钥', true);
                return false;
            }
            
            // 标准化URL
            baseUrl = normalizeUrl(baseUrl);
            baseUrlInput.value = baseUrl;
            
            // 显示正在连接状态
            showStatus('正在测试连接...', false, true);
            
            // 直接调用API进行测试
            const response = await fetch(`${baseUrl}/api/v1/plugin/twofahelper/get_codes?apikey=${apiKey}`);
            if (!response.ok) {
                throw new Error(`服务器返回错误 (${response.status}): ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // 检查返回数据格式
            if (data.code === 0 || data.code === undefined) {
                // 测试成功，保存配置
                await saveApiConfig(baseUrl, apiKey);
                
                // 更新当前配置
                currentConfig = {
                    baseUrl: baseUrl,
                    apiKey: apiKey
                };
                
                await chrome.storage.sync.set({ 
                    apiConfig: currentConfig,
                    connectionTested: true
                });
                
                showStatus('连接测试成功，配置已保存');
                
                // 测试成功后刷新站点列表
                await refreshSitesList();
                
                return true;
            } else {
                throw new Error(data.message || '未知错误');
            }
        } catch (error) {
            console.log('测试连接失败:', error);
            showStatus(`连接测试失败: ${error.message}`, true);
            return false;
        }
    }

    // 删除站点
    async function deleteSite(siteName) {
        try {
            if (!confirm(`确定要删除站点 ${siteName} 吗？`)) {
                return;
            }
            
            // 检查配置
            if (!currentConfig.sites || !currentConfig.sites[siteName]) {
                showStatus(`站点 ${siteName} 不存在`, true);
                return;
            }
            
            // 创建新的配置（移除要删除的站点）
            const newSites = { ...currentConfig.sites };
            delete newSites[siteName];
            
            // 获取API配置
            const config = await loadApiConfig();
            if (!config || !config.baseUrl || !config.apiKey) {
                throw new Error('未配置API连接信息，无法删除站点');
            }
            
            showStatus('正在删除站点...');
            
            // 直接调用API更新配置
            const response = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/update_config?apikey=${config.apiKey}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(newSites)
            });
            
            if (!response.ok) {
                throw new Error(`服务器返回错误 (${response.status}): ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // 检查返回数据
            if (data.code === 0 || data.code === undefined || data.success === true) {
                // 更新内存中的配置
                currentConfig.sites = newSites;
                
                // 显示成功消息
                showStatus(`站点 ${siteName} 已删除`);
                
                // 刷新站点列表
                await refreshSitesList();
            } else {
                throw new Error(data.message || '服务器返回错误');
            }
        } catch (error) {
            console.error('删除站点失败:', error);
            showStatus(`删除站点失败: ${error.message}`, true);
        }
    }

    // 编辑站点
    async function editSite(siteName) {
        try {
            // 确保有站点数据
            if (!currentConfig.sites || !currentConfig.sites[siteName]) {
                showStatus(`站点 ${siteName} 不存在`, true);
                return;
            }
            
            // 获取站点数据
            const siteData = currentConfig.sites[siteName];
            
            // 填充表单
            siteNameInput.value = siteName;
            secretInput.value = siteData.secret || '';
            urlsTextarea.value = (siteData.urls || []).join('\n');
            
            // 设置图标
            currentIconDataUrl = siteData.icon || null;
            updateIconPreview();
            
            // 滚动到添加站点表单
            const siteSectionTitle = document.getElementById('siteSectionTitle');
            if (siteSectionTitle) {
                siteSectionTitle.textContent = `编辑站点: ${siteName}`;
                siteSectionTitle.scrollIntoView({ behavior: 'smooth' });
            }
            
            // 聚焦到第一个输入框
            siteNameInput.focus();
            
            // 更改按钮文本为"更新站点"
            addSiteBtn.textContent = '更新站点';
            addSiteBtn.dataset.editing = siteName;
            
            showStatus(`正在编辑站点 ${siteName}`);
        } catch (error) {
            console.error('编辑站点失败:', error);
            showStatus(`编辑站点失败: ${error.message}`, true);
        }
    }

    // 添加站点
    async function addSite() {
        try {
            // 获取输入值
            const siteName = siteNameInput.value.trim();
            const secret = secretInput.value.trim().replace(/\s+/g, ''); // 移除所有空格
            const urlsText = urlsTextarea.value.trim();
            
            // 验证输入
            if (!siteName) {
                showStatus('请输入站点名称', true);
                return;
            }
            
            if (!secret) {
                showStatus('请输入TOTP密钥', true);
                return;
            }
            
            // 解析URLs
            const urls = urlsText
                .split('\n')
                .map(url => url.trim())
                .filter(url => url.length > 0)
                .map(normalizeUrl);
            
            // 获取API配置
            const config = await loadApiConfig();
            if (!config || !config.baseUrl || !config.apiKey) {
                throw new Error('未配置API连接信息，无法添加/更新站点');
            }
            
            showStatus('正在获取当前配置...');
            
            // 直接从API获取当前配置
            const response = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/config?apikey=${config.apiKey}`);
            if (!response.ok) {
                throw new Error(`服务器返回错误 (${response.status}): ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // 提取站点数据
            let sites;
            if (data.data) {
                sites = data.data;
            } else if (data.success && data.result) {
                sites = data.result;
            } else {
                sites = data;
            }
            
            if (!sites || typeof sites !== 'object') {
                throw new Error('获取配置时返回的数据格式无效');
            }
            
            // 检查站点是否已存在
            const isUpdate = !!sites[siteName] || addSiteBtn.dataset.editing;
            
            // 保存或更新站点
            if (isUpdate) {
                // 如果是更新，保持原有站点属性，只更新需要修改的内容
                sites[siteName] = {
                    ...sites[siteName],
                    secret: secret,
                    urls: urls,
                    icon: currentIconDataUrl || (sites[siteName] ? sites[siteName].icon : null)
                };
            } else {
                // 如果是新增，创建一个新的站点配置
                const newSites = {};
                
                // 保留原有站点
                Object.entries(sites).forEach(([key, value]) => {
                    newSites[key] = value;
                });
                
                // 添加新站点到末尾
                newSites[siteName] = {
                    secret: secret,
                    urls: urls,
                    icon: currentIconDataUrl
                };
                
                // 替换sites引用，保持顺序
                sites = newSites;
            }
            
            showStatus('正在保存站点配置...');
            
            // 直接调用API更新配置
            const updateResponse = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/update_config?apikey=${config.apiKey}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(sites)
            });
            
            if (!updateResponse.ok) {
                throw new Error(`服务器返回错误 (${updateResponse.status}): ${updateResponse.statusText}`);
            }
            
            const updateData = await updateResponse.json();
            
            // 检查返回数据
            if (updateData.code === 0 || updateData.code === undefined || updateData.success === true) {
                // 更新内存中的配置
                currentConfig.sites = sites;
                
                // 显示成功消息
                const action = isUpdate ? '更新' : '添加';
                showStatus(`站点 ${siteName} 已${action}`);
                
                // 清空输入
                siteNameInput.value = '';
                secretInput.value = '';
                urlsTextarea.value = '';
                currentIconDataUrl = null;
                updateIconPreview();
                
                // 重置按钮文本和标题
                addSiteBtn.textContent = '添加站点';
                delete addSiteBtn.dataset.editing;
                
                const siteSectionTitle = document.getElementById('siteSectionTitle');
                if (siteSectionTitle) {
                    siteSectionTitle.textContent = '添加/编辑站点';
                }
                
                // 刷新站点列表
                await refreshSitesList();
            } else {
                throw new Error(updateData.message || '服务器返回错误');
            }
        } catch (error) {
            console.error('添加/更新站点失败:', error);
            showStatus(`添加/更新站点失败: ${error.message}`, true);
        }
    }

    // 导出配置
    async function exportConfig() {
        try {
            // 获取API配置
            const config = await loadApiConfig();
            if (!config || !config.baseUrl || !config.apiKey) {
                throw new Error('未配置API连接信息，无法导出配置');
            }
            
            showStatus('正在获取配置数据...');
            
            // 直接从API获取当前配置
            const response = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/config?apikey=${config.apiKey}`);
            if (!response.ok) {
                throw new Error(`服务器返回错误 (${response.status}): ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // 提取站点数据
            let sites;
            if (data.data) {
                sites = data.data;
            } else if (data.success && data.result) {
                sites = data.result;
            } else {
                sites = data;
            }
            
            if (!sites || typeof sites !== 'object') {
                throw new Error('获取配置时返回的数据格式无效');
            }
            
            // 创建下载链接
            const dataStr = JSON.stringify(sites, null, 2);
            const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr);
            
            const exportLink = document.createElement('a');
            exportLink.setAttribute('href', dataUri);
            exportLink.setAttribute('download', 'totp_config.json');
            document.body.appendChild(exportLink);
            exportLink.click();
            document.body.removeChild(exportLink);
            
            showStatus('配置已导出');
        } catch (error) {
            console.error('导出配置失败:', error);
            showStatus(`导出配置失败: ${error.message}`, true);
        }
    }

    // 导入配置
    function importConfig() {
        importFileInput.click();
    }

    // 处理导入文件
    async function handleImportFile(event) {
        try {
        const file = event.target.files[0];
        if (!file) {
            return;
        }
        
            // 读取文件
        const reader = new FileReader();
            
            reader.onload = async (e) => {
                try {
                    const config = JSON.parse(e.target.result);
                    
                    // 验证配置
                    if (typeof config !== 'object') {
                        showStatus('导入失败: 配置格式不正确', true);
                        return;
                    }
                    
                    // 更新服务器
                    const result = await new Promise(resolve => {
                        chrome.runtime.sendMessage(
                            { 
                                action: 'updateConfig',
                                config: config
                            },
                            resolve
                        );
                    });
                    
                    if (result.success) {
                        // 更新内存中的配置
                        currentConfig.sites = config;
                        
                        // 显示成功消息
                        const sitesCount = Object.keys(config).length;
                        showStatus(`导入成功，共 ${sitesCount} 个站点`);
                        
                        // 刷新站点列表
                        await refreshSitesList();
                    } else {
                        showStatus(`导入失败: ${result.message}`, true);
                    }
                } catch (error) {
                    console.error('解析导入文件失败:', error);
                    showStatus(`导入失败: ${error.message}`, true);
                }
            };
            
            reader.readAsText(file);
        } catch (error) {
            console.error('导入文件处理失败:', error);
            showStatus(`导入失败: ${error.message}`, true);
        }
    }

    // 清除设置
    function clearSettings() {
        // 确认对话框
        if (confirm('确定要清除所有设置吗？这不会影响服务器上的配置，但会清除本地保存的服务器地址和密钥。')) {
            // 清空输入框
            baseUrlInput.value = '';
            apiKeyInput.value = '';
            
            // 清空内存中的配置
            currentConfig = {
                sites: {},
                baseUrl: '',
                apiKey: ''
            };
            
            // 清空存储，包括connectionTested标记
            chrome.storage.sync.clear(() => {
                console.log('所有设置已清除');
                showStatus('所有设置已清除');
                
                // 清空站点列表
                sitesListDiv.innerHTML = '<div class="help-text">请先配置服务器地址和API密钥</div>';
            });
        }
    }

    // 添加事件监听器
    testConnectionBtn.addEventListener('click', testConnection);
    clearSettingsBtn.addEventListener('click', clearSettings);
    addSiteBtn.addEventListener('click', addSite);
    exportConfigBtn.addEventListener('click', exportConfig);
    importConfigBtn.addEventListener('click', importConfig);
    importFileInput.addEventListener('change', handleImportFile);

    // 添加图标URL获取按钮事件监听
    document.getElementById('fetchIconButton').addEventListener('click', function() {
        const iconUrl = document.getElementById('iconUrl').value.trim();
        if (iconUrl) {
            fetchAndSetIconFromUrl(iconUrl);
        } else {
            showStatus('请输入有效的图标URL', true);
        }
    });

    // 检查更新
    async function checkForUpdates() {
        try {
            const response = await fetch('https://api.github.com/repos/madrays/MoviePilot-Plugins/releases/latest');
            if (!response.ok) {
                console.error('获取版本信息失败:', response.statusText);
                return;
            }
            
            const releaseInfo = await response.json();
            const latestVersion = releaseInfo.tag_name;
            
            // 从release名称中解析版本号
            if (latestVersion) {
                const cleanLatestVersion = latestVersion.replace(/^v/, '');
                console.log('最新版本:', cleanLatestVersion, '当前版本:', CURRENT_VERSION);
                
                // 检查是否有更新（简单的字符串比较，假设版本号格式为x.y.z）
                if (isNewerVersion(cleanLatestVersion, CURRENT_VERSION)) {
                    // 显示更新通知
                    showUpdateNotice(cleanLatestVersion);
                }
            }
        } catch (error) {
            console.error('检查更新失败:', error);
            
            // 尝试备用方案：解析压缩包名称来检查版本
            fallbackVersionCheck();
        }
    }
    
    // 备用方案：解析压缩包名称来检查版本
    function fallbackVersionCheck() {
        try {
            // 尝试通过备用方式获取版本信息 - 解析zip文件名
            fetch('https://api.github.com/repos/madrays/MoviePilot-Plugins/releases')
                .then(response => response.json())
                .then(releases => {
                    if (releases && releases.length > 0) {
                        // 过滤出TOTP相关的资产
                        for (const release of releases) {
                            const totpAssets = release.assets.filter(asset => 
                                asset.name.toLowerCase().includes('totp') && 
                                asset.name.endsWith('.zip'));
                            
                            if (totpAssets.length > 0) {
                                // 从文件名中提取版本信息
                                const fileName = totpAssets[0].name;
                                const versionMatch = fileName.match(/[vV]?(\d+\.\d+\.\d+)/);
                                
                                if (versionMatch && versionMatch[1]) {
                                    const zipVersion = versionMatch[1];
                                    console.log('从ZIP文件名中检测到版本:', zipVersion);
                                    
                                    if (isNewerVersion(zipVersion, CURRENT_VERSION)) {
                                        showUpdateNotice(zipVersion);
                                    }
                                    return;
                                }
                                
                                // 如果没有找到版本号，但找到了新的ZIP文件
                                const createdAt = new Date(totpAssets[0].created_at);
                                const nowMinus30Days = new Date();
                                nowMinus30Days.setDate(nowMinus30Days.getDate() - 30);
                                
                                // 如果文件是最近30天创建的，则认为有更新
                                if (createdAt > nowMinus30Days) {
                                    showUpdateWithoutVersion();
                                }
                            }
                        }
                    }
                })
                .catch(error => {
                    console.error('获取发布资产失败:', error);
                    tryManifestCheck();
                });
        } catch (error) {
            console.error('备用版本检查失败:', error);
            tryManifestCheck();
        }
    }
    
    // 尝试从manifest.json获取版本信息
    function tryManifestCheck() {
        try {
            // 尝试获取插件的版本信息
            chrome.runtime.getPackageDirectoryEntry(function(root) {
                root.getFile('manifest.json', {}, function(fileEntry) {
                    fileEntry.file(function(file) {
                        const reader = new FileReader();
                        reader.onloadend = function(e) {
                            const manifest = JSON.parse(this.result);
                            const manifestVersion = manifest.version;
                            
                            // 如果当前版本与manifest版本不同，可能是更新了
                            if (manifestVersion && manifestVersion !== CURRENT_VERSION) {
                                showUpdateNotice(manifestVersion);
                            }
                        };
                        reader.readAsText(file);
                    });
                });
            });
        } catch (error) {
            console.error('清单文件版本检查失败:', error);
        }
    }
    
    // 显示有更新但没有具体版本号的通知
    function showUpdateWithoutVersion() {
        const updateNotice = document.getElementById('updateNotice');
        if (updateNotice) {
            updateNotice.textContent = `发现新版本`;
            updateNotice.style.display = 'inline-block';
            
            // 在状态区域也显示通知
            showStatus(`TOTP助手有新版本可用，点击右上角更新按钮了解详情`, false);
        }
    }
    
    // 比较版本号
    function isNewerVersion(latest, current) {
        const latestParts = latest.split('.').map(Number);
        const currentParts = current.split('.').map(Number);
        
        for (let i = 0; i < Math.max(latestParts.length, currentParts.length); i++) {
            const latestPart = latestParts[i] || 0;
            const currentPart = currentParts[i] || 0;
            
            if (latestPart > currentPart) {
                return true;
            } else if (latestPart < currentPart) {
                return false;
            }
        }
        
        return false; // 版本相同
    }
    
    // 显示更新通知
    function showUpdateNotice(newVersion) {
        const updateNotice = document.getElementById('updateNotice');
        if (updateNotice) {
            updateNotice.textContent = `发现新版本 v${newVersion}`;
            updateNotice.style.display = 'inline-block';
            
            // 在状态区域也显示通知
            showStatus(`TOTP助手有新版本 v${newVersion} 可用，点击右上角更新按钮了解详情`, false);
            
            // 存储新版本信息
            chrome.storage.sync.set({ 'latestVersion': newVersion });
        }
    }
});

// 保存API配置
async function saveApiConfig(baseUrl, apiKey) {
  return new Promise((resolve, reject) => {
    try {
      // 使用chrome.storage.sync代替local
      chrome.storage.sync.set({
        apiBaseUrl: baseUrl,
        apiKey: apiKey
      }, () => {
        console.log('API配置已保存');
        resolve();
      });
    } catch (error) {
      console.error('保存API配置失败:', error);
      reject(error);
    }
  });
}

// 加载API配置
async function loadApiConfig() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['apiBaseUrl', 'apiKey'], (result) => {
      if (result.apiBaseUrl && result.apiKey) {
        resolve({
          baseUrl: result.apiBaseUrl,
          apiKey: result.apiKey
        });
      } else {
        resolve(null);
      }
    });
  });
}

// 更新站点列表
async function updateSitesList(updatedSites) {
    try {
        const config = await loadApiConfig();
        if (!config || !config.baseUrl || !config.apiKey) {
            console.log('未配置API连接信息，无法更新站点列表');
            return;
        }
        
        showStatus('正在更新站点列表...');
        
        // 直接调用API更新配置
        const response = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/update_config?apikey=${config.apiKey}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(updatedSites)
        });
        
        if (!response.ok) {
            throw new Error(`服务器返回错误 (${response.status}): ${response.statusText}`);
        }
        
        const data = await response.json();
        
        // 检查返回数据格式
        if (data.code === 0 || data.code === undefined || data.success === true) {
            showStatus('站点列表已更新');
            return true;
        } else {
            throw new Error(data.message || '未知错误');
        }
    } catch (error) {
        console.error('更新站点列表失败:', error);
        showStatus(`更新站点列表失败: ${error.message}`, true);
        return false;
    }
}

// 添加直接从URL获取图标的功能
function fetchAndSetIconFromUrl(url) {
    if (!url) return;
    
    // 显示加载状态
    const fetchButton = document.getElementById('fetchIconButton');
    const originalText = fetchButton.textContent;
    fetchButton.textContent = '获取中...';
    fetchButton.disabled = true;
    
    const img = new Image();
    img.crossOrigin = 'Anonymous';
    
    img.onload = function() {
        try {
            // 创建canvas来调整和压缩图像
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            
            // 设置画布大小为32x32（最佳图标尺寸）
            canvas.width = 32;
            canvas.height = 32;
            
            // 绘制并调整图像大小
            ctx.drawImage(img, 0, 0, 32, 32);
            
            // 转换为base64
            const base64 = canvas.toDataURL('image/png');
            
            // 更新预览
            const iconPreview = document.getElementById('iconPreview');
            iconPreview.innerHTML = '';
            const iconImg = document.createElement('img');
            iconImg.src = base64;
            iconPreview.appendChild(iconImg);
            
            // 显示移除按钮
            document.getElementById('removeIconButton').style.display = 'inline-block';
            
            // 存储base64图标
            currentIconDataUrl = base64;
            
            showStatus('图标已成功获取并压缩', false);
        } catch (error) {
            console.error('处理图标时出错:', error);
            showStatus('处理图标时出错: ' + error.message, true);
        } finally {
            // 恢复按钮状态
            fetchButton.textContent = originalText;
            fetchButton.disabled = false;
        }
    };
    
    img.onerror = function() {
        console.error('无法加载图标URL:', url);
        showStatus('无法加载图标，请检查URL是否有效', true);
        fetchButton.textContent = originalText;
        fetchButton.disabled = false;
    };
    
    img.src = url;
}
