// 当前页面URL
const currentUrl = window.location.href;

// 全局变量，防止重复弹出
let panelShown = false;
let isTotpInitialized = false;

// 添加全局配置对象
let globalConfig = null;
let lastConfigRefreshTime = 0;
const CONFIG_REFRESH_INTERVAL = 300000; // 配置刷新间隔，5分钟

// 全局变量，控制验证码刷新
let isExpiredRefreshing = false; // 控制过期刷新状态

// 监听页面加载完成
document.addEventListener('DOMContentLoaded', function() {
  // 只在页面首次加载时初始化TOTP
  if (!isTotpInitialized) {
    setTimeout(checkAndInitTOTP, 1000);
    isTotpInitialized = true;
  }
});

// 防止重复检查的标志
let isCheckingTOTP = false;

// 监听DOM变化，以便在动态加载的页面上添加按钮
const mutationObserver = new MutationObserver(function(mutations) {
  // 只有在未显示面板且未初始化时才检查
  if (!panelShown && !document.querySelector('.totp-helper-panel') && !isCheckingTOTP && !isTotpInitialized) {
    clearTimeout(window.totpCheckTimer);
    window.totpCheckTimer = setTimeout(() => {
      checkAndInitTOTP();
      isTotpInitialized = true;
    }, 1000);
  }
});

// 配置观察器，只在没有初始化时观察
if (!isTotpInitialized) {
mutationObserver.observe(document.body, {
  childList: true,
  subtree: true
});
}

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
    'form[action*="security"] input[type="text"]',
    // 特殊验证页面的输入框 - 适用于示例中的情况
    '.input-content .input-item',  // 包含多个子输入框的布局
    '.input-wrap .input-content .input-item', // 更具体的嵌套结构
    '.input-wrap input.visible',   // 某些站点用于验证码的特殊输入框
    // 常见的多个单字符输入框组合
    'input[type="text"][maxlength="1"]:not([style*="display: none"])',
    'input[type="number"][maxlength="1"]:not([style*="display: none"])'
  ];
  
  // 尝试所有选择器
  let matchedInputs = [];
  for (const selector of selectors) {
    const inputs = document.querySelectorAll(selector);
    if (inputs.length > 0) {
      inputs.forEach(input => matchedInputs.push(input));
    }
  }
  
  // 检查是否有特殊的验证码布局 - 多个连续输入框
  if (matchedInputs.length === 0) {
    const multipleInputs = findMultipleInputsGroup();
    if (multipleInputs && multipleInputs.length >= 4 && multipleInputs.length <= 8) {
      matchedInputs = multipleInputs;
    }
  }
  
  // 如果找到的是包装了多个输入字段的单个容器，尝试找出实际的输入字段
  if (matchedInputs.length === 1 && matchedInputs[0].classList.contains('input-content')) {
    const container = matchedInputs[0];
    const subInputs = container.querySelectorAll('.input-item');
    if (subInputs.length > 0) {
      matchedInputs = Array.from(subInputs);
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
      
      // 检查周围上下文
      const surroundingText = getSurroundingText(input);
      if (surroundingText.includes('验证码') || 
          surroundingText.includes('authentication') ||
          surroundingText.includes('verification code')) {
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
  
  // 如果是GitHub，只在验证页面上检测输入框
  if (window.location.hostname.includes('github.com')) {
    // 只有在二步验证页面才返回输入框
    if (!isGitHubAuthPage()) {
      return [];
    }
  }
  
  // 返回找到的输入框
  return matchedInputs;
}

// 查找多个连续的输入框组 - 适用于将验证码分成单个数字输入的情况
function findMultipleInputsGroup() {
  // 查找所有可能是验证码一部分的单字符输入框
  const potentialInputs = document.querySelectorAll('input[type="text"][maxlength="1"], input[type="number"][maxlength="1"]');
  if (potentialInputs.length < 4) return null;
  
  // 转换为数组
  const inputs = Array.from(potentialInputs);
  
  // 找到在DOM中连续的输入框组
  for (let i = 0; i < inputs.length - 3; i++) {
    // 检查是否至少有4个连续的输入框
    let consecutive = 1;
    for (let j = i; j < i + 5 && j < inputs.length - 1; j++) {
      // 检查两个输入框是否相邻或处于同一容器中
      if (areInputsRelated(inputs[j], inputs[j+1])) {
        consecutive++;
      } else {
        break;
      }
    }
    
    if (consecutive >= 4) {
      // 返回找到的连续输入框组
      return inputs.slice(i, i + consecutive);
    }
  }
  
  return null;
}

// 检查两个输入框是否相关联 (相邻或在同一容器内)
function areInputsRelated(input1, input2) {
  // 检查是否有共同的父容器
  let commonParent = input1.parentElement;
  for (let i = 0; i < 3 && commonParent; i++) {
    if (commonParent.contains(input2)) {
      return true;
    }
    commonParent = commonParent.parentElement;
  }
  
  // 检查是否相邻
  return input1.nextElementSibling === input2 || 
         input2.previousElementSibling === input1;
}

// 获取输入框周围的文本内容
function getSurroundingText(element) {
  // 获取包含该元素的表单或相近容器
  const container = element.closest('form') || element.parentElement?.parentElement;
  if (!container) return '';
  
  // 提取容器中的文本
  return container.textContent.toLowerCase();
}

// 检查是否是GitHub的验证页面
function isGitHubAuthPage() {
  const path = window.location.pathname;
  return path.includes('/sessions/two-factor') || 
         path.includes('/sessions/verification') ||
         path.includes('/authentication/verify');
}

// 主函数：检查并初始化TOTP
async function checkAndInitTOTP() {
  try {
    // 如果已经显示过面板或正在检查，不再重复显示
    if (panelShown || document.querySelector('.totp-helper-panel') || isCheckingTOTP) {
      return;
    }
    
    isCheckingTOTP = true;

    // 0. 检查当前页面是否需要验证码
    if (!isValidAuthPage()) {
      isCheckingTOTP = false;
      stopAllScansAndObservers();
      return;
    }

    // 1. 获取当前域名
    const currentDomain = window.location.hostname.toLowerCase();
    
    // 2. 获取配置的站点列表
    const result = await getApiConfig();
    if (!result || !result.sites || Object.keys(result.sites).length === 0) {
      isCheckingTOTP = false;
      stopAllScansAndObservers();
      return;
    }
    
    // 3. 检查当前域名是否匹配任何配置的站点
    let matchedSite = null;
    
    for (const [siteName, siteData] of Object.entries(result.sites)) {
      if (siteData.urls && Array.isArray(siteData.urls)) {
        for (const url of siteData.urls) {
          try {
            // 处理URL，确保它有协议前缀
            let fullUrl = url;
            if (!url.startsWith('http://') && !url.startsWith('https://')) {
              fullUrl = 'https://' + url;
            }
            
            // 解析URL获取域名
            const siteUrlObj = new URL(fullUrl);
            const siteDomain = siteUrlObj.hostname.toLowerCase();
            
            // 使用包含匹配，而不是精确匹配
            if (currentDomain === siteDomain || 
                currentDomain.includes(siteDomain) || 
                siteDomain.includes(currentDomain)) {
              matchedSite = {
                name: siteName,
                data: siteData
              };
          break;
        }
          } catch (e) {
            // 尝试直接比较域名部分
            const urlLower = url.toLowerCase();
            if (urlLower.includes(currentDomain) || currentDomain.includes(urlLower)) {
              matchedSite = {
                name: siteName,
                data: siteData
              };
              break;
            }
          }
        }
      }
      if (matchedSite) break;
    }
    
    // 如果当前域名不匹配任何配置的站点，不显示面板
    if (!matchedSite) {
      isCheckingTOTP = false;
      stopAllScansAndObservers();
      return;
    }
    
    // 4. 检查页面是否有二级验证输入框
    const inputs = findOTPInput();
    if (!inputs || inputs.length === 0) {
      isCheckingTOTP = false;
      return;
    }
    
    // 5. 显示弹出面板
    createOTPPanel();
    panelShown = true;
    
    // 如果成功初始化，断开MutationObserver
    mutationObserver.disconnect();
    
  } catch (error) {
    console.error('初始化TOTP助手失败:', error);
  } finally {
    isCheckingTOTP = false;
  }
}

// 停止所有扫描和观察器
function stopAllScansAndObservers() {
  // 停止所有定时器
  if (window.totpUpdateTimer) {
    clearInterval(window.totpUpdateTimer);
    window.totpUpdateTimer = null;
  }
  
  if (window.totpCheckTimer) {
    clearTimeout(window.totpCheckTimer);
    window.totpCheckTimer = null;
  }
  
  // 断开所有观察器
  if (mutationObserver) {
    mutationObserver.disconnect();
  }
  
  // 用于停止initTOTPHelper中的定期扫描
  window.stopPeriodicScan = true;
}

// 检查当前页面是否需要验证码
function isValidAuthPage() {
  const url = window.location.href;
  const domain = window.location.hostname;
  const path = window.location.pathname;
  
  // 特定网站的验证码页面路径
  const authPaths = {
    'github.com': ['/sessions/two-factor', '/authentication/verify'],
    'gitlab.com': ['/users/sign_in', '/users/two_factor_auth'],
    'bitbucket.org': ['/account/two-step-verification'],
    'microsoft.com': ['/auth/requires-two-factor'],
    'live.com': ['/login.srf'],
    'office.com': ['/logincallback'],
    'zhuque.in': ['/login.php', '/auth/login', '/auth.php'],
    'piggo.me': ['/login.php', '/auth/login', '/auth.php'],
    'pterclub.com': ['/login.php', '/auth/login', '/auth.php'],
    '1ptba.com': ['/login.php', '/auth/login', '/auth.php']
  };
  
  // 通用验证码页面URL关键词
  const authKeywords = [
    'two-factor', 'two_factor', '2fa', 'two-step', 'verification', 
    'authenticate', 'security-code', 'otp', 'mfa', 'multi-factor',
    'login.php?2fa=1', 'auth.php?code=1'
  ];
  
  // 1. 检查是否匹配特定站点的验证码页面路径
  for (const site in authPaths) {
    if (domain.includes(site)) {
      if (authPaths[site].some(authPath => path.includes(authPath))) {
        return true;
      }
    }
  }
  
  // 2. 检查URL是否包含验证码关键词
  if (authKeywords.some(keyword => url.toLowerCase().includes(keyword))) {
    return true;
  }
  
  // 3. 检查页面内容是否包含验证码相关文本
  const bodyText = document.body.innerText.toLowerCase();
  const authTexts = [
    'verification code', 'security code', 'two-factor', 'two factor',
    '2fa', 'authenticator', 'authentication code', 'totp', 
    '二步验证', '两步验证', '验证码', '安全验证', '双重验证',
    'enter the code'
  ];
  
  if (authTexts.some(text => bodyText.includes(text.toLowerCase()))) {
    return true;
  }
  
  // 4. 检查表单标题或结构
  const formTitles = document.querySelectorAll('h1, h2, h3, h4, h5, h6, legend, .layui-field-title');
  for (const title of formTitles) {
    const titleText = title.textContent.toLowerCase();
    if (titleText.includes('验证') || 
        titleText.includes('安全') || 
        titleText.includes('verification') || 
        titleText.includes('security') ||
        titleText.includes('authentication')) {
      return true;
    }
  }
  
  // 5. PT站特有的样式特征
  const ptAuthElements = document.querySelectorAll('.layui-tab-title, #input-form-box, .input-wrap');
  if (ptAuthElements.length > 0) {
    return true;
  }
  
  // 没有匹配任何验证页面特征
  return false;
}

// 创建验证码展示面板
function createOTPPanel() {
  // 确保页面中只有一个面板
  const existingPanel = document.querySelector('.totp-helper-panel');
  if (existingPanel) {
    return;
  }
  
  // 创建面板容器
  const panel = document.createElement('div');
  panel.className = 'totp-helper-panel';
  panel.id = 'totp-helper-panel';
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
  closeButton.onclick = () => {
    panel.remove();
    // 重置面板显示标记，允许在下次条件满足时再次显示
    panelShown = false;
    isTotpInitialized = false;
    
    // 清除所有定时器
    if (window.totpUpdateTimer) {
      clearInterval(window.totpUpdateTimer);
      window.totpUpdateTimer = null;
    }
    if (window.totpCheckTimer) {
      clearTimeout(window.totpCheckTimer);
      window.totpCheckTimer = null;
    }
  };
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
  let lastUpdateTime = 0;
  const MIN_UPDATE_INTERVAL = 5000; // 最小更新间隔，5秒
  
  async function updateCodes(forceRefresh = false) {
    try {
      const now = Date.now();
      
      // 非强制刷新时限制更新频率
      if (!forceRefresh && now - lastUpdateTime < MIN_UPDATE_INTERVAL) {
      return;
    }
    
      lastUpdateTime = now;
      
      const result = await fetchTOTPCodes(forceRefresh);
      const { codes, sites } = result;
      content.innerHTML = '';
      
      // 获取当前域名
      const domain = window.location.hostname;
      let matchedCodes = [];
      
      // 处理数据格式
      if (Array.isArray(codes)) {
        // 数组格式处理
        matchedCodes = codes.filter(code => 
          code.urls && Array.isArray(code.urls) && code.urls.some(url => url.includes(domain))
        );
      } else {
        // 对象格式处理
        matchedCodes = Object.entries(codes)
          .filter(([siteName, codeData]) => 
            codeData.urls && Array.isArray(codeData.urls) && codeData.urls.some(url => url.includes(domain))
          )
          .map(([siteName, codeData]) => ({
            siteName,
            ...codeData
          }));
      }
      
      if (matchedCodes.length === 0) {
        content.innerHTML = '<div style="color: #999; text-align: center; padding: 8px;">未找到匹配的验证码</div>';
        return;
      }
      
      matchedCodes.forEach(code => {
        // 确定站点名称
        const siteName = code.siteName || '未命名站点';
        
        // 获取站点配置（包含图标）
        const siteConfig = sites[siteName] || {};
        
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
          background-color: #ffffff;
          border: 1px solid #e0e0e0;
          color: #757575;
        `;
        
        // 优先使用配置中的base64图标
        if (siteConfig.icon && siteConfig.icon.startsWith('data:image')) {
          siteIcon.innerHTML = '';
          const iconImg = document.createElement('img');
          iconImg.src = siteConfig.icon;
          iconImg.alt = 'Site Icon';
          iconImg.style.cssText = 'width: 100%; height: 100%; object-fit: cover;';
          siteIcon.appendChild(iconImg);
        } else {
          // 如果没有base64图标，使用首字母作为占位
          const letter = siteName.charAt(0).toUpperCase();
          siteIcon.textContent = letter;
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
          const progress = (elapsed / period) * 100;
          
          progressBar.style.width = `${100 - progress}%`;
          timeDisplay.textContent = `${remaining}秒后更新`;
          
          // 当剩余时间小于5秒时改变颜色
          if (remaining <= 5) {
            progressBar.style.background = '#ff9800';
          } else {
            progressBar.style.background = '#4caf50';
          }
          
          // 当时间完全归零后，设置过期标志，小延迟后刷新
          if (remaining === 0 && !isExpiredRefreshing) {
            isExpiredRefreshing = true;
            
            // 延迟1秒后刷新，确保在过期后但不是立即刷新
            setTimeout(() => {
              updateCodes(true); // 强制刷新
              isExpiredRefreshing = false;
            }, 1000);
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
          
          // 显示复制成功消息
          const successMsg = document.createElement('div');
          successMsg.textContent = '验证码已复制到剪贴板';
          successMsg.style.cssText = `
            font-size: 11px;
            color: #4caf50;
            text-align: center;
            margin-top: 4px;
          `;
          
          // 避免重复添加消息
          const existingMsg = codeItem.querySelector('.copy-success-msg');
          if (existingMsg) {
            existingMsg.remove();
          }
          
          successMsg.className = 'copy-success-msg';
          codeItem.appendChild(successMsg);
          
          setTimeout(() => {
            copyButton.textContent = '复制';
            if (successMsg.parentNode) {
              successMsg.remove();
            }
          }, 2000);
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
    
    // 点击刷新按钮时强制刷新
    updateCodes(true).finally(() => {
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
  
  // 设置全局标志
  panelShown = true;
  
  // 初始更新验证码
  updateCodes();
  
  // 设置定时更新（每30秒）
  // 存储定时器ID以便能够清除
  if (window.totpUpdateTimer) {
    clearInterval(window.totpUpdateTimer);
  }
  window.totpUpdateTimer = setInterval(updateCodes, 30000);
}

// 获取API配置
async function getApiConfig() {
  return new Promise((resolve) => {
    // 如果已经有全局配置且未过期，直接使用缓存
    const now = Date.now();
    if (globalConfig && (now - lastConfigRefreshTime < CONFIG_REFRESH_INTERVAL)) {
      resolve(globalConfig);
      return;
    }
    
    chrome.storage.sync.get(['apiBaseUrl', 'apiKey', 'apiConfig'], async (result) => {
      let config = {};
      
      // 检查主要配置
      if (result.apiBaseUrl && result.apiKey) {
        config = {
          baseUrl: result.apiBaseUrl,
          apiKey: result.apiKey,
          sites: {}
        };
      } else if (result.apiConfig && result.apiConfig.baseUrl && result.apiConfig.apiKey) {
        config = {
          baseUrl: result.apiConfig.baseUrl,
          apiKey: result.apiConfig.apiKey,
          sites: {}
        };
      } else {
        resolve(null);
      return;
    }
    
      // 尝试从API获取站点配置
      try {
        const configResponse = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/config?apikey=${config.apiKey}`);
        if (configResponse.ok) {
          const configData = await configResponse.json();
          if (configData && configData.data) {
            config.sites = configData.data;
            
            // 更新全局配置和刷新时间
            globalConfig = config;
            lastConfigRefreshTime = now;
          }
        }
      } catch (configError) {
        console.error('获取站点配置出错:', configError);
      }
      
      resolve(config);
    });
  });
}

// 从API获取TOTP验证码
let cachedCodes = null;
let lastCodeFetchTime = 0;
const CODE_FETCH_INTERVAL = 25000; // 25秒缓存时间

async function fetchTOTPCodes(forceRefresh = false) {
  try {
    const now = Date.now();
    
    // 只在非强制刷新时使用缓存
    if (!forceRefresh && cachedCodes && (now - lastCodeFetchTime < CODE_FETCH_INTERVAL)) {
      return cachedCodes;
    }
    
    // 获取配置
    const config = await getApiConfig();
    
    if (!config || !config.baseUrl || !config.apiKey) {
      throw new Error('未配置连接信息');
    }
    
    // 获取验证码
    const response = await fetch(`${config.baseUrl}/api/v1/plugin/twofahelper/get_codes?apikey=${config.apiKey}`);
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('授权失败，请重新配置');
      }
      throw new Error(`服务器错误: ${response.status} ${response.statusText}`);
    }
    
    const data = await response.json();
    
    if (!data || !data.data) {
      throw new Error('无效的验证码数据');
    }
    
    // 更新缓存
    cachedCodes = {
      codes: data.data,
      sites: config.sites
    };
    lastCodeFetchTime = now;
    
    return cachedCodes;
  } catch (error) {
    console.error('获取验证码失败:', error);
    throw error;
  }
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

// 自动填充验证码到输入框
function fillCodeToInputs(code) {
  // 禁用自动填充功能
  console.log('自动填充功能已禁用，仅显示验证码面板供用户复制');
  return false;
}

// 自动提交验证码
function tryAutoSubmit() {
  // 常见的提交按钮选择器
  const buttonSelectors = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button.submit',
    'button.confirm',
    'button.verify',
    'button.layui-btn',
    'button:contains("提交")',
    'button:contains("验证")',
    'button:contains("Submit")',
    'button:contains("Verify")'
  ];
  
  // 尝试所有选择器
  for (const selector of buttonSelectors) {
    try {
      const buttons = document.querySelectorAll(selector);
      if (buttons.length > 0) {
        // 找到了可能的提交按钮，但不自动点击
        // 只记录找到的按钮，让用户手动点击
        console.log('找到可能的提交按钮:', buttons);
        return true;
      }
    } catch (e) {
      // 某些选择器可能不支持，忽略错误
    }
  }
  
  return false;
}

// 初始化TOTP助手
function initTOTPHelper() {
  // 重置停止标志
  window.stopPeriodicScan = false;
  
  // 监听页面加载完成
  document.addEventListener('DOMContentLoaded', function() {
    // 延迟检查，确保页面元素已完全加载
    setTimeout(() => {
      checkPTVerificationForm();
    }, 500);
  });
  
  // 定义一个函数检查PT站验证框
  function checkPTVerificationForm() {
    if (panelShown || document.querySelector('.totp-helper-panel')) {
      return false;
    }
    
    // 先检查特定的input-wrap结构
    const inputWrap = document.querySelector('.input-wrap');
    const inputFormBox = document.querySelector('#input-form-box');
    
    if (inputWrap || inputFormBox) {
      createOTPPanel();
      panelShown = true;
      return true;
    }
    
    // 如果没找到，则尝试正常的TOTP检查
    if (!isTotpInitialized) {
      setTimeout(checkAndInitTOTP, 500);
      isTotpInitialized = true;
    }
    
    return false;
  }
  
  // 创建一个DOM监视器，监控验证框的出现
  const formObserver = new MutationObserver(function(mutations) {
    if (panelShown || document.querySelector('.totp-helper-panel') || window.stopPeriodicScan) {
      return;
    }
    
    for (const mutation of mutations) {
      if (mutation.type === 'childList') {
        // 检查是否有新添加的input-wrap或input-form-box元素
        const addedNodes = Array.from(mutation.addedNodes);
        for (const node of addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            if ((node.classList && node.classList.contains('input-wrap')) || 
                (node.id === 'input-form-box')) {
              createOTPPanel();
              panelShown = true;
              return;
            }
            
            // 检查子元素
            if (node.querySelector) {
              const foundInputWrap = node.querySelector('.input-wrap');
              const foundInputFormBox = node.querySelector('#input-form-box');
              if (foundInputWrap || foundInputFormBox) {
                createOTPPanel();
                panelShown = true;
                return;
              }
            }
          }
        }
      }
    }
  });
  
  // 开始观察DOM变化
  formObserver.observe(document.body, {
    childList: true,
    subtree: true
  });
  
  // 立即进行第一次检查
  setTimeout(checkPTVerificationForm, 300);
  
  // 定期扫描，防止其他检测方法失效
  let scanCount = 0;
  const maxScans = 10; // 最多扫描10次
  
  const periodicScan = setInterval(() => {
    // 如果设置了停止标志，立即停止扫描
    if (window.stopPeriodicScan) {
      clearInterval(periodicScan);
      return;
    }
    
    scanCount++;
    
    if (panelShown || document.querySelector('.totp-helper-panel')) {
      clearInterval(periodicScan);
      return;
    }
    
    if (scanCount >= maxScans) {
      clearInterval(periodicScan);
      return;
    }
    
    // 检查页面中的PT站验证框
    const inputWrap = document.querySelector('.input-wrap');
    const inputFormBox = document.querySelector('#input-form-box');
    
    if (inputWrap || inputFormBox) {
      createOTPPanel();
      panelShown = true;
      clearInterval(periodicScan);
    }
  }, 1500); // 每1.5秒扫描一次
  
  // 常规的DOM变化观察，用于其他类型的验证页面
  const mutationObserver = new MutationObserver(function(mutations) {
    // 如果设置了停止标志，不再处理
    if (window.stopPeriodicScan) {
      return;
    }
    
    // 只有在未显示面板且未初始化时才检查
    if (!panelShown && !document.querySelector('.totp-helper-panel') && !isCheckingTOTP && !isTotpInitialized) {
      clearTimeout(window.totpCheckTimer);
      window.totpCheckTimer = setTimeout(() => {
        // 再次检查PT站结构
        if (!checkPTVerificationForm()) {
          checkAndInitTOTP();
        }
        isTotpInitialized = true;
      }, 1000);
    }
  });
  
  // 配置观察器
  mutationObserver.observe(document.body, {
    childList: true,
    subtree: true
  });
}

// 添加全局辅助函数，允许用户手动触发
window.showTOTPHelper = function() {
  if (!panelShown && !document.querySelector('.totp-helper-panel')) {
    createOTPPanel();
    panelShown = true;
    return '已显示TOTP助手面板，请查看右下角';
  } else {
    return 'TOTP助手面板已经显示';
  }
};

// 简化初始化消息
console.log('TOTP助手已加载，如需手动显示面板，请在控制台执行: window.showTOTPHelper()');

// 启动初始化
initTOTPHelper();
