// 当页面加载完成后执行
document.addEventListener('DOMContentLoaded', async function () {
  try {
    // 获取HTML元素
    const codeContainer = document.getElementById('codes-container');
    const errorElement = document.getElementById('error');
    const loadingElement = document.getElementById('loading');
    const setupButton = document.getElementById('setup-button');
    const settingsButton = document.getElementById('settings-button');
    const notificationElement = document.getElementById('notification');
    
    // 初始化加载状态
    if (loadingElement) loadingElement.style.display = 'block';
    if (errorElement) errorElement.style.display = 'none';
    
    // 显示错误信息
    function displayError(message) {
      console.error('错误:', message);
      if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.display = 'block';
      }
      if (loadingElement) loadingElement.style.display = 'none';
      if (setupButton) setupButton.style.display = 'block';
    }
    
    // 显示通知
    function showNotification(message, duration = 2000) {
      if (!notificationElement) return;
      
      notificationElement.textContent = message;
      notificationElement.classList.add('show');
      
      setTimeout(() => {
        notificationElement.classList.remove('show');
      }, duration);
    }
    
    // 打开设置页面
    function openOptionsPage() {
      chrome.runtime.openOptionsPage();
    }
    
    // 设置按钮监听器
    if (setupButton) {
      setupButton.addEventListener('click', openOptionsPage);
    }
    
    if (settingsButton) {
      settingsButton.addEventListener('click', openOptionsPage);
    }
    
    // 获取API配置 - 统一检查所有可能的配置格式
    async function getApiConfig() {
      return new Promise((resolve) => {
        console.log("尝试获取API配置...");
        
        // 首先尝试直接获取新格式的配置
        chrome.storage.sync.get(['apiBaseUrl', 'apiKey'], (result) => {
          console.log("尝试读取apiBaseUrl和apiKey结果:", result);
          
          if (result.apiBaseUrl && result.apiKey) {
            const config = {
              baseUrl: result.apiBaseUrl,
              apiKey: result.apiKey
            };
            console.log("找到新格式配置:", config);
            resolve(config);
          } else {
            // 尝试从apiConfig对象中获取
            chrome.storage.sync.get(['apiConfig'], (result) => {
              console.log("尝试读取apiConfig结果:", result);
              
              if (result.apiConfig && result.apiConfig.baseUrl && result.apiConfig.apiKey) {
                const config = {
                  baseUrl: result.apiConfig.baseUrl,
                  apiKey: result.apiConfig.apiKey
                };
                console.log("找到旧格式配置:", config);
                
                // 保存为新格式以便将来使用
                chrome.storage.sync.set({
                  apiBaseUrl: config.baseUrl,
                  apiKey: config.apiKey
                });
                
                resolve(config);
              } else {
                console.log("没有找到有效的API配置");
                resolve(null);
              }
            });
          }
        });
      });
    }
    
    // 创建验证码卡片
    function createCodeCard(container, siteName, data) {
      try {
        // 创建卡片元素
        const card = document.createElement('div');
        card.className = 'code-card';
        
        // 站点名称和图标行
        const siteRow = document.createElement('div');
        siteRow.className = 'site-row';
        
        // 添加站点图标容器
        const siteIcon = document.createElement('div');
        siteIcon.className = 'site-icon';
        
        // 使用首字母作为初始占位图标
        const letter = siteName.charAt(0).toUpperCase();
        const hue = Math.abs(siteName.split('').reduce((a, b) => a + b.charCodeAt(0), 0) % 360);
        siteIcon.textContent = letter;
        siteIcon.style.backgroundColor = `hsl(${hue}, 70%, 60%)`;
        
        // 尝试从URL获取图标
        if (data.urls && Array.isArray(data.urls) && data.urls.length > 0) {
          fetchSiteIcon(data.urls[0], siteIcon);
        }
        
        siteRow.appendChild(siteIcon);
        
        // 站点名称
        const nameElement = document.createElement('div');
        nameElement.className = 'site-name';
        nameElement.textContent = siteName;
        siteRow.appendChild(nameElement);
        
        card.appendChild(siteRow);
        
        // 验证码显示区域
        const codeDisplay = document.createElement('div');
        codeDisplay.className = 'code-display';
        
        // 验证码文本
        const codeElement = document.createElement('div');
        codeElement.className = 'totp-code';
        codeElement.textContent = data.code || '------';
        codeDisplay.appendChild(codeElement);
        
        // 复制按钮
        const copyButton = document.createElement('button');
        copyButton.className = 'copy-button';
        copyButton.textContent = '复制';
        copyButton.addEventListener('click', () => {
          const code = data.code || '';
          if (!code) return;
          
          // 尝试使用新的剪贴板API
          navigator.clipboard.writeText(code)
            .then(() => {
              showNotification('验证码已复制到剪贴板');
              copyButton.textContent = '已复制';
              setTimeout(() => {
                copyButton.textContent = '复制';
              }, 1000);
            })
            .catch(err => {
              console.error('复制失败:', err);
              // 尝试兼容的剪贴板方法
              const textArea = document.createElement('textarea');
              textArea.value = code;
              document.body.appendChild(textArea);
              textArea.focus();
              textArea.select();
              
              try {
                const successful = document.execCommand('copy');
                if (successful) {
                  showNotification('验证码已复制到剪贴板');
                  copyButton.textContent = '已复制';
                  setTimeout(() => {
                    copyButton.textContent = '复制';
                  }, 1000);
                } else {
                  showNotification('复制失败，请手动复制');
                }
              } catch (err) {
                console.error('复制命令失败:', err);
                showNotification('复制失败，请手动复制');
              }
              
              document.body.removeChild(textArea);
            });
        });
        codeDisplay.appendChild(copyButton);
        
        card.appendChild(codeDisplay);
        
        // 进度条容器
        const progressContainer = document.createElement('div');
        progressContainer.className = 'progress-container';
        
        // 倒计时文本
        const timeText = document.createElement('div');
        timeText.className = 'time-text';
        timeText.textContent = `${data.remaining_seconds || 0}秒后更新`;
        progressContainer.appendChild(timeText);
        
        // 进度条
        const progressBar = document.createElement('div');
        progressBar.className = 'progress-bar';
        progressBar.dataset.remaining = data.remaining_seconds || 0;
        progressBar.style.width = `${((30 - (data.remaining_seconds || 0)) / 30) * 100}%`;
        progressContainer.appendChild(progressBar);
        
        card.appendChild(progressContainer);
        
        // 添加到容器
        container.appendChild(card);
      } catch (error) {
        console.error('创建验证码卡片失败:', error);
      }
    }
    
    // 从URL获取网站图标
    async function fetchSiteIcon(url, iconElement) {
      try {
        if (!url) return;
        
        // 提取域名
        let domain = url;
        try {
          domain = new URL(url).hostname;
        } catch (e) {
          console.error('无法解析URL:', e);
        }
        
        // 首先尝试直接获取网站的favicon
        let faviconUrl = `https://${domain}/favicon.ico`;
        
        // 尝试加载图标
        try {
          const img = new Image();
          img.onload = function() {
            // 成功加载图标，更新显示
            iconElement.innerHTML = '';
            const iconImg = document.createElement('img');
            iconImg.src = faviconUrl;
            iconImg.alt = 'Site Icon';
            iconImg.style.width = '100%';
            iconImg.style.height = '100%';
            iconElement.appendChild(iconImg);
          };
          
          img.onerror = function() {
            console.error('无法直接加载favicon，尝试备用方案');
            tryFallbackIcon(domain, iconElement);
          };
          
          img.crossOrigin = 'Anonymous';
          img.src = faviconUrl;
        } catch (error) {
          console.error('加载图标失败:', error);
          tryFallbackIcon(domain, iconElement);
        }
      } catch (error) {
        console.error('获取站点图标失败:', error);
      }
    }
    
    // 尝试备用图标获取方法
    function tryFallbackIcon(domain, iconElement) {
      try {
        // 尝试Google Favicon服务
        const googleFaviconUrl = `https://www.google.com/s2/favicons?domain=${domain}&sz=64`;
        
        const fallbackImg = new Image();
        fallbackImg.onload = function() {
          iconElement.innerHTML = '';
          const iconImg = document.createElement('img');
          iconImg.src = googleFaviconUrl;
          iconImg.alt = 'Site Icon';
          iconImg.style.width = '100%';
          iconImg.style.height = '100%';
          iconElement.appendChild(iconImg);
        };
        
        fallbackImg.onerror = function() {
          console.error('无法通过Google获取图标，尝试DuckDuckGo');
          tryDuckDuckGoIcon(domain, iconElement);
        };
        
        fallbackImg.crossOrigin = 'Anonymous';
        fallbackImg.src = googleFaviconUrl;
      } catch (error) {
        console.error('备用图标加载失败:', error);
        tryDuckDuckGoIcon(domain, iconElement);
      }
    }
    
    // 尝试DuckDuckGo图标API
    function tryDuckDuckGoIcon(domain, iconElement) {
      try {
        const ddgIconUrl = `https://icons.duckduckgo.com/ip3/${domain}.ico`;
        
        const ddgImg = new Image();
        ddgImg.onload = function() {
          iconElement.innerHTML = '';
          const iconImg = document.createElement('img');
          iconImg.src = ddgIconUrl;
          iconImg.alt = 'Site Icon';
          iconImg.style.width = '100%';
          iconImg.style.height = '100%';
          iconElement.appendChild(iconImg);
        };
        
        ddgImg.onerror = function() {
          console.error('无法获取网站图标');
          // 保持默认的首字母图标
        };
        
        ddgImg.crossOrigin = 'Anonymous';
        ddgImg.src = ddgIconUrl;
      } catch (error) {
        console.error('DuckDuckGo图标加载失败:', error);
        // 保持默认的首字母图标
      }
    }
    
    // 更新单个进度条
    function updateProgressBar(progressBar) {
      if (!progressBar || !progressBar.dataset.remaining) return;
      
      // 获取初始剩余时间
      let remaining = parseInt(progressBar.dataset.remaining);
      if (isNaN(remaining)) remaining = 0;
      
      // 已过时间
      remaining = Math.max(0, remaining - 1);
      progressBar.dataset.remaining = remaining;
      
      // 更新进度条宽度 - 反向进度：剩余时间越少，进度条越长
      const percent = ((30 - remaining) / 30) * 100;
      progressBar.style.width = `${percent}%`;
      
      // 更新颜色
      if (remaining <= 5) {
        progressBar.style.backgroundColor = '#f44336'; // 红色
      } else if (remaining <= 10) {
        progressBar.style.backgroundColor = '#ff9800'; // 橙色
      } else {
        progressBar.style.backgroundColor = '#4caf50'; // 绿色
      }
      
      // 更新相关的时间文本
      const timeText = progressBar.parentElement.querySelector('.time-text');
      if (timeText) {
        timeText.textContent = `${remaining}秒后更新`;
      }
    }
    
    // 更新所有进度条
    function updateProgressBars() {
      try {
        // 获取所有进度条
        const progressBars = document.querySelectorAll('.progress-bar');
        
        // 对每个进度条进行更新
        progressBars.forEach(updateProgressBar);
      } catch (error) {
        console.error('更新进度条失败:', error);
      }
    }
    
    // 显示配置提示
    function showConfigPrompt() {
      if (setupButton) setupButton.style.display = 'block';
      if (loadingElement) loadingElement.style.display = 'none';
      
      if (errorElement) {
        errorElement.textContent = '请先在选项页配置API连接信息';
        errorElement.style.display = 'block';
      }
      
      if (codeContainer) {
        codeContainer.innerHTML = '<div class="empty-message">请先配置服务器</div>';
      }
    }
    
    // 获取验证码数据 - 直接从API获取，不依赖后台页面
    async function fetchTOTPCodes() {
      try {
        // 获取API配置
        const config = await getApiConfig();
        if (!config || !config.baseUrl || !config.apiKey) {
          throw new Error('未配置API连接信息');
        }
        
        console.log('正在获取验证码...');
        console.log('使用配置:', config);
        
        // 从API获取验证码
        const response = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/get_codes?apikey=${config.apiKey}`);
        if (!response.ok) {
          throw new Error(`服务器返回错误 (${response.status}): ${response.statusText}`);
        }
        
        const data = await response.json();
        const codesData = data.data || data;
        
        // 验证返回数据
        if (!codesData || typeof codesData !== 'object') {
          throw new Error('无效的验证码数据');
        }
        
        return codesData;
      } catch (error) {
        console.error('获取验证码失败:', error);
        throw error;
      }
    }
    
    // 刷新验证码
    async function refreshTOTPCodes() {
      try {
        console.log('开始刷新验证码...');
        
        // 获取配置
        const config = await getApiConfig();
        
        if (!config || !config.baseUrl || !config.apiKey) {
          console.log('未找到API配置，显示配置提示');
          showConfigPrompt();
          return;
        }
        
        console.log('找到API配置:', config);
        
        // 获取验证码
        const codesData = await fetchTOTPCodes();
        console.log('获取到验证码数据:', Object.keys(codesData).length, '个站点');
        
        // 清空容器并创建新卡片
        if (codeContainer) {
          codeContainer.innerHTML = '';
          
          // 创建验证码卡片
          for (const [siteName, data] of Object.entries(codesData)) {
            createCodeCard(codeContainer, siteName, data);
          }
        }
        
        // 隐藏错误和加载提示
        if (errorElement) errorElement.style.display = 'none';
        if (loadingElement) loadingElement.style.display = 'none';
        if (setupButton) setupButton.style.display = 'none';
        
      } catch (error) {
        console.error('刷新验证码失败:', error);
        displayError('刷新验证码失败: ' + error.message);
      }
    }
    
    // 初始化：检查配置并获取验证码
    console.log('TOTP Popup已加载');
    
    // 先尝试获取配置
    const config = await getApiConfig();
    console.log('初始化加载配置结果:', config);
    
    if (!config || !config.baseUrl || !config.apiKey) {
      console.log('未找到有效配置，显示配置提示');
      showConfigPrompt();
    } else {
      // 配置有效，刷新验证码
      console.log('找到有效配置，开始刷新验证码');
      await refreshTOTPCodes();
    }
    
    // 定期刷新验证码 - 每5秒刷新一次
    setInterval(refreshTOTPCodes, 5000);
    
    // 每秒更新进度条
    setInterval(updateProgressBars, 1000);
    
  } catch (error) {
    console.error('初始化失败:', error);
    displayError('初始化失败: ' + error.message);
  }
});
