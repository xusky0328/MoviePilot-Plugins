// 当前页面URL
const currentUrl = window.location.href;

// 监听页面加载完成
document.addEventListener('DOMContentLoaded', function() {
  console.log('TOTP助手内容脚本已加载');
  
  // 添加按钮到页面上的特定输入框旁边
  setTimeout(init, 1000);
});

// 监听DOM变化，以便在动态加载的页面上添加按钮
const mutationObserver = new MutationObserver(function(mutations) {
  mutations.forEach(function(mutation) {
    if (mutation.addedNodes && mutation.addedNodes.length > 0) {
      // 检测到DOM变化，可能有新的输入框
      setTimeout(init, 500);
    }
  });
});

// 配置观察器
mutationObserver.observe(document.body, {
  childList: true,
  subtree: true
});

// 查找验证码输入框
function findOTPInput() {
  // 常见的2FA/OTP输入框选择器
  const selectors = [
    'input[name*="otp" i]',
    'input[name*="2fa" i]',
    'input[name*="code" i]',
    'input[name*="token" i]',
    'input[name*="two_step_code" i]',
    'input[placeholder*="验证码" i]',
    'input[placeholder*="code" i]',
    'input[aria-label*="验证码" i]',
    'input[aria-label*="code" i]',
    // 特定网站的选择器
    'input#totp',                  // 一些PT站点特定ID
    'input[name="twostep_code"]',  // 一些PT站点使用的名称
    'input[name="two_step_code"]', // 另一种常见命名
    'input.form-control[maxlength="6"]', // 6位数字验证码的常见模式
    // 1ptba特定选择器
    'input[name="code"]',
    'form[action*="security"] input[type="text"]'
  ];
  
  // 尝试所有选择器
  let matchedInputs = [];
  for (const selector of selectors) {
    const inputs = document.querySelectorAll(selector);
    if (inputs.length > 0) {
      inputs.forEach(input => matchedInputs.push(input));
    }
  }
  
  // 如果没有找到输入框，使用通用选择器
  if (matchedInputs.length === 0) {
    matchedInputs = Array.from(document.querySelectorAll('input[type="password"], input[type="text"]'));
    
    // 过滤掉不可能是验证码输入框的元素
    matchedInputs = matchedInputs.filter(input => {
      // 验证码通常是6位数，输入框长度有限制
      const maxLength = input.getAttribute('maxlength');
      if (maxLength && (maxLength === '6' || maxLength === '8')) {
        return true;
      }
      
      // 检查输入框是否在表单中
      const form = input.closest('form');
      if (form && (
        form.action.includes('security') || 
        form.action.includes('2fa') || 
        form.action.includes('verification')
      )) {
        return true;
      }
      
      // 检查输入框附近的文本是否包含"验证码"等相关词
      const parentText = input.parentElement?.textContent?.toLowerCase() || '';
      if (
        parentText.includes('验证码') || 
        parentText.includes('code') || 
        parentText.includes('otp') || 
        parentText.includes('2fa') ||
        parentText.includes('两步') ||
        parentText.includes('two-factor') ||
        parentText.includes('two factor') ||
        parentText.includes('two step')
      ) {
        return true;
      }
      
      // 常见的验证码input id或name
      const idOrName = (input.id || '') + (input.name || '');
      return (
        idOrName.includes('otp') || 
        idOrName.includes('2fa') || 
        idOrName.includes('code') || 
        idOrName.includes('token') ||
        idOrName.includes('totp')
      );
    });
  }
  
  // 返回找到的输入框
  return matchedInputs;
}

// 主函数
async function init() {
  try {
    // 防止重复初始化
    if (document.querySelector('.totp-helper-initialized')) {
      return;
    }

    // 检查是否为MP插件或仪表盘页面，如果是则不显示
    if (isMoviePilotPage()) {
      return;
    }

    // 检查页面是否包含二步验证相关内容
    if (!isOTPPage()) {
      return;
    }
    
    // 创建验证码展示面板
    createOTPPanel();
    
  } catch (error) {
    console.error('初始化TOTP助手失败:', error);
  }
}

// 检查是否为MoviePilot页面
function isMoviePilotPage() {
  // 检查URL
  const url = window.location.href.toLowerCase();
  
  // 检查是否包含MoviePilot相关内容
  if (url.includes('plugins') || 
      url.includes('dashboard') || 
      url.includes('/mp/')) {
    return true;
  }
  
  // 检查页面标题是否包含MoviePilot
  const title = document.title.toLowerCase();
  if (title.includes('moviepilot') || 
      title.includes('mp仪表盘')) {
    return true;
  }
  
  // 检查页面内容是否包含MoviePilot特征
  const bodyContent = document.body.textContent.toLowerCase();
  if (bodyContent.includes('moviepilot仪表盘') || 
      bodyContent.includes('mp控制台')) {
    return true;
  }
  
  return false;
}

// 检查页面是否包含二步验证相关内容
function isOTPPage() {
  // 检查URL
  const url = window.location.href.toLowerCase();
  if (url.includes('2fa') || 
      url.includes('two-factor') || 
      url.includes('two-step') || 
      url.includes('security') ||
      url.includes('verification')) {
    return true;
  }
  
  // 检查页面内容
  const pageText = document.body.textContent.toLowerCase();
  if (pageText.includes('两步验证') ||
      pageText.includes('二步验证') ||
      pageText.includes('two-factor') ||
      pageText.includes('2fa') ||
      pageText.includes('验证码')) {
    return true;
  }
  
  // 检查是否存在验证码输入框
  const inputs = findOTPInput();
  return inputs && inputs.length > 0;
}

// 创建验证码展示面板
function createOTPPanel() {
  // 创建面板容器
  const panel = document.createElement('div');
  panel.className = 'totp-helper-panel totp-helper-initialized';
  panel.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
    padding: 12px;
    z-index: 9999;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    max-width: 300px;
    min-width: 200px;
    opacity: 0.95;
    transition: opacity 0.2s;
  `;
  
  // 添加鼠标悬停效果
  panel.addEventListener('mouseenter', () => {
    panel.style.opacity = '1';
  });
  panel.addEventListener('mouseleave', () => {
    panel.style.opacity = '0.95';
  });
  
  // 创建标题
  const title = document.createElement('div');
  title.style.cssText = `
    font-size: 14px;
    font-weight: bold;
    color: #333;
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  `;
  title.textContent = '验证码助手';
  
  // 创建关闭按钮
  const closeButton = document.createElement('button');
  closeButton.textContent = '×';
  closeButton.style.cssText = `
    border: none;
    background: none;
    font-size: 18px;
    color: #999;
    cursor: pointer;
    padding: 0 4px;
  `;
  closeButton.onclick = () => panel.remove();
  title.appendChild(closeButton);
  
  // 创建内容区域
  const content = document.createElement('div');
  content.style.cssText = `
    margin-top: 8px;
    max-height: 300px;
    overflow-y: auto;
  `;
  
  // 添加刷新按钮
  const refreshButton = document.createElement('button');
  refreshButton.textContent = '刷新';
  refreshButton.style.cssText = `
    border: 1px solid #ddd;
    background: #f8f8f8;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
    cursor: pointer;
    margin-top: 8px;
    width: 100%;
  `;
  
  // 更新验证码函数
  async function updateCodes() {
    try {
      const codes = await fetchTOTPCodes();
      content.innerHTML = '';
      
      // 确保codes是数组
      const codesArray = Array.isArray(codes) ? codes : [];
      
      // 获取当前域名
      const domain = window.location.hostname;
      
      // 过滤出匹配当前域名的验证码
      const matchedCodes = codesArray.filter(code => 
        code.urls && code.urls.some(url => url.includes(domain))
      );
      
      if (matchedCodes.length === 0) {
        content.innerHTML = '<div style="color: #999; text-align: center; padding: 8px;">未找到匹配的验证码</div>';
      return;
    }
    
      matchedCodes.forEach(code => {
        const codeItem = document.createElement('div');
        codeItem.style.cssText = `
          padding: 8px;
          border: 1px solid #4caf50;
          border-radius: 4px;
          margin-bottom: 8px;
          background: #f1f8e9;
        `;
        
        // 创建站点名称和图标的容器
        const siteHeader = document.createElement('div');
        siteHeader.style.cssText = `
          display: flex;
          align-items: center;
          margin-bottom: 4px;
        `;
        
        // 添加站点图标容器
        const siteIcon = document.createElement('div');
        siteIcon.style.cssText = `
          width: 16px;
          height: 16px;
          border-radius: 2px;
          margin-right: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 10px;
          font-weight: bold;
          overflow: hidden;
        `;
        
        // 获取站点名称
        const siteName = code.siteName || '未命名站点';
        
        // 使用首字母作为初始占位图标
        const letter = siteName.charAt(0).toUpperCase();
        const hue = Math.abs(letter.charCodeAt(0) * 5) % 360;
        siteIcon.textContent = letter;
        siteIcon.style.backgroundColor = `hsl(${hue}, 70%, 60%)`;
        siteIcon.style.color = 'white';
        
        // 尝试从URL获取图标
        if (code.urls && code.urls.length > 0) {
          fetchSiteIcon(code.urls[0], siteIcon);
        }
        
        // 添加站点名称
        const siteNameEl = document.createElement('div');
        siteNameEl.textContent = siteName;
        siteNameEl.style.cssText = 'font-size: 12px; color: #666; flex-grow: 1;';
        
        // 组装站点头部
        siteHeader.appendChild(siteIcon);
        siteHeader.appendChild(siteNameEl);
        codeItem.appendChild(siteHeader);
        
        const codeDisplay = document.createElement('div');
        codeDisplay.style.cssText = `
          font-family: monospace;
          font-size: 18px;
          font-weight: bold;
          color: #333;
          letter-spacing: 2px;
          text-align: center;
          margin: 4px 0;
        `;
        codeDisplay.textContent = code.code;

        // 添加进度条容器
        const progressContainer = document.createElement('div');
        progressContainer.style.cssText = `
          margin: 8px 0;
          position: relative;
          height: 4px;
          background: #e0e0e0;
          border-radius: 2px;
          overflow: hidden;
        `;

        // 添加进度条
        const progressBar = document.createElement('div');
        progressBar.style.cssText = `
          position: absolute;
          left: 0;
          top: 0;
          height: 100%;
          background: #4caf50;
          transition: width 1s linear;
          border-radius: 2px;
        `;
        
        // 添加剩余时间显示
        const timeDisplay = document.createElement('div');
        timeDisplay.style.cssText = `
          font-size: 11px;
          color: #666;
          text-align: center;
          margin-top: 2px;
        `;

        // 计算剩余时间和进度
        const updateProgress = () => {
          const now = Math.floor(Date.now() / 1000);
          const period = 30; // TOTP 默认周期为30秒
          const elapsed = now % period;
          const remaining = period - elapsed;
          const progress = (remaining / period) * 100;
          
          progressBar.style.width = `${progress}%`;
          timeDisplay.textContent = `${remaining}秒后更新`;
          
          // 当剩余时间小于5秒时改变颜色
          if (remaining <= 5) {
            progressBar.style.background = '#ff9800';
        } else {
            progressBar.style.background = '#4caf50';
          }
          
          // 当时间到时自动刷新
          if (remaining <= 1) {
            updateCodes();
          }
        };
        
        progressContainer.appendChild(progressBar);
        
        const copyButton = document.createElement('button');
        copyButton.textContent = '复制';
        copyButton.style.cssText = `
          border: none;
          background: #4caf50;
          color: white;
          border-radius: 4px;
          padding: 4px 8px;
          font-size: 12px;
          cursor: pointer;
          width: 100%;
          margin-top: 8px;
        `;
        copyButton.onclick = () => {
          navigator.clipboard.writeText(code.code);
          copyButton.textContent = '已复制';
          setTimeout(() => copyButton.textContent = '复制', 1000);
        };
        
        codeItem.appendChild(codeDisplay);
        codeItem.appendChild(progressContainer);
        codeItem.appendChild(timeDisplay);
        codeItem.appendChild(copyButton);
        content.appendChild(codeItem);
        
        // 启动进度条更新
        updateProgress();
        const progressInterval = setInterval(updateProgress, 1000);
        
        // 当元素被移除时清除定时器
        const observer = new MutationObserver((mutations) => {
          mutations.forEach((mutation) => {
            mutation.removedNodes.forEach((node) => {
              if (node === codeItem) {
                clearInterval(progressInterval);
                observer.disconnect();
              }
            });
          });
        });
        observer.observe(codeItem.parentNode, { childList: true });
    });
  } catch (error) {
      console.error('更新验证码失败:', error);
      // 根据错误类型显示不同的提示
      if (error.message.includes('授权失败')) {
        content.innerHTML = '<div style="color: #f44336; text-align: center; padding: 8px;">授权失败，请重新配置连接信息</div>';
      } else if (error.message.includes('未配置连接信息')) {
        content.innerHTML = '<div style="color: #f44336; text-align: center; padding: 8px;">请先配置连接信息</div>';
      } else if (error.message.includes('服务器错误')) {
        content.innerHTML = '<div style="color: #f44336; text-align: center; padding: 8px;">服务器暂时无法访问，请稍后重试</div>';
      } else {
        content.innerHTML = '<div style="color: #f44336; text-align: center; padding: 8px;">获取验证码失败，请刷新重试</div>';
      }
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
          // 创建canvas元素
          const canvas = document.createElement('canvas');
          const ctx = canvas.getContext('2d');
          canvas.width = img.width;
          canvas.height = img.height;
          
          // 将图像绘制到canvas上
          ctx.drawImage(img, 0, 0);
          
          // 将canvas内容转换为DataURL
          try {
            const dataUrl = canvas.toDataURL('image/png');
            
            // 更新图标
            iconElement.innerHTML = '';
            const iconImg = document.createElement('img');
            iconImg.src = dataUrl;
            iconImg.alt = 'Site Icon';
            iconImg.style.width = '100%';
            iconImg.style.height = '100%';
            iconElement.appendChild(iconImg);
          } catch (e) {
            console.error('转换图标格式失败:', e);
            tryFallbackIcon(domain, iconElement);
          }
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
  
  refreshButton.onclick = () => {
    refreshButton.textContent = '正在刷新...';
    refreshButton.style.opacity = '0.7';
    refreshButton.disabled = true;
    
    updateCodes().finally(() => {
      refreshButton.textContent = '刷新';
      refreshButton.style.opacity = '1';
      refreshButton.disabled = false;
    });
  };
  
  // 组装面板
  panel.appendChild(title);
  panel.appendChild(content);
  panel.appendChild(refreshButton);
  
  // 添加到页面
  document.body.appendChild(panel);
  
  // 初始更新验证码
  updateCodes();
  
  // 设置定时更新（每30秒）
  setInterval(updateCodes, 30000);
}

// 从API获取TOTP验证码
async function fetchTOTPCodes() {
  try {
    // 获取配置（从popup传入或用户手动输入）
    const config = await getApiConfig();
    
    if (!config || !config.baseUrl || !config.apiKey) {
      throw new Error('未配置连接信息');
    }
    
    // 直接从API获取验证码，不使用缓存
    const response = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/get_codes?apikey=${config.apiKey}`);
    if (!response.ok) {
      // 只有在明确的授权错误时才提示重新配置
      if (response.status === 401 || response.status === 403) {
        throw new Error('授权失败，请重新配置');
      }
      throw new Error(`服务器错误: ${response.status} ${response.statusText}`);
    }
    
    const data = await response.json();
    
    // 确保返回的是数组格式
    if (!data || !data.data) {
      return [];
    }
    
    // 如果data.data不是数组，尝试转换
    if (!Array.isArray(data.data)) {
      if (typeof data.data === 'object') {
        return Object.entries(data.data).map(([siteName, info]) => ({
          siteName,
          code: info.code,
          urls: info.urls || []
        }));
      }
      return [];
    }
    
    return data.data;
  } catch (error) {
    console.error('获取验证码失败:', error);
    throw error;
  }
}

// 从设置中获取API配置
async function getApiConfig() {
  // 尝试从popup.js传入的消息获取配置
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: 'getApiConfig' }, (response) => {
      if (response && response.config) {
        resolve(response.config);
      } else {
        // 如果没有获取到配置，从存储中读取
        chrome.storage.sync.get(['apiBaseUrl', 'apiKey'], (result) => {
          if (result.apiBaseUrl && result.apiKey) {
            resolve({
              baseUrl: result.apiBaseUrl,
              apiKey: result.apiKey
            });
          } else {
            // 最后尝试从localStorage获取
            try {
              const savedConfig = localStorage.getItem('totp_connection');
              if (savedConfig) {
                const parsedConfig = JSON.parse(savedConfig);
                if (parsedConfig.serverUrl && parsedConfig.apiKey) {
                  resolve({
                    baseUrl: parsedConfig.serverUrl,
                    apiKey: parsedConfig.apiKey
                  });
                } else {
                  resolve(null);
                }
              } else {
                resolve(null);
              }
            } catch (e) {
              console.warn('从localStorage获取配置失败:', e);
              resolve(null);
            }
          }
        });
      }
    });
  });
}

// 从页面响应提取验证码
function extractCodesFromPageResponse(response) {
  try {
    console.log('开始解析页面响应以提取验证码');
    
    if (!response) {
      console.error('响应为空');
      return {};
    }
    
    const result = {};
    
    // 如果不是数组，尝试包装成数组
    const formList = Array.isArray(response) ? response : [response];
    
    // 首先尝试按照组件结构提取
    for (let i = 0; i < formList.length; i++) {
      const form = formList[i];
      console.log(`分析第 ${i+1}/${formList.length} 个表单元素`);
      
      // 查找任何可能包含验证码的组件
      if (form && typeof form === 'object') {
        // 1. 先尝试VCard方式提取
        tryExtractFromCards(form, result);
        
        // 2. 如果没有找到，尝试div+VCardText方式提取
        if (Object.keys(result).length === 0) {
          tryExtractFromDiv(form, result);
        }
      }
    }
    
    // 如果结构化提取失败，尝试深度搜索
    if (Object.keys(result).length === 0) {
      console.log('结构化提取失败，尝试直接搜索...');
      findCodesDirectly(response, result);
    }
    
    console.log('提取完成，找到验证码:', result);
    return result;
  } catch (error) {
    console.error('提取验证码时出错:', error);
    return {};
  }
}

// 尝试从VCard结构中提取验证码
function tryExtractFromCards(form, result) {
  // 查找TOTP容器和VRow
  if (!form.component) {
    console.log('元素不是组件，跳过VCard方式提取');
    return;
  }
  
  // 可能的TOTP容器类型
  if (form.component === 'totp-container' || 
      (form.component.type === 'totp-container') || 
      (form.props && form.props.id === 'totp-container')) {
    console.log('找到TOTP容器');
    
    // 查找VRow组件
    const vRow = findComponentByType(form, 'VRow');
    if (!vRow) {
      console.log('未找到VRow组件，跳过');
      return;
    }
    
    console.log('找到VRow组件');
    
    // 提取VCol组件列表
    const vCols = findAllComponentsByType(vRow, 'VCol');
    console.log(`找到 ${vCols.length} 个VCol组件`);
    
    // 遍历每个VCol，查找VCard组件
    for (const vCol of vCols) {
      const vCard = findComponentByType(vCol, 'VCard');
      if (!vCard) {
        console.log('此VCol中没有VCard组件，跳过');
        continue;
      }
      
      // 从VCard中提取站点名称和验证码
      const info = extractSiteInfo(vCard);
      if (info && info.siteName && info.code) {
        result[info.siteName] = {
          code: info.code,
          remainingSeconds: info.remainingSeconds || 30,
          progressPercentage: info.progressPercentage || 100
        };
        console.log(`成功提取站点 ${info.siteName} 的验证码: ${info.code}`);
      }
    }
  } else {
    console.log('未找到TOTP容器，跳过VCard方式提取');
  }
}

// 尝试从div结构中提取验证码
function tryExtractFromDiv(form, result) {
  if (form.component !== 'div' || !form.content || !Array.isArray(form.content)) {
    console.log('非div组件或无内容，跳过div方式提取');
    return;
  }
  
  console.log('尝试从div结构中提取验证码');
  // 遍历div的内容
  for (let i = 0; i < form.content.length; i++) {
    const item = form.content[i];
    
    // 查找VCardText组件
    if (item && item.component === 'VCardText' && item.content && Array.isArray(item.content)) {
      console.log('找到VCardText组件');
      
      // 在VCardText中查找span
      for (let j = 0; j < item.content.length; j++) {
        const span = item.content[j];
        if (span && 
            span.component === 'span' && 
            span.props && 
            span.props.id && 
            span.props.id.startsWith('code-') && 
            span.text && 
            span.text.match(/^\d{6,8}$/)) {
          
          const siteName = span.props.id.substring(5); // 去掉"code-"前缀
          console.log(`在VCardText中找到验证码span: ${siteName} - ${span.text}`);
          result[siteName] = {
            code: span.text,
            remainingSeconds: 30,
            progressPercentage: 100
          };
        }
      }
    }
  }
}

// 查找指定类型的组件
function findComponentByType(parent, type) {
  if (!parent || !parent.component) return null;
  
  if (parent.component.type === type) {
    return parent;
  }
  
  if (parent.content && Array.isArray(parent.content)) {
    for (const child of parent.content) {
      const found = findComponentByType(child, type);
      if (found) return found;
    }
  }
  
  return null;
}

// 查找所有指定类型的组件
function findAllComponentsByType(parent, type) {
  const results = [];
  
  if (!parent || !parent.component) return results;
  
  if (parent.component.type === type) {
    results.push(parent);
  }
  
  if (parent.content && Array.isArray(parent.content)) {
    for (const child of parent.content) {
      const found = findAllComponentsByType(child, type);
      results.push(...found);
    }
  }
  
  return results;
}

// 从VCard中提取站点信息
function extractSiteInfo(vCard) {
  try {
    if (!vCard || !vCard.component) return null;
    
    let siteName = null;
    let code = null;
    let remainingSeconds = null;
    let progressPercentage = null;
    
    // 查找h3标题元素
    const h3 = findComponentByType(vCard, 'h3');
    if (h3 && h3.content && h3.content.length > 0) {
      siteName = h3.content[0];
      console.log('找到站点名称:', siteName);
    }
    
    // 查找code-XXX元素，通常包含验证码
    const codeElements = findComponentsWithPattern(vCard, 'code-');
    if (codeElements.length > 0) {
      for (const codeEl of codeElements) {
        if (codeEl.component && codeEl.component.props && codeEl.component.props.id) {
          const idParts = codeEl.component.props.id.split('-');
          // 确保id格式为code-sitename
          if (idParts.length >= 2 && idParts[0] === 'code') {
            // 如果之前没找到站点名，用id中的站点名
            if (!siteName) {
              siteName = idParts.slice(1).join('-');
            }
            
            // 提取验证码内容
            if (codeEl.content && codeEl.content.length > 0) {
              code = codeEl.content[0];
              console.log(`找到站点 ${siteName} 的验证码:`, code);
            }
          }
        }
      }
    }
    
    // 查找进度条和剩余时间
    const progressBar = findComponentByType(vCard, 'VProgressLinear');
    if (progressBar && progressBar.component && progressBar.component.props) {
      progressPercentage = progressBar.component.props.value;
      console.log(`找到进度百分比: ${progressPercentage}%`);
    }
    
    const timeText = findComponentWithText(vCard, '秒');
    if (timeText && timeText.content && timeText.content.length > 0) {
      const timeString = timeText.content[0];
      const match = timeString.match(/(\d+)\s*秒/);
      if (match && match[1]) {
        remainingSeconds = parseInt(match[1], 10);
        console.log(`找到剩余时间: ${remainingSeconds}秒`);
      }
    }
    
    return { 
      siteName, 
      code, 
      remainingSeconds, 
      progressPercentage 
    };
  } catch (error) {
    console.error('提取站点信息时出错:', error);
    return null;
  }
}

// 查找ID或class包含特定模式的组件
function findComponentsWithPattern(parent, pattern) {
  const results = [];
  
  if (!parent || !parent.component) return results;
  
  if (parent.component.props) {
    const props = parent.component.props;
    if ((props.id && props.id.includes(pattern)) || 
        (props.class && props.class.includes(pattern))) {
      results.push(parent);
    }
  }
  
  if (parent.content && Array.isArray(parent.content)) {
    for (const child of parent.content) {
      const found = findComponentsWithPattern(child, pattern);
      results.push(...found);
    }
  }
  
  return results;
}

// 查找包含特定文本的组件
function findComponentWithText(parent, text) {
  if (!parent) return null;
  
  if (parent.content && Array.isArray(parent.content)) {
    for (const item of parent.content) {
      if (typeof item === 'string' && item.includes(text)) {
        return parent;
      }
    }
    
    for (const child of parent.content) {
      const found = findComponentWithText(child, text);
      if (found) return found;
    }
  }
  
  return null;
}

// 直接在响应中查找验证码
function findCodesDirectly(response, result) {
  console.log('开始直接搜索验证码...');
  
  // 递归搜索对象中的所有id
  function searchObject(obj, path = '') {
    if (!obj) return;
    
    if (typeof obj === 'object' && obj !== null) {
      // 检查整个对象
      if (obj.component === 'div' && obj.content && Array.isArray(obj.content)) {
        // 尝试在div的内容中找VCardText
        for (let i = 0; i < obj.content.length; i++) {
          const item = obj.content[i];
          if (item && item.component === 'VCardText' && item.content && Array.isArray(item.content)) {
            // 检查VCardText的内容中是否有span
            for (let j = 0; j < item.content.length; j++) {
              const span = item.content[j];
              if (span && 
                  span.component === 'span' && 
                  span.props && 
                  span.props.id && 
                  span.props.id.startsWith('code-') && 
                  span.text && 
                  span.text.match(/^\d{6,8}$/)) {
                
                const siteName = span.props.id.substring(5); // 去掉"code-"前缀
                console.log(`找到验证码span: ${siteName} - ${span.text}, 路径: ${path}.content[${i}].content[${j}]`);
                result[siteName] = {
                  code: span.text,
                  remainingSeconds: 30,
                  progressPercentage: 100
                };
              }
            }
          }
        }
      }
      
      // 检查是否是包含验证码的span
      if (obj.component === 'span' && 
          obj.props && 
          obj.props.id && 
          obj.props.id.startsWith('code-') && 
          obj.text && 
          obj.text.match(/^\d{6,8}$/)) {
        
        const siteName = obj.props.id.substring(5); // 去掉"code-"前缀
        console.log(`直接找到span元素中的验证码: ${siteName} - ${obj.text}, 路径: ${path}`);
        result[siteName] = {
          code: obj.text,
          remainingSeconds: 30,
          progressPercentage: 100
        };
        return;
      }
      
      // 查找code-XXX格式的ID
      if (obj.props && obj.props.id && obj.props.id.startsWith('code-')) {
        const siteName = obj.props.id.substring(5); // 去掉"code-"前缀
        
        // 查找内容，可能是兄弟节点或子节点
        let codeValue = null;
        if (obj.content && Array.isArray(obj.content) && obj.content.length > 0) {
          if (typeof obj.content[0] === 'string') {
            codeValue = obj.content[0];
          } else if (typeof obj.text === 'string') {
            codeValue = obj.text;
          }
        } else if (typeof obj.text === 'string') {
          codeValue = obj.text;
        }
        
        if (codeValue && codeValue.match(/^\d{6,8}$/)) {
          console.log(`直接搜索找到站点 ${siteName} 的验证码: ${codeValue}, 路径: ${path}`);
          result[siteName] = {
            code: codeValue,
            remainingSeconds: 30, // 默认值
            progressPercentage: 100 // 默认值
          };
        }
      }
      
      // 递归搜索所有属性
      for (const key in obj) {
        const newPath = path ? `${path}.${key}` : key;
        searchObject(obj[key], newPath);
      }
    } else if (Array.isArray(obj)) {
      obj.forEach((item, index) => {
        const newPath = `${path}[${index}]`;
        searchObject(item, newPath);
      });
    }
  }
  
  // 开始搜索
  searchObject(response);
  
  // 如果还是没找到，尝试在response是数组且只有一个元素时在它的content中搜索
  if (Object.keys(result).length === 0 && Array.isArray(response) && response.length === 1) {
    const firstItem = response[0];
    if (firstItem && firstItem.content && Array.isArray(firstItem.content)) {
      console.log('尝试在第一个元素的content中搜索');
      firstItem.content.forEach((item, index) => {
        searchObject(item, `content[${index}]`);
      });
    }
  }
  
  // 尝试直接解析整个响应的字符串形式
  if (Object.keys(result).length === 0) {
    console.log('尝试从响应字符串中提取验证码');
    try {
      const responseStr = JSON.stringify(response);
      
      // 直接匹配id和text模式
      const pattern = /"id":\s*"code-([^"]+)".*?"text":\s*"(\d{6,8})"/g;
      let match;
      while ((match = pattern.exec(responseStr)) !== null) {
        const siteName = match[1];
        const code = match[2];
        console.log(`从字符串中提取到验证码: ${siteName} - ${code}`);
        result[siteName] = {
          code: code,
          remainingSeconds: 30,
          progressPercentage: 100
        };
      }
      
      // 如果上面的方法没找到，尝试另一种匹配方式
      if (Object.keys(result).length === 0) {
        const codeMatches = responseStr.match(/code-([a-zA-Z0-9_]+).*?text":[ ]*"(\d{6,8})"/g);
        if (codeMatches && codeMatches.length > 0) {
          for (const match of codeMatches) {
            const siteMatch = match.match(/code-([a-zA-Z0-9_]+)/);
            const codeMatch = match.match(/text":[ ]*"(\d{6,8})"/);
            if (siteMatch && siteMatch[1] && codeMatch && codeMatch[1]) {
              const siteName = siteMatch[1];
              const code = codeMatch[1];
              console.log(`从字符串中提取到验证码: ${siteName} - ${code}`);
              result[siteName] = {
                code: code,
                remainingSeconds: 30,
                progressPercentage: 100
              };
            }
          }
        }
      }
    } catch (error) {
      console.error('从字符串提取验证码失败:', error);
    }
  }
  
  // 如果仍然没找到，直接输出完整响应，帮助调试
  if (Object.keys(result).length === 0) {
    console.log('无法提取验证码，完整响应内容:', JSON.stringify(response, null, 2));
  }
  
  console.log('直接搜索完成，结果:', result);
}
