// 获取UI元素
document.addEventListener('DOMContentLoaded', function() {
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
    
    // 添加修复按钮
    const fixConnectionBtn = document.createElement('button');
    fixConnectionBtn.id = 'fixConnection';
    fixConnectionBtn.textContent = '修复连接问题';
    fixConnectionBtn.style.marginLeft = '10px';
    fixConnectionBtn.style.backgroundColor = '#ff9800';
    
    // 将修复按钮添加到测试连接按钮旁边
    testConnectionBtn.parentNode.insertBefore(fixConnectionBtn, testConnectionBtn.nextSibling);

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
        testConnectionBtn: !!testConnectionBtn,
        fixConnectionBtn: !!fixConnectionBtn
    });

    // 存储当前配置
    let currentConfig = {
        sites: {},
        baseUrl: '',
        apiKey: ''
    };

    // 初始化
    loadConfig();
    
    // 修复连接按钮点击事件
    fixConnectionBtn.addEventListener('click', fixConnection);
    
    // 修复连接函数
    async function fixConnection() {
        try {
            showStatus('正在修复连接问题...');
            
            // 获取当前配置
            const baseUrl = baseUrlInput.value.trim();
            const apiKey = apiKeyInput.value.trim();
            
            if (!baseUrl || !apiKey) {
                showStatus('请先输入服务器地址和API密钥', true);
                return;
            }
            
            // 强制重置后台的配置
            const result = await new Promise(resolve => {
                chrome.runtime.sendMessage(
                    { 
                        action: 'resetApiConfig',
                        config: {
                            baseUrl: normalizeUrl(baseUrl),
                            apiKey: apiKey
                        }
                    },
                    resolve
                );
            });
            
            if (result && result.success) {
                showStatus('连接问题已修复，请尝试刷新插件页面');
                
                // 保存配置到本地存储
                currentConfig.baseUrl = normalizeUrl(baseUrl);
                currentConfig.apiKey = apiKey;
                saveConfig();
                
                // 延迟2秒后刷新站点列表
                setTimeout(() => {
                    refreshSitesList();
                }, 2000);
            } else {
                showStatus('修复失败: ' + (result ? result.message : '未知错误'), true);
            }
        } catch (error) {
            console.error('修复连接失败:', error);
            showStatus('修复失败: ' + error.message, true);
        }
    }
    
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
        console.log('渲染站点列表, 传入数据:', sites);
        
        // 获取站点列表容器 - 兼容两种可能的ID
        const sitesListDiv = document.getElementById('sites-list') || document.getElementById('sitesList');
        console.log('站点列表容器元素:', sitesListDiv);
        
        if (!sitesListDiv) {
            console.error('找不到站点列表容器元素');
                return;
            }
            
        // 清空站点列表
        sitesListDiv.innerHTML = '';
            
            if (!sites || Object.keys(sites).length === 0) {
                sitesListDiv.innerHTML = '<div class="help-text">暂无配置的站点</div>';
                return;
            }
            
            // 显示站点总数
            const totalSites = Object.keys(sites).length;
        console.log(`渲染 ${totalSites} 个站点`);
        
            const siteCountInfo = document.createElement('div');
            siteCountInfo.className = 'site-count-info';
            siteCountInfo.innerHTML = `当前已配置 <strong>${totalSites}</strong> 个站点`;
            sitesListDiv.appendChild(siteCountInfo);
        
        // 添加排序功能
        const sortContainer = document.createElement('div');
        sortContainer.className = 'sort-container';
        sortContainer.style.marginBottom = '15px';
        sortContainer.style.display = 'flex';
        sortContainer.style.justifyContent = 'flex-end';
        sortContainer.style.alignItems = 'center';
        
        const sortLabel = document.createElement('span');
        sortLabel.textContent = '排序: ';
        sortLabel.style.marginRight = '8px';
        sortLabel.style.fontSize = '14px';
        sortContainer.appendChild(sortLabel);
        
        const sortSelect = document.createElement('select');
        sortSelect.id = 'sort-select';
        sortSelect.style.padding = '4px 8px';
        sortSelect.style.borderRadius = '4px';
        sortSelect.style.border = '1px solid #ddd';
        
        const sortOptions = [
            { value: 'default', text: '默认顺序' },
            { value: 'name-asc', text: '名称 (A-Z)' },
            { value: 'name-desc', text: '名称 (Z-A)' }
        ];
        
        sortOptions.forEach(option => {
            const optElement = document.createElement('option');
            optElement.value = option.value;
            optElement.textContent = option.text;
            sortSelect.appendChild(optElement);
        });
        
        sortSelect.addEventListener('change', () => {
            renderSites(sites, sortSelect.value);
        });
        
        sortContainer.appendChild(sortSelect);
        sitesListDiv.appendChild(sortContainer);
        
        // 添加拖拽排序提示
        const dragSortInfo = document.createElement('div');
        dragSortInfo.className = 'drag-sort-info';
        dragSortInfo.style.padding = '8px';
        dragSortInfo.style.marginBottom = '15px';
        dragSortInfo.style.backgroundColor = '#e3f2fd';
        dragSortInfo.style.borderRadius = '4px';
        dragSortInfo.style.fontSize = '14px';
        dragSortInfo.textContent = '提示: 您可以通过拖拽卡片来自定义排序顺序';
        sitesListDiv.appendChild(dragSortInfo);
        
        // 创建站点卡片容器
        const sitesContainer = document.createElement('div');
        sitesContainer.id = 'sites-container';
        sitesContainer.style.marginTop = '10px';
        sitesListDiv.appendChild(sitesContainer);
        
        // 渲染站点
        renderSites(sites, 'default');
        
        // 启用拖拽排序
        enableDragSort(sitesContainer);
    }
    
    // 渲染站点列表
    function renderSites(sites, sortOrder) {
        const sitesContainer = document.getElementById('sites-container');
        if (!sitesContainer) return;
        
        // 清空容器
        sitesContainer.innerHTML = '';
        
        // 按照指定顺序排序站点
        let siteEntries = Object.entries(sites);
        
        switch (sortOrder) {
            case 'name-asc':
                siteEntries.sort((a, b) => a[0].localeCompare(b[0]));
                break;
            case 'name-desc':
                siteEntries.sort((a, b) => b[0].localeCompare(a[0]));
                break;
            case 'default':
            default:
                // 保持当前配置的顺序
                // 不做任何排序操作，使用原始顺序
                break;
        }
        
        console.log('排序后的站点顺序:', siteEntries.map(entry => entry[0]));
            
            // 创建站点卡片
        siteEntries.forEach(([siteName, data], index) => {
                const card = document.createElement('div');
                card.className = 'card';
            card.dataset.siteName = siteName;
            card.dataset.sortIndex = index;
            card.draggable = true;
            
            // 添加拖动手柄
            const dragHandle = document.createElement('div');
            dragHandle.className = 'drag-handle';
            dragHandle.innerHTML = '&#9776;'; // Unicode for "三" (menu/grip icon)
            dragHandle.style.cursor = 'move';
            dragHandle.style.color = '#999';
            dragHandle.style.position = 'absolute';
            dragHandle.style.top = '10px';
            dragHandle.style.left = '10px';
            card.appendChild(dragHandle);
                
                // 站点名称行 - 包含图标和名称
                const titleRow = document.createElement('div');
                titleRow.className = 'title-row';
                titleRow.style.display = 'flex';
                titleRow.style.alignItems = 'center';
                titleRow.style.marginBottom = '10px';
            titleRow.style.paddingLeft = '25px'; // 为拖动手柄留出空间
                
                // 站点图标（如果有）
                if (data.icon) {
                    const iconImg = document.createElement('img');
                    iconImg.src = data.icon;
                    iconImg.alt = `${siteName} 图标`;
                    iconImg.className = 'site-icon';
                    iconImg.style.width = '24px';
                    iconImg.style.height = '24px';
                    iconImg.style.marginRight = '8px';
                    iconImg.style.borderRadius = '4px';
                    titleRow.appendChild(iconImg);
                } else {
                    // 占位图标
                    const iconPlaceholder = document.createElement('div');
                    iconPlaceholder.className = 'icon-placeholder';
                    iconPlaceholder.style.width = '24px';
                    iconPlaceholder.style.height = '24px';
                    iconPlaceholder.style.backgroundColor = '#ddd';
                    iconPlaceholder.style.marginRight = '8px';
                    iconPlaceholder.style.borderRadius = '4px';
                    iconPlaceholder.style.display = 'flex';
                    iconPlaceholder.style.alignItems = 'center';
                    iconPlaceholder.style.justifyContent = 'center';
                    iconPlaceholder.textContent = siteName.charAt(0).toUpperCase();
                    titleRow.appendChild(iconPlaceholder);
                }
                
                // 站点名称
                const title = document.createElement('h3');
                title.textContent = siteName;
                title.style.margin = '0';
                title.style.flex = '1';
                titleRow.appendChild(title);
                
                card.appendChild(titleRow);
                
                // 密钥 (隐藏实际值)
                const secret = document.createElement('div');
                secret.className = 'site-secret';
                secret.textContent = `密钥: ${data.secret.substring(0, 3)}****${data.secret.substring(data.secret.length - 3)}`;
                card.appendChild(secret);
                
                // URLs
                if (data.urls && data.urls.length > 0) {
                    const urlsContainer = document.createElement('div');
                    urlsContainer.className = 'site-urls';
                    urlsContainer.innerHTML = '<strong>URLs:</strong>';
                    
                    const urlsList = document.createElement('ul');
                    data.urls.forEach(url => {
                        const li = document.createElement('li');
                        li.textContent = url;
                        urlsList.appendChild(li);
                    });
                    
                    urlsContainer.appendChild(urlsList);
                    card.appendChild(urlsContainer);
                }
                
                // 按钮容器
                const buttonContainer = document.createElement('div');
                buttonContainer.className = 'site-buttons';
                buttonContainer.style.display = 'flex';
                buttonContainer.style.justifyContent = 'flex-end';
                buttonContainer.style.marginTop = '10px';
                buttonContainer.style.gap = '8px';
                
                // 编辑按钮
                const editBtn = document.createElement('button');
                editBtn.className = 'edit-btn';
                editBtn.textContent = '编辑';
                editBtn.style.backgroundColor = '#1976d2';
                editBtn.style.color = 'white';
                editBtn.style.padding = '4px 8px';
                editBtn.style.fontSize = '12px';
                editBtn.dataset.site = siteName;
                editBtn.addEventListener('click', () => editSite(siteName));
                buttonContainer.appendChild(editBtn);
                
                // 删除按钮
                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'delete-btn';
                deleteBtn.textContent = '删除';
                deleteBtn.dataset.site = siteName;
                deleteBtn.addEventListener('click', () => deleteSite(siteName));
                buttonContainer.appendChild(deleteBtn);
                
                card.appendChild(buttonContainer);
                
            sitesContainer.appendChild(card);
        });
    }
    
    // 启用拖拽排序
    function enableDragSort(container) {
        let draggedItem = null;
        
        // 添加拖拽事件监听器
        container.addEventListener('dragstart', function(e) {
            draggedItem = e.target;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', ''); // 必须设置一些数据才能拖拽
            setTimeout(() => {
                draggedItem.style.opacity = '0.5';
            }, 0);
        });
        
        container.addEventListener('dragend', function(e) {
            if (draggedItem) {
                draggedItem.style.opacity = '1';
                draggedItem = null;
            }
        });
        
        container.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
        });
        
        container.addEventListener('dragenter', function(e) {
            e.preventDefault();
            const target = e.target.closest('.card');
            if (target && target !== draggedItem) {
                target.style.borderTop = '2px solid #1976d2';
            }
        });
        
        container.addEventListener('dragleave', function(e) {
            const target = e.target.closest('.card');
            if (target) {
                target.style.borderTop = '';
            }
        });
        
        container.addEventListener('drop', async function(e) {
            e.preventDefault();
            const dropTarget = e.target.closest('.card');
            
            if (dropTarget && draggedItem && dropTarget !== draggedItem) {
                // 清除所有卡片的边框样式
                const cards = container.querySelectorAll('.card');
                cards.forEach(card => card.style.borderTop = '');
                
                // 获取所有卡片元素
                const cardElements = Array.from(container.querySelectorAll('.card'));
                
                // 找到目标位置
                const dropIndex = cardElements.indexOf(dropTarget);
                const dragIndex = cardElements.indexOf(draggedItem);
                
                // 移动元素
                if (dragIndex < dropIndex) {
                    container.insertBefore(draggedItem, dropTarget.nextSibling);
                } else {
                    container.insertBefore(draggedItem, dropTarget);
                }
                
                // 更新卡片的排序指数
                cardElements.forEach((card, index) => {
                    card.dataset.sortIndex = index;
                });
                
                // 保存新的排序顺序
                await saveCustomOrder();
            }
        });
    }
    
    // 保存自定义排序
    async function saveCustomOrder() {
        try {
            // 获取当前排序
            const sitesContainer = document.getElementById('sites-container');
            const cards = Array.from(sitesContainer.querySelectorAll('.card'));
            
            // 创建有序的站点对象 - 使用ES2015+的对象属性顺序特性
            const orderedSites = {};
            
            // 按照DOM中的顺序遍历卡片，创建新的有序对象
            cards.forEach((card) => {
                const siteName = card.dataset.siteName;
                if (siteName && currentConfig.sites[siteName]) {
                    // 复制原始站点数据，保持顺序
                    orderedSites[siteName] = {...currentConfig.sites[siteName]};
                }
            });
            
            console.log('保存的排序顺序:', Object.keys(orderedSites));
            
            // 获取API配置
            const config = await loadApiConfig();
            if (!config || !config.baseUrl || !config.apiKey) {
                throw new Error('未配置API连接信息，无法保存排序');
            }
            
            console.log('正在保存自定义排序...');
            showStatus('正在保存排序...');
            
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
            const isUpdate = !!sites[siteName];
            
            // 保存或更新站点
            if (isUpdate) {
                // 如果是更新，保持原有站点属性，只更新需要修改的内容
            sites[siteName] = {
                    ...sites[siteName],
                secret: secret,
                urls: urls,
                    icon: currentIconDataUrl || sites[siteName].icon
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
            const addSiteHeading = Array.from(document.querySelectorAll('h2')).find(h => h.textContent.includes('添加站点'));
            if (addSiteHeading) {
                addSiteHeading.scrollIntoView({ behavior: 'smooth' });
            }
            
            // 聚焦到第一个输入框
            siteNameInput.focus();
            
            showStatus(`正在编辑站点 ${siteName}`);
        } catch (error) {
            console.error('编辑站点失败:', error);
            showStatus(`编辑站点失败: ${error.message}`, true);
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
