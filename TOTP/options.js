// 获取UI元素
document.addEventListener('DOMContentLoaded', function() {
    // 版本信息
    const CURRENT_VERSION = '1.2';
    const versionElement = document.getElementById('currentVersion');
    const updateNotice = document.getElementById('updateNotice');
    
    // 图标标签切换功能
    const iconTabs = document.querySelectorAll('.icon-tab');
    const iconPanels = document.querySelectorAll('.icon-panel');
    
    iconTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // 移除所有标签的活动状态
            iconTabs.forEach(t => t.classList.remove('active'));
            // 隐藏所有面板
            iconPanels.forEach(p => p.classList.remove('active'));
            
            // 激活当前标签
            tab.classList.add('active');
            
            // 显示对应面板
            const tabId = tab.getAttribute('data-tab');
            document.getElementById(`${tabId}-panel`).classList.add('active');
        });
    });
    
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
    const useLetterIconButton = document.getElementById('useLetterIconButton');
    const iconSourceText = document.getElementById('iconSourceText');
    
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

    // 图标来源显示
    function updateIconSourceText() {
        if (!iconSourceText) return;
        
        let sourceText = '';
        switch(iconSource.type) {
            case 'letter':
                sourceText = '首字母图标';
                break;
            case 'favicon':
                sourceText = '网站图标';
                break;
            case 'url':
                sourceText = '链接图标';
                break;
            case 'upload':
                sourceText = '本地上传';
                break;
            case 'none':
                sourceText = '未设置';
                break;
            default:
                sourceText = '自定义图标';
        }
        
        iconSourceText.textContent = sourceText;
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
            iconSource = { type: 'none', url: null };
            updateIconPreview();
            updateIconSourceText();
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
    
    // 使用字母图标按钮点击事件
    if (useLetterIconButton) {
        useLetterIconButton.addEventListener('click', function() {
            const siteName = siteNameInput.value.trim();
            if (siteName) {
                useLetterIcon(siteName);
            } else {
                showStatus('请先输入站点名称', true);
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
    
    // 全局变量，用于跟踪图标来源
    let iconSource = {
        type: 'none', // 'none', 'letter', 'favicon', 'url', 'upload'
        url: null
    };

    // 自动获取图标
    function autoFetchIcon(url) {
        if (!url) return;
        
        const iconPreview = document.getElementById('iconPreview');
        if (!iconPreview) return;
        
        try {
            // 切换到自动获取图标模式
            iconSource = { type: 'favicon', url: url };
            
            // 显示正在获取图标
            iconPreview.innerHTML = '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;"><span style="font-size:10px;">加载中</span></div>';
            
            // 提取域名
            let domain = url;
            try {
                domain = new URL(url).hostname;
        } catch (e) {
                console.error('无法解析URL:', e);
                showStatus('无效的URL格式', true);
                // 如果无法解析URL，切换到字母图标
                useLetterIcon(urlsTextarea.value);
                return;
            }
            
            // 首先尝试直接获取网站的favicon
            let faviconUrl = `https://${domain}/favicon.ico`;
            
            // 创建图像元素
            const img = new Image();
            
            // 图像加载成功回调
            img.onload = function() {
                try {
                    // 创建canvas元素
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    canvas.width = img.width;
                    canvas.height = img.height;
                    
                    // 将图像绘制到canvas上
                    ctx.drawImage(img, 0, 0);
                    
                    // 将canvas内容转换为DataURL
                    currentIconDataUrl = canvas.toDataURL('image/png');
                    updateIconPreview();
                    console.log('自动获取图标成功');
                    
                    // 更新状态显示
                    showStatus('成功获取网站图标', false);
                    
                    // 更新图标来源
                    iconSource = { type: 'favicon', url: faviconUrl };
                } catch (e) {
                    console.error('转换图标格式失败:', e);
                    showStatus('图标处理失败，将使用首字母显示', true);
                    
                    // 如果处理失败，使用字母图标
                    useLetterIcon(siteName.value);
                }
            };
            
            // 图像加载失败回调
            img.onerror = function() {
                console.error('无法直接加载favicon，使用字母图标');
                showStatus('无法获取网站图标，将使用首字母显示', true);
                
                // 如果获取失败，使用字母图标
                useLetterIcon(siteName.value);
            };
            
            // 设置跨域属性并加载图像
            img.crossOrigin = 'Anonymous';
            img.src = faviconUrl;
            
        } catch (error) {
            console.error('自动获取图标失败:', error);
            showStatus('图标获取失败，将使用首字母显示', true);
            iconPreview.innerHTML = '';
            
            // 如果出现异常，使用字母图标
            useLetterIcon(siteName.value);
        }
    }
    
    // 使用URL获取图标
    function fetchAndSetIconFromUrl(url) {
        if (!url) {
            showStatus('请输入有效的图标URL', true);
            return;
        }
        
        // 显示加载状态
        const fetchButton = document.getElementById('fetchIconButton');
        const originalText = fetchButton.textContent;
        fetchButton.textContent = '获取中...';
        fetchButton.disabled = true;
        
        // 切换到URL获取图标模式
        iconSource = { type: 'url', url: url };
        
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
                
                // 更新图标数据
                currentIconDataUrl = base64;
                
                // 更新预览
                updateIconPreview();
                
                showStatus('图标已成功获取并压缩', false);
            } catch (error) {
                console.error('处理图标时出错:', error);
                showStatus('处理图标时出错: ' + error.message, true);
                
                // 如果处理失败，使用字母图标
                useLetterIcon(siteName.value);
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
            
            // 如果获取失败，使用字母图标
            useLetterIcon(siteName.value);
        };
        
        img.src = url;
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
        
        // 切换到本地上传图标模式
        iconSource = { type: 'upload', url: null };
        
        // 读取文件为DataURL
        const reader = new FileReader();
        reader.onload = function(e) {
            currentIconDataUrl = e.target.result;
            updateIconPreview();
            showStatus('本地图标已上传', false);
        };
        reader.readAsDataURL(file);
    }

    // 使用字母图标（缺省方式）
    function useLetterIcon(siteName) {
        if (!siteName) {
            siteName = document.getElementById('siteName').value.trim();
        }
        
        if (!siteName) {
            currentIconDataUrl = null;
            updateIconPreview();
            return;
        }
        
        // 切换到字母图标模式
        iconSource = { type: 'letter', url: null };
        
        // 生成颜色（基于站点名的哈希）
        const colorHash = getHashColor(siteName);
        
        // 创建Canvas
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 32;
        canvas.height = 32;
        
        // 绘制背景
        ctx.fillStyle = colorHash;
        ctx.fillRect(0, 0, 32, 32);
        
        // 绘制文字
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 20px Arial';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(siteName.charAt(0).toUpperCase(), 16, 16);
        
        // 生成dataURL
        currentIconDataUrl = canvas.toDataURL('image/png');
        updateIconPreview();
        
        showStatus('使用首字母作为图标', false);
    }

    // 从字符串生成颜色哈希
    function getHashColor(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            hash = str.charCodeAt(i) + ((hash << 5) - hash);
        }
        
        const colors = [
            '#3498db', '#2ecc71', '#e74c3c', '#f39c12',
            '#9b59b6', '#1abc9c', '#d35400', '#34495e',
            '#16a085', '#27ae60', '#2980b9', '#8e44ad',
            '#c0392b', '#f1c40f'
        ];
        
        // 使用哈希选择颜色
        return colors[Math.abs(hash) % colors.length];
    }

    // 更新图标预览
    function updateIconPreview() {
        const iconPreview = document.getElementById('iconPreview');
        if (!iconPreview) return;

        if (currentIconDataUrl) {
            // 显示图标预览
            iconPreview.innerHTML = `<img src="${currentIconDataUrl}" alt="站点图标">`;
            
            // 显示移除按钮
            const removeButton = document.getElementById('removeIconButton');
            if (removeButton) {
                removeButton.style.display = 'block';
            }
        } else {
            // 清空预览
            iconPreview.innerHTML = '';
            // 隐藏移除按钮
            const removeButton = document.getElementById('removeIconButton');
            if (removeButton) {
                removeButton.style.display = 'none';
            }
        }
        
        // 更新图标来源显示
        updateIconSourceText();
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
                
                // 加载完成后检查HTTP警告
                checkHttpWarning(currentConfig.baseUrl);
                
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
                
                // 加载完成后检查HTTP警告
                checkHttpWarning(currentConfig.baseUrl);
                
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
        console.log('开始刷新站点列表...');
        
        try {
            // 1. 首先尝试从API获取最新配置（如果已设置API连接信息）
            let sites = {};
            
            if (currentConfig.baseUrl && currentConfig.apiKey) {
                // 从API获取最新数据
                console.log('获取API配置结果:', currentConfig);
                const apiUrl = `${currentConfig.baseUrl}/api/v1/plugin/twofahelper/config?apikey=${currentConfig.apiKey}`;
                console.log('请求站点列表URL:', apiUrl);
                
                try {
                    const response = await fetch(apiUrl);
                    console.log('获取配置响应状态:', response.status, response.statusText);
                    
                    if (response.ok) {
                        const result = await response.json();
                        console.log('API返回的原始响应数据:', result);
                        
                        // 根据API实现，正确的响应结构应该是：
                        // { success: true, message: "获取成功", data: { ... } }
                        if (result.success && result.data) {
                            // 最常见的标准格式
                            sites = result.data;
                            // 更新内存中的配置
                            currentConfig.sites = sites;
                            console.log('获取到的站点数据(success格式):', sites);
                        } else if (result.code === 0 && result.data) {
                            // 兼容code格式
                            sites = result.data;
                            // 更新内存中的配置
                            currentConfig.sites = sites;
                            console.log('获取到的站点数据(code格式):', sites);
                        } else if (typeof result === 'object' && Object.keys(result).length > 0) {
                            // 如果直接返回了配置对象
                            sites = result;
                            // 更新内存中的配置
                            currentConfig.sites = sites;
                            console.log('获取到的站点数据(直接对象):', sites);
                        }
                    } else {
                        console.error('请求失败，状态码:', response.status, response.statusText);
                    }
                } catch (error) {
                    console.log('从API获取配置失败:', error);
                }
            }
            
            // 2. 如果API未能获取数据（或未设置API），则从存储中读取
            if (Object.keys(sites).length === 0) {
                sites = currentConfig.sites || {};
                
                // 如果内存中也没有，尝试从存储中读取
                if (Object.keys(sites).length === 0) {
                    const data = await new Promise(resolve => {
                        chrome.storage.sync.get(['sites', 'icons_in_local'], resolve);
                    });
                    
                    // 获取基本配置
                    const basicConfig = data.sites || {};
                    
                    // 检查图标是否存储在local
                    if (data.icons_in_local) {
                        // 从local存储获取图标
                        const iconKeysToFetch = Object.keys(basicConfig).map(siteName => `icon_${siteName}`);
                        
                        if (iconKeysToFetch.length > 0) {
                            const iconData = await new Promise(resolve => {
                                chrome.storage.local.get(iconKeysToFetch, resolve);
                            });
                            
                            // 合并基本配置和图标
                            sites = {};
                            for (const [siteName, siteConfig] of Object.entries(basicConfig)) {
                                sites[siteName] = {
                                    ...siteConfig,
                                    icon: iconData[`icon_${siteName}`] || '' // 添加图标如果存在
                                };
                            }
                        } else {
                            sites = basicConfig;
                        }
                    } else {
                        // 旧数据格式，直接使用
                        sites = basicConfig;
                    }
                    
                    // 更新内存中的配置
                    currentConfig.sites = sites;
                }
            }
            
            // 更新站点数量显示
            const sitesCount = Object.keys(sites).length;
            const sitesCountElement = document.getElementById('sitesCount');
            if (sitesCountElement) {
                sitesCountElement.textContent = `${sitesCount}个站点`;
            }
            
            console.log('开始渲染站点列表, 站点数量:', sitesCount);
            
            // 清空站点列表容器
        sitesListDiv.innerHTML = '';
        
            if (sitesCount === 0) {
                sitesListDiv.innerHTML = '<div class="help-text">尚未配置任何站点，请添加或导入配置</div>';
            return;
        }
        
            // 创建站点卡片
            for (const [siteName, siteData] of Object.entries(sites)) {
            const card = document.createElement('div');
                card.className = 'site-card';
                card.dataset.siteName = siteName;
                card.draggable = true; // 设置为可拖拽
                
                // 站点头部：图标和名称
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
                
                // 图标容器
                const iconContainer = document.createElement('div');
                iconContainer.className = 'site-icon-sm';
                
                // 如果有图标，显示图标；否则显示首字母
                if (siteData.icon) {
                    const img = document.createElement('img');
                    img.src = siteData.icon;
                    img.alt = siteName;
                    iconContainer.appendChild(img);
                } else {
                    // 显示首字母
                    iconContainer.textContent = siteName.charAt(0).toUpperCase();
                    iconContainer.style.backgroundColor = getColorForSite(siteName);
                    iconContainer.style.color = '#fff';
                    iconContainer.style.fontWeight = 'bold';
                    iconContainer.style.display = 'flex';
                    iconContainer.style.alignItems = 'center';
                    iconContainer.style.justifyContent = 'center';
                }
                
                header.appendChild(iconContainer);
                
                // 站点名称
                const name = document.createElement('div');
                name.className = 'site-name-sm';
                name.textContent = siteName;
                header.appendChild(name);
                
                card.appendChild(header);
                
                // URL（如果有）
                if (siteData.urls && siteData.urls.length > 0) {
                    const urls = document.createElement('div');
                    urls.className = 'site-urls-sm';
                    urls.textContent = siteData.urls[0] + (siteData.urls.length > 1 ? ` (+${siteData.urls.length - 1})` : '');
                    urls.style.color = '#666';
                    urls.style.fontSize = '12px';
                    urls.style.marginTop = '5px';
                    card.appendChild(urls);
                }
                
                // 操作按钮
                const actions = document.createElement('div');
                actions.className = 'site-actions';
                actions.style.marginTop = '10px';
                actions.style.display = 'flex';
                actions.style.justifyContent = 'space-between';
                
                // 编辑按钮
                const editButton = document.createElement('button');
                editButton.textContent = '编辑';
                editButton.style.backgroundColor = '#4CAF50';
                editButton.style.color = 'white';
                editButton.style.border = 'none';
                editButton.style.padding = '6px 15px';
                editButton.style.borderRadius = '4px';
                editButton.style.cursor = 'pointer';
                editButton.style.flex = '1';
                editButton.style.marginRight = '8px';
                editButton.onmouseover = function() { this.style.backgroundColor = '#45a049'; };
                editButton.onmouseout = function() { this.style.backgroundColor = '#4CAF50'; };
                editButton.onclick = function() { editSite(siteName); };
                actions.appendChild(editButton);
                
                // 删除按钮
                const deleteButton = document.createElement('button');
                deleteButton.textContent = '删除';
                deleteButton.style.backgroundColor = '#f44336';
                deleteButton.style.color = 'white';
                deleteButton.style.border = 'none';
                deleteButton.style.padding = '6px 15px';
                deleteButton.style.borderRadius = '4px';
                deleteButton.style.cursor = 'pointer';
                deleteButton.style.flex = '1';
                deleteButton.onmouseover = function() { this.style.backgroundColor = '#d32f2f'; };
                deleteButton.onmouseout = function() { this.style.backgroundColor = '#f44336'; };
                deleteButton.onclick = function() { deleteSite(siteName); };
                actions.appendChild(deleteButton);
                
                card.appendChild(actions);
                
                // 卡片样式美化
                card.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)';
                card.style.borderRadius = '8px';
                card.style.padding = '15px';
                card.style.margin = '10px 0';
                card.style.backgroundColor = '#fff';
                card.style.transition = 'transform 0.2s ease, box-shadow 0.2s ease';
                
                // 卡片悬停效果
                card.onmouseover = function() { 
                    this.style.boxShadow = '0 5px 15px rgba(0,0,0,0.15)';
                    this.style.transform = 'translateY(-2px)';
                };
                card.onmouseout = function() { 
                    this.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)';
                    this.style.transform = 'translateY(0)';
                };
                
                // 将卡片添加到列表
            sitesListDiv.appendChild(card);
            }
            
            // 启用拖拽排序
            enableDragSort(sitesListDiv);
            
            // 更新初始的自定义排序数组
            updateCustomOrderFromDOM();
            
            // 确保存在保存排序按钮
            if (sitesCount > 1) {
                const saveOrderBtn = document.getElementById('saveOrderBtn');
                if (!saveOrderBtn) {
                    createSaveOrderButton();
                } else {
                    // 刷新列表时隐藏保存按钮，等到用户拖动后再显示
                    saveOrderBtn.style.display = 'none';
                    saveOrderBtn.classList.remove('highlight');
                }
            }
            
        } catch (error) {
            console.error('刷新站点列表失败:', error);
            sitesListDiv.innerHTML = `<div class="help-text error">加载站点列表失败: ${error.message}</div>`;
        }
    }
    
    // 渲染站点列表
    function renderSitesList(sites, sortOrder) {
        const container = document.getElementById('sitesList');
        container.innerHTML = '';
        
        // 更新站点计数
        const sitesCount = Object.keys(sites).length;
        document.getElementById('sitesCount').textContent = `${sitesCount}个站点`;
        
        if (sitesCount === 0) {
            container.innerHTML = '<div class="help-text">尚未配置任何站点。点击"添加站点"来开始。</div>';
                return;
            }
            
        // 如果未提供排序方式，默认使用自定义排序
        if (!sortOrder) {
            sortOrder = 'custom';
        }
        
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
                
                // 更新自定义排序数组，但不立即保存到服务器
                updateCustomOrderFromDOM();
                
                // 显示保存按钮提示用户手动保存
                const saveOrderBtn = document.getElementById('saveOrderBtn');
                if (saveOrderBtn) {
                    saveOrderBtn.style.display = 'block';
                    saveOrderBtn.classList.add('highlight');
                    // 3秒后移除高亮效果
                    setTimeout(() => {
                        saveOrderBtn.classList.remove('highlight');
                    }, 3000);
                } else {
                    // 如果按钮不存在，创建一个
                    createSaveOrderButton();
                }
                
                // 提示用户保存更改
                showStatus('排序已更新，请点击"保存排序"按钮保存更改');
                
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
            
            // 显示保存按钮提示用户手动保存
            const saveOrderBtn = document.getElementById('saveOrderBtn');
            if (saveOrderBtn) {
                saveOrderBtn.style.display = 'block';
                saveOrderBtn.classList.add('highlight');
                // 3秒后移除高亮效果
                setTimeout(() => {
                    saveOrderBtn.classList.remove('highlight');
                }, 3000);
            } else {
                // 如果按钮不存在，创建一个
                createSaveOrderButton();
            }
            
            // 提示用户保存更改
            showStatus('排序已更新，请点击"保存排序"按钮保存更改');
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
        // 防止短时间内多次点击
        const saveOrderBtn = document.getElementById('saveOrderBtn');
        if (saveOrderBtn) {
            if (saveOrderBtn.disabled) return;
            
            // 禁用按钮并显示加载状态
            const originalText = saveOrderBtn.textContent;
            saveOrderBtn.textContent = '保存中...';
            saveOrderBtn.disabled = true;
            saveOrderBtn.style.opacity = '0.7';
            saveOrderBtn.style.cursor = 'wait';
        }
        
        try {
            showStatus('正在更新站点排序，请稍候...', false, true);
            
            // 确保已更新自定义排序数组
            updateCustomOrderFromDOM();
            
            // 获取API配置
            const config = await loadApiConfig();
            if (!config || !config.baseUrl || !config.apiKey) {
                throw new Error('未配置API连接信息，无法保存排序');
            }
            
            console.log('正在保存自定义排序...');
            
            // 直接从服务器获取站点数据，确保有最新数据
            const response = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/config?apikey=${config.apiKey}`);
            if (!response.ok) {
                throw new Error(`获取配置失败 (${response.status}): ${response.statusText}`);
            }
            
            const data = await response.json();
            console.log('获取到的原始站点数据:', data);
            
            // 提取站点数据
            let sites;
            if (data.data) {
                sites = data.data;
            } else if (data.success && data.data) {
                sites = data.data;
            } else if (typeof data === 'object' && Object.keys(data).length > 0) {
                sites = data;
            } else {
                throw new Error('无法获取站点数据');
            }
            
            // 更新内存中的配置
            currentConfig.sites = sites;
            
            // 确保真的有站点数据
            if (!sites || Object.keys(sites).length === 0) {
                throw new Error('没有站点数据可供排序');
            }
            
            // 创建有序的站点对象
            const orderedSites = {};
            
            // 按照自定义顺序遍历站点名称
            customOrder.forEach(siteName => {
                if (sites[siteName]) {
                    orderedSites[siteName] = sites[siteName];
                }
            });
            
            // 确保所有原始站点都在有序对象中
            for (const siteName in sites) {
                if (!orderedSites[siteName]) {
                    orderedSites[siteName] = sites[siteName];
                }
            }
            
            console.log('将要保存的有序站点:', orderedSites);
            
            // 直接调用API更新配置
            showStatus('正在保存排序到服务器...', false, true);
            const updateResponse = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/update_config?apikey=${config.apiKey}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(orderedSites)
            });
            
            if (!updateResponse.ok) {
                throw new Error(`服务器返回错误 (${updateResponse.status}): ${updateResponse.statusText}`);
            }
            
            const updateData = await updateResponse.json();
            
            // 检查返回数据
            if (updateData.code === 0 || updateData.code === undefined || updateData.success === true) {
                // 更新内存中的配置
                currentConfig.sites = orderedSites;
                console.log('自定义排序已保存');
                
                // 隐藏保存按钮
                const saveOrderBtn = document.getElementById('saveOrderBtn');
                if (saveOrderBtn) {
                    saveOrderBtn.style.display = 'none';
                    saveOrderBtn.classList.remove('highlight');
                }
                
                showStatus('站点排序已保存');
                return true;
            } else {
                throw new Error(updateData.message || '服务器返回错误');
            }
        } catch (error) {
            console.error('保存排序失败:', error);
            showStatus(`保存排序失败: ${error.message}`, true);
            return false;
        } finally {
            // 恢复按钮状态
            const saveOrderBtn = document.getElementById('saveOrderBtn');
            if (saveOrderBtn) {
                saveOrderBtn.textContent = '保存排序';
                saveOrderBtn.disabled = false;
                saveOrderBtn.style.opacity = '1';
                saveOrderBtn.style.cursor = 'pointer';
            }
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
                
                // 检查是否是HTTP连接，并显示适当警告
                checkHttpWarning(baseUrl);
                
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

    // 根据站点名称生成一致的颜色
    function getColorForSite(siteName) {
        // 简单的字符串哈希算法
        let hash = 0;
        for (let i = 0; i < siteName.length; i++) {
            hash = siteName.charCodeAt(i) + ((hash << 5) - hash);
        }
        
        // 转换为HSL颜色，保持饱和度和亮度一致，只变化色相
        const hue = Math.abs(hash) % 360;
        return `hsl(${hue}, 65%, 55%)`;
    }

    // 删除站点
    async function deleteSite(siteName) {
        if (!confirm(`确定要删除站点 "${siteName}" 吗？此操作不可撤销。`)) {
            return;
        }
        
        try {
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
            console.log('开始编辑站点:', siteName);
            // 确保有站点数据
            if (!currentConfig.sites || !currentConfig.sites[siteName]) {
                showStatus(`站点 ${siteName} 不存在`, true);
            return;
        }
        
            // 获取站点数据
            const siteData = currentConfig.sites[siteName];
            console.log('获取到站点数据:', siteData);
            
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

    // 添加站点或更新站点
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
        
            // 如果没有图标，使用字母图标
            if (!currentIconDataUrl) {
                useLetterIcon(siteName);
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
            console.log("获取的原始配置数据:", data);
            
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
                    icon: currentIconDataUrl
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
            
            // 如果配置中已经有API连接信息，发送更新到后台
            if (currentConfig.baseUrl && currentConfig.apiKey) {
                try {
                    showStatus('正在同步配置到服务器...');
                    
                    // 直接调用API更新配置
                    const updateUrl = `${currentConfig.baseUrl}/api/v1/plugin/twofahelper/update_config?apikey=${currentConfig.apiKey}`;
                    console.log('调用更新配置API:', updateUrl);
                    const response = await fetch(updateUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json'
                        },
                        body: JSON.stringify(sites)
                    });
                    
                    if (!response.ok) {
                        throw new Error(`服务器返回错误 (${response.status}): ${response.statusText}`);
                    }
                    
                    const result = await response.json();
                    console.log('更新配置返回结果:', result);
                    
                    if (result.code === 0 || result.success === true) {
                        // 显示成功消息
                        showStatus(`导入成功，共 ${Object.keys(sites).length} 个站点已同步到服务器`);
                    } else {
                        throw new Error(result.message || '服务器返回错误');
                    }
                } catch (syncError) {
                    console.error('同步到服务器失败:', syncError);
                    showStatus(`导入成功，但同步到服务器失败: ${syncError.message}`, true);
                }
            } else {
                showStatus(`导入成功，共 ${Object.keys(sites).length} 个站点`);
            }
            
            // 更新内存中的配置
            currentConfig.sites = sites;
            
            // 清空输入
            siteNameInput.value = '';
            secretInput.value = '';
            urlsTextarea.value = '';
            currentIconDataUrl = null;
            iconSource = { type: 'none', url: null };
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
        } catch (error) {
            console.error('添加/更新站点失败:', error);
            showStatus(`添加/更新站点失败: ${error.message}`, true);
        }
    }

    // 导出配置
    async function exportConfig() {
        try {
            // 确保有配置数据可导出
            if (!currentConfig.sites || Object.keys(currentConfig.sites).length === 0) {
                showStatus('没有站点配置可导出', true);
                return;
            }
            
            // 检查是否需要从local存储中获取图标
            const data = await new Promise(resolve => {
                chrome.storage.sync.get(['sites', 'icons_in_local'], resolve);
            });
            
            let exportData = currentConfig.sites;
            
            // 如果图标存储在local存储中，合并数据
            if (data.icons_in_local) {
                const storedSites = data.sites || {};
                const siteNames = Object.keys(storedSites);
                
                if (siteNames.length > 0) {
                    // 获取local存储中的图标
                    const iconKeys = siteNames.map(name => `icon_${name}`);
                    const iconData = await new Promise(resolve => {
                        chrome.storage.local.get(iconKeys, resolve);
                    });
                    
                    // 创建完整的导出数据
                    exportData = {};
                    for (const siteName of siteNames) {
                        exportData[siteName] = {
                            ...storedSites[siteName],
                            icon: iconData[`icon_${siteName}`] || '' // 添加图标
                        };
                    }
                }
            }
            
            // 导出为JSON文件
            const jsonStr = JSON.stringify(exportData, null, 2);
            const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
            
            // 创建下载链接
            const now = new Date();
            const timestamp = `${now.getFullYear()}${(now.getMonth()+1).toString().padStart(2, '0')}${now.getDate().toString().padStart(2, '0')}_${now.getHours().toString().padStart(2, '0')}${now.getMinutes().toString().padStart(2, '0')}`;
            
        const a = document.createElement('a');
        a.href = url;
            a.download = `totp_config_${timestamp}.json`;
            document.body.appendChild(a);
        a.click();
            
            // 清理
            setTimeout(() => {
                document.body.removeChild(a);
        URL.revokeObjectURL(url);
            }, 100);
            
            showStatus('配置已导出');
        } catch (error) {
            console.error('导出配置失败:', error);
            showStatus(`导出失败: ${error.message}`, true);
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
                    // 解析JSON文件
                    const jsonContent = e.target.result;
                    const importedData = JSON.parse(jsonContent);
                    
                    // 验证配置格式
                    if (typeof importedData !== 'object') {
                        showStatus('导入失败: 配置格式不正确', true);
                        return;
                    }
                    
                    console.log('解析的导入数据:', importedData);
                    
                    // 获取站点数量，确认导入的数据是正确的格式
                    const sitesCount = Object.keys(importedData).length;
                    if (sitesCount === 0) {
                        showStatus('导入失败: 未找到站点配置', true);
                        return;
                    }
                    
                    // 避免存储配额限制：分离图标和基本数据
                    try {
                        // 1. 提取图标数据单独存储到local存储
                        const iconStorage = {};
                        const basicConfig = {};
                        
                        // 遍历所有站点，分离数据
                        for (const [siteName, siteData] of Object.entries(importedData)) {
                            // 创建基本配置（不包含图标）
                            basicConfig[siteName] = {
                                secret: siteData.secret,
                                urls: siteData.urls
                            };
                            
                            // 单独保存图标数据
                            if (siteData.icon) {
                                iconStorage[`icon_${siteName}`] = siteData.icon;
                            }
                        }
                        
                        // 2. 保存基本配置到sync存储
                        await new Promise(resolve => {
                            chrome.storage.sync.set({ 'sites': basicConfig }, resolve);
                        });
                        
                        // 3. 保存图标数据到local存储(更大配额)
                        await new Promise(resolve => {
                            chrome.storage.local.set(iconStorage, resolve);
                        });
                        
                        // 保存标记，表明图标存储在local
                        await new Promise(resolve => {
                            chrome.storage.sync.set({ 'icons_in_local': true }, resolve);
                        });
                        
                        // 更新内存中的配置 - 保持完整数据结构不变
                        currentConfig.sites = importedData;
                        
                    } catch (storageError) {
                        console.error('存储数据失败:', storageError);
                        showStatus(`导入失败: 存储限制错误 - ${storageError.message}`, true);
                        return;
                    }
                    
                    // 如果配置中已经有API连接信息，发送更新到后台
                    if (currentConfig.baseUrl && currentConfig.apiKey) {
                        try {
                            showStatus('正在同步配置到服务器...');
                            
                            // 直接调用API更新配置
                            const updateUrl = `${currentConfig.baseUrl}/api/v1/plugin/twofahelper/update_config?apikey=${currentConfig.apiKey}`;
                            console.log('调用更新配置API:', updateUrl);
                            const response = await fetch(updateUrl, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json'
                                },
                                body: JSON.stringify(importedData)
                            });
                            
                            if (!response.ok) {
                                throw new Error(`服务器返回错误 (${response.status}): ${response.statusText}`);
                            }
                            
                            const result = await response.json();
                            console.log('更新配置返回结果:', result);
                            
                            if (result.code === 0 || result.success === true) {
                                // 显示成功消息
                                showStatus(`导入成功，共 ${sitesCount} 个站点已同步到服务器`);
                            } else {
                                throw new Error(result.message || '服务器返回错误');
                            }
                        } catch (syncError) {
                            console.error('同步到服务器失败:', syncError);
                            showStatus(`导入成功，但同步到服务器失败: ${syncError.message}`, true);
                        }
                    } else {
                        showStatus(`导入成功，共 ${sitesCount} 个站点`);
                    }
                    
                    // 刷新站点列表
                    await refreshSitesList();
                    
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

    // 检查更新 - 优化GitHub API调用
    async function checkForUpdates() {
        try {
            // 避免频繁检查，增加缓存逻辑
            const cachedVersion = await getCachedVersion();
            if (cachedVersion && !shouldCheckUpdate()) {
                // 使用缓存的结果
                if (cachedVersion.isNewer) {
                    showUpdateNotice(cachedVersion.version);
                    updateVersionStatus('update_available');
                } else {
                    updateVersionStatus('latest');
                }
                return;
            }
            
            // 首先检查网络连接
            const networkStatus = await checkNetworkStatus();
            if (!networkStatus.isOnline) {
                showStatus('网络连接不可用，无法检查更新', true);
                updateVersionStatus('offline');
                return;
            }

            // 使用随机参数避免缓存
            const timestamp = new Date().getTime();
            const response = await fetch(`https://api.github.com/repos/madrays/MoviePilot-Plugins/releases?_=${timestamp}`, {
                headers: {
                    'Accept': 'application/vnd.github.v3+json',
                    // 添加User-Agent来避免GitHub API的一些限制
                    'User-Agent': 'Mozilla/5.0 TOTP-Helper'
                },
                // 使用缓存控制
                cache: 'no-store'
            });
            
            if (!response.ok) {
                if (response.status === 403) {
                    // 限制访问的处理，使用本地版本显示
                    showStatus('GitHub API访问受限，将使用本地版本信息', true);
                    updateVersionStatus('error');
                    return;
                }
                throw new Error(`GitHub API返回错误: ${response.status}`);
            }
            
            const releases = await response.json();
            
            // 获取最新的正式版本
            const latestRelease = releases.find(release => !release.prerelease);
            if (!latestRelease) {
                throw new Error('未找到正式版本');
            }
            
            const latestVersion = latestRelease.tag_name.replace('v', '');
            const currentVersion = CURRENT_VERSION;  // 使用CURRENT_VERSION常量
            
            // 缓存版本信息
            const isNewer = isNewerVersion(latestVersion, currentVersion);
            cacheVersionInfo(latestVersion, isNewer);
            
            if (isNewer) {
                showUpdateNotice(latestVersion);
                updateVersionStatus('update_available');
            } else {
                updateVersionStatus('latest');
            }
        } catch (error) {
            console.error('获取版本信息失败:', error);
            if (error.message.includes('Failed to fetch') || error.message.includes('Network Error')) {
                showStatus('无法连接到GitHub，请检查网络连接', true);
                updateVersionStatus('offline');
            } else {
                showStatus('检查更新失败: ' + error.message, true);
                updateVersionStatus('error');
            }
            
            // 使用本地存储的上次检查结果，如果有的话
            const cachedVersion = await getCachedVersion();
            if (cachedVersion) {
                if (cachedVersion.isNewer) {
                    showUpdateNotice(cachedVersion.version);
                }
            }
        }
    }
    
    // 缓存版本信息
    function cacheVersionInfo(version, isNewer) {
        const now = new Date().getTime();
        const versionInfo = {
            version: version,
            isNewer: isNewer,
            timestamp: now
        };
        
        chrome.storage.local.set({ 'versionCache': versionInfo });
    }
    
    // 获取缓存的版本信息
    async function getCachedVersion() {
        return new Promise(resolve => {
            chrome.storage.local.get('versionCache', result => {
                if (result.versionCache) {
                    resolve(result.versionCache);
                } else {
                    resolve(null);
                }
            });
        });
    }
    
    // 判断是否应该检查更新（避免频繁API调用）
    async function shouldCheckUpdate() {
        const cache = await getCachedVersion();
        if (!cache || !cache.timestamp) return true;
        
        const now = new Date().getTime();
        const elapsed = now - cache.timestamp;
        
        // 间隔大于2小时才检查
        return elapsed > 2 * 60 * 60 * 1000;
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

    // 更新版本状态显示
    function updateVersionStatus(status) {
        const versionElement = document.getElementById('currentVersion');
        const updateNotice = document.getElementById('updateNotice');
        const statusBanner = document.getElementById('version-status-banner');
        const statusIcon = document.getElementById('status-icon');
        const statusMessage = document.getElementById('status-message');
        const statusAction = document.getElementById('status-action');
        
        if (!versionElement) return;
        
        // 移除所有可能的状态类
        versionElement.classList.remove('latest', 'update_available', 'offline', 'error');
        
        // 显示状态横幅
        if (statusBanner) {
            // 移除之前的所有状态类
            statusBanner.classList.remove('latest', 'update', 'offline', 'error');
            
            // 显示横幅
            statusBanner.style.display = 'flex';
            
            // 配置横幅内容
            switch (status) {
                case 'latest':
                    versionElement.classList.add('latest');
                    versionElement.title = '当前已是最新版本';
                    
                    statusBanner.classList.add('latest');
                    statusIcon.innerHTML = '✓';
                    statusMessage.textContent = '您的 TOTP 助手已是最新版本';
                    statusAction.textContent = '查看版本历史';
                    statusAction.classList.add('latest');
                    statusAction.onclick = function() {
                        chrome.tabs.create({
                            url: 'https://github.com/madrays/MoviePilot-Plugins/releases'
                        });
                    };
                    
                    if (updateNotice) {
                        updateNotice.style.display = 'none';
                    }
                    break;
                
                case 'update_available':
                    versionElement.classList.add('update_available');
                    versionElement.title = '有新版本可用';
                    
                    statusBanner.classList.add('update');
                    statusIcon.innerHTML = '↑';
                    statusMessage.textContent = '发现 TOTP 助手新版本，建议更新';
                    statusAction.textContent = '立即更新';
                    statusAction.classList.add('update');
                    statusAction.onclick = function() {
                        chrome.tabs.create({
                            url: 'https://github.com/madrays/MoviePilot-Plugins/releases'
                        });
                    };
                    
                    if (updateNotice) {
                        updateNotice.style.display = 'inline-block';
                    }
                    break;
                
                case 'offline':
                    versionElement.classList.add('offline');
                    versionElement.title = '网络连接不可用';
                    
                    statusBanner.classList.add('offline');
                    statusIcon.innerHTML = '⚠';
                    statusMessage.textContent = '网络连接不可用，无法检查更新';
                    statusAction.textContent = '重试';
                    statusAction.classList.add('offline');
                    statusAction.onclick = checkForUpdates;
                    
                    if (updateNotice) {
                        updateNotice.style.display = 'none';
                    }
                    break;
                
                case 'error':
                    versionElement.classList.add('error');
                    versionElement.title = '检查更新失败';
                    
                    statusBanner.classList.add('error');
                    statusIcon.innerHTML = '!';
                    statusMessage.textContent = '检查更新失败，可能是GitHub访问受限';
                    statusAction.textContent = '重试';
                    statusAction.classList.add('error');
                    statusAction.onclick = checkForUpdates;
                    
                    if (updateNotice) {
                        updateNotice.style.display = 'none';
                    }
                    break;
            }
        } else {
            // 如果没有状态横幅，退回到原来的行为
            switch (status) {
                case 'latest':
                    versionElement.classList.add('latest');
                    versionElement.title = '当前已是最新版本';
                    if (updateNotice) {
                        updateNotice.style.display = 'none';
                    }
                    break;
                
                case 'update_available':
                    versionElement.classList.add('update_available');
                    versionElement.title = '有新版本可用';
                    if (updateNotice) {
                        updateNotice.style.display = 'inline-block';
                    }
                    break;
                
                case 'offline':
                    versionElement.classList.add('offline');
                    versionElement.title = '网络连接不可用';
                    if (updateNotice) {
                        updateNotice.style.display = 'none';
                    }
                    break;
                
                case 'error':
                    versionElement.classList.add('error');
                    versionElement.title = '检查更新失败';
                    if (updateNotice) {
                        updateNotice.style.display = 'none';
                    }
                    break;
            }
        }
    }

    // 检查地址是否是HTTP或局域网，这会导致混合内容问题
    function checkHttpWarning(url) {
        const httpWarning = document.getElementById('httpWarning');
        if (!httpWarning) return;
        
        // 如果为空，隐藏警告
        if (!url) {
            httpWarning.style.display = 'none';
            return;
        }
        
        // 检查是否使用HTTP
        if (url.startsWith('http://')) {
            httpWarning.style.display = 'block';
            return;
        }
        
        // 检查是否是局域网IP
        try {
            const urlObj = new URL(url);
            const hostname = urlObj.hostname;
            
            // 检查常见的局域网地址模式
            if (
                hostname === 'localhost' ||
                hostname.startsWith('127.') ||
                hostname.startsWith('192.168.') ||
                hostname.startsWith('10.') ||
                hostname.match(/^172\.(1[6-9]|2[0-9]|3[0-1])\./)
            ) {
                httpWarning.style.display = 'block';
                return;
            }
            
            // 其他情况，隐藏警告
            httpWarning.style.display = 'none';
        } catch (e) {
            // URL解析失败，保持警告隐藏
            httpWarning.style.display = 'none';
        }
    }

    // 添加到baseUrl输入字段的事件监听
    if (baseUrlInput) {
        baseUrlInput.addEventListener('input', function() {
            const url = this.value.trim();
            checkHttpWarning(url);
        });
        
        // 页面加载时检查一次
        checkHttpWarning(baseUrlInput.value.trim());
    }

    // 创建保存排序按钮的函数
    function createSaveOrderButton() {
        const container = document.getElementById('sitesList').parentNode;
        
        // 检查是否已存在按钮
        if (document.getElementById('saveOrderBtn')) return;
        
        // 创建按钮容器
        const btnContainer = document.createElement('div');
        btnContainer.style.textAlign = 'center';
        btnContainer.style.margin = '15px 0';
        
        // 创建保存排序按钮
        const saveBtn = document.createElement('button');
        saveBtn.id = 'saveOrderBtn';
        saveBtn.textContent = '保存排序';
        saveBtn.className = 'btn-primary highlight';
        saveBtn.style.backgroundColor = '#2196F3'; // 改为蓝色
        saveBtn.style.color = 'white';
        saveBtn.style.border = 'none';
        saveBtn.style.padding = '10px 20px';
        saveBtn.style.borderRadius = '4px';
        saveBtn.style.cursor = 'pointer';
        saveBtn.style.fontSize = '16px';
        saveBtn.style.fontWeight = 'bold';
        saveBtn.style.display = 'none'; // 默认隐藏
        saveBtn.onclick = saveCustomOrder;
        
        // 添加按钮过渡效果
        saveBtn.style.transition = 'all 0.3s ease';
        
        // 添加按钮悬停效果
        saveBtn.onmouseover = function() { 
            this.style.backgroundColor = '#1976D2'; // 深蓝色
            this.style.transform = 'scale(1.05)';
        };
        saveBtn.onmouseout = function() { 
            this.style.backgroundColor = '#2196F3'; // 恢复蓝色
            this.style.transform = 'scale(1)';
        };
        
        // 高亮样式
        const style = document.createElement('style');
        style.textContent = `
            .highlight {
                animation: pulse 1.5s infinite;
            }
            @keyframes pulse {
                0% { box-shadow: 0 0 0 0 rgba(33, 150, 243, 0.7); }
                70% { box-shadow: 0 0 0 10px rgba(33, 150, 243, 0); }
                100% { box-shadow: 0 0 0 0 rgba(33, 150, 243, 0); }
            }
        `;
        document.head.appendChild(style);
        
        // 将按钮添加到容器
        btnContainer.appendChild(saveBtn);
        
        // 将容器添加到站点列表下方
        container.insertBefore(btnContainer, document.getElementById('sitesList').nextSibling);
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

// 显示状态消息 - 移到全局作用域
function showStatus(message, isError = false, persistent = false) {
    const statusElement = document.getElementById('status');
    if (statusElement) {
        statusElement.textContent = message;
        statusElement.className = isError ? 'status error' : 'status success';
        statusElement.style.display = 'block';
        
        // 清除之前的超时
        if (statusElement._hideTimeout) {
            clearTimeout(statusElement._hideTimeout);
            statusElement._hideTimeout = null;
        }
        
        // 如果不是持久显示，3秒后自动隐藏
        if (!persistent) {
            statusElement._hideTimeout = setTimeout(() => {
                statusElement.style.display = 'none';
                statusElement._hideTimeout = null;
            }, 3000);
        }
    }
}

// 检查网络状态
async function checkNetworkStatus() {
    try {
        // 尝试访问一个更可靠的小资源
        const urls = [
            'https://www.cloudflare.com/favicon.ico',
            'https://www.baidu.com/favicon.ico',
            'https://www.qq.com/favicon.ico'
        ];
        
        // 同时尝试多个URL以增加成功率
        const promises = urls.map(url => 
            fetch(url, { 
                mode: 'no-cors',
                cache: 'no-store',
                method: 'HEAD',
                timeout: 5000 
            }).catch(e => null)
        );
        
        const results = await Promise.all(promises);
        // 只要有一个成功就认为网络正常
        return { isOnline: results.some(r => r !== null) };
    } catch (error) {
        return { isOnline: false };
    }
}

