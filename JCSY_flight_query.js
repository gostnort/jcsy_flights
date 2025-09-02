// ==UserScript==
// @name         JCSY航班自动查询工具
// @namespace    http://tampermonkey.net/
// @version      0.7
// @description  在原始JCSY文本的ARVL列中就地回填查询结果，并完美对齐格式。
// @author       You
// @match        *://*.google.com/*
// @icon         https://www.google.com/favicon.ico
// @grant        GM_addStyle
// @run-at       document-end
// @noframes
// ==/UserScript==

(function () {
    'use strict';

    // --- [1] 配置项 ---
    // 在这里配置脚本的核心参数。
    const DESTINATION_CITY = 'Los Angeles'; // 目标城市名称，用于在搜索结果中验证航班信息。

    // --- [2] CSS 样式 ---
    // 通过 GM_addStyle 注入CSS，美化UI界面。
    GM_addStyle(`
      #gsh-panel {
        position: fixed; bottom: 20px; right: 20px; width: 455px;
        background: #fff; color: #111; border: 1px solid rgba(0,0,0,0.1);
        border-radius: 10px; box-shadow: 0 12px 32px rgba(0,0,0,0.2);
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
        z-index: 2147483647; display: block;
      }
      #gsh-header {
        display: flex; justify-content: space-between; align-items: center;
        padding: 10px 12px; font-weight: 600; background: #f6f8fb;
        border-bottom: 1px solid rgba(0,0,0,0.06); border-radius: 10px 10px 0 0;
        cursor: move; user-select: none;
      }
      #gsh-close {
        cursor: pointer; font-size: 22px; color: #888; font-weight: 600;
        line-height: 1; padding: 0 4px; border-radius: 4px;
      }
      #gsh-close:hover { background-color: #e8eaed; color: #111; }
      #gsh-body { padding: 12px; }
      #gsh-q {
        width: 100%; box-sizing: border-box; padding: 10px 12px;
        border: 1px solid #d0d7de; border-radius: 8px; outline: none;
        font-size: 10px;
        font-family: "Courier New", Courier, monospace;
        resize: vertical; min-height: 150px;
      }
      #gsh-q:focus { border-color: #1a73e8; box-shadow: 0 0 0 3px rgba(26,115,232,0.15); }
      #gsh-buttons { display: flex; margin-top: 10px; gap: 10px; }
      #gsh-go, #gsh-stop {
        flex-grow: 1; padding: 8px 16px; color: #fff;
        border: none; border-radius: 8px; cursor: pointer; font-size: 14px;
      }
      #gsh-go { background: #1a73e8; }
      #gsh-go:hover { background: #1558b0; }
      #gsh-go:disabled { background: #ccc; cursor: not-allowed; }
      #gsh-stop { background: #d93025; }
      #gsh-stop:hover { background: #a50e0e; }
    `);

    // --- [3] HTML 结构 ---
    // 创建并定义操作面板的HTML内容。
    const panel = document.createElement('div');
    panel.id = 'gsh-panel';
    panel.innerHTML = `
      <div id="gsh-header">
        <span>JCSY 航班查询</span>
        <span id="gsh-close" title="关闭">&times;</span>
      </div>
      <div id="gsh-body">
        <textarea id="gsh-q" placeholder="请在此处粘贴完整的 JCSY 文本..."></textarea>
        <div id="gsh-buttons">
            <button id="gsh-go">开始查询</button>
            <button id="gsh-stop" style="display: none;">停止</button>
        </div>
      </div>
    `;
    document.body.append(panel);

    // --- [4] 核心逻辑 ---

    // 获取所有需要操作的DOM元素
    const inputArea = panel.querySelector('#gsh-q');
    const startButton = panel.querySelector('#gsh-go');
    const stopButton = panel.querySelector('#gsh-stop');
    const closeButton = panel.querySelector('#gsh-close');

    // “开始查询”按钮的点击事件
    startButton.addEventListener('click', () => {
        const jcsyText = inputArea.value;
        if (!jcsyText.trim()) { alert('输入内容不能为空。'); return; }

        // 将原始文本存入 sessionStorage，以便在页面跳转后恢复。
        // sessionStorage 是浏览器的一个临时存储区域，数据在标签页关闭后清除。
        // 由于脚本需要在多个页面之间传递数据（每次搜索都是一个新页面），因此必须使用它。
        sessionStorage.setItem('originalJCSY', jcsyText);

        // 使用正则表达式从输入文本中提取所有航班号。
        // 正则表达式: \b([A-Z0-9]{2}\d{3,4})\s\/[A-Z]{3}\b
        // \b: 单词边界，确保匹配的是完整的航班号
        // ([A-Z0-9]{2}\d{3,4}): 捕获组，匹配2个字母或数字 + 3到4个数字 (例如: CA983, AA170)
        // \s\/: 匹配一个空格和斜杠
        // [A-Z]{3}: 匹配三个大写字母（起飞城市）
        const flightRegex = /\b([A-Z0-9]{2}\d{3,4})\s\/[A-Z]{3}\b/g;
        const flightQueue = [];
        let match;
        while ((match = flightRegex.exec(jcsyText)) !== null) {
            flightQueue.push(match[1]);
        }

        // 如果找到了航班，就开始处理流程
        if (flightQueue.length > 0) {
            // flightQueue (航班队列) 是一个数组，用于存储待查询的航班号。
            // 结构示例: ['AA0170', 'CA0983', 'CX0884', 'CA0770']
            sessionStorage.setItem('flightQueue', JSON.stringify(flightQueue));

            // resultsMap (结果映射表) 是一个对象，用于存储每个航班的查询结果。
            // 结构示例: { 'AA0170': '11:55 AM', 'CA0983': '日期不符' }
            sessionStorage.setItem('resultsMap', JSON.stringify({}));

            // 保存当前页面的URL，以便所有查询结束后返回。
            sessionStorage.setItem('originalURL', window.location.href);

            // 更新UI状态：禁用“开始”按钮，显示“停止”按钮
            startButton.disabled = true;
            stopButton.style.display = 'inline-block';
            stopButton.disabled = false;
            stopButton.textContent = '停止';

            // 开始处理队列中的第一个航班
            processNextFlight();
        } else {
            alert('未能在输入内容中找到任何有效格式的航班信息。');
        }
    });

    // “停止”按钮的点击事件
    stopButton.addEventListener('click', () => {
        // 通过清空航班队列来中断查询流程。
        sessionStorage.setItem('flightQueue', JSON.stringify([]));
        stopButton.disabled = true;
        stopButton.textContent = '正在停止...';
        // 当前的抓取操作完成后，会自动调用 processNextFlight，届时它会发现队列已空并开始生成最终结果。
    });

    // “关闭”按钮的点击事件
    closeButton.addEventListener('click', () => {
        // 隐藏整个UI面板。
        panel.style.display = 'none';
    });

    /**
     * @description 处理航班队列中的下一个航班，或者在队列为空时生成最终结果。
     * 这是脚本的核心调度函数。
     */
    function processNextFlight() {
        let flightQueue = JSON.parse(sessionStorage.getItem('flightQueue'));

        // 当队列为空时，表示所有航班都已查询完毕（或被手动停止）。
        if (!flightQueue || flightQueue.length === 0) {
            const originalJCSY = sessionStorage.getItem('originalJCSY');
            const resultsMap = JSON.parse(sessionStorage.getItem('resultsMap'));
            const lines = originalJCSY.split('\n');

            // --- 结果格式化与对齐 ---
            // 1. 动态计算 'ARVL' 列的最大宽度，以保证所有内容都能完美对齐。
            let maxResultLength = 'ARVL'.length;
            Object.values(resultsMap).forEach(result => {
                const currentLength = (' ' + result + ' ').length;
                if (currentLength > maxResultLength) {
                    maxResultLength = currentLength;
                }
            });

            // 2. 遍历原始文本的每一行，进行修改。
            const modifiedLines = lines.map(line => {
                // 首先，修改表头，使其与最宽的结果对齐。
                if (line.includes('FLT/ORIG')) {
                    const headerArvlWidth = maxResultLength;
                    return line.replace(/ARVL\s+/, 'ARVL'.padEnd(headerArvlWidth, ' '));
                }
                // 其次，找到包含航班号的行并插入结果。
                const flightNumberMatch = line.trim().match(/^[A-Z0-9]{2}\d{3,4}/);
                if (flightNumberMatch && resultsMap[flightNumberMatch[0]]) {
                    const flightNumber = flightNumberMatch[0];
                    const result = resultsMap[flightNumber];
                    // 使用正则表达式将行分割为“前缀”和“后缀”，以便在中间插入结果。
                    const regex = new RegExp(`(^.*?${flightNumber}\\s*\\/\\s*[A-Z]{3})(\\s+)(\\S.*$)`);
                    const lineMatch = line.match(regex);
                    if (lineMatch) {
                        const prefix = lineMatch[1]; // 例如: "AA0170 /HND"
                        const suffix = lineMatch[3]; // 例如: "000/003 000/003+00..."
                        // 使用 padEnd 填充空格，确保对齐。
                        const formattedResult = (' ' + result + ' ').padEnd(maxResultLength, ' ');
                        return prefix + formattedResult + suffix;
                    }
                }
                return line;
            });

            // 3. 将修改后的文本存储起来，准备显示。
            sessionStorage.setItem('finalOutputText', modifiedLines.join('\n'));
            const originalURL = sessionStorage.getItem('originalURL');

            // 4. 清理本次任务在 sessionStorage 中存储的所有数据。
            ['flightQueue', 'resultsMap', 'currentFlightNumber', 'originalURL', 'originalJCSY'].forEach(k => sessionStorage.removeItem(k));

            // 5. 返回到最初的页面。
            window.location.href = originalURL;
            return;
        }

        // --- 处理下一个航班 ---
        // 从队列中取出第一个航班号。
        const nextFlightNumber = flightQueue.shift();
        sessionStorage.setItem('flightQueue', JSON.stringify(flightQueue)); // 更新队列
        sessionStorage.setItem('currentFlightNumber', nextFlightNumber); // 记录当前正在查询的航班

        // 构建Google搜索查询，并跳转到搜索结果页面。
        const searchQuery = `${nextFlightNumber} flight`;
        window.location.href = 'https://www.google.com/search?q=' + encodeURIComponent(searchQuery);
    }

    /**
     * @description 在Google搜索结果页面上抓取航班到达时间。
     */
    function scrapeAndContinue() {
        const currentFlightNumber = sessionStorage.getItem('currentFlightNumber');
        // 如果 sessionStorage 中没有 currentFlightNumber，说明当前不是搜索结果页面，直接返回。
        if (!currentFlightNumber) return;

        // 更新UI，显示当前正在查询的航班号。
        startButton.disabled = true;
        stopButton.style.display = 'inline-block';
        startButton.textContent = `查询中... (${currentFlightNumber})`;

        // 设置一个短暂的延时，等待Google页面的航班信息动态加载完成。
        setTimeout(() => {
            let arrivalTime = '未能找到';
            try {
                // Google页面的航班信息在一个特定的 `div` 容器中。
                const mainContainer = document.querySelector(`div[data-async-context*="query:${currentFlightNumber}"]`);
                if (mainContainer) {
                    // 1. 查找包含日期的抬头，并验证日期是否为今天或昨天。
                    const headerRegex = new RegExp(`${DESTINATION_CITY}\\s+·\\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\\s+([A-Za-z]{3}\\s+\\d{1,2})`);
                    const headerElement = Array.from(mainContainer.querySelectorAll('div')).find(div => headerRegex.test(div.textContent));
                    if (headerElement) {
                        const match = headerElement.textContent.match(headerRegex);
                        const dateString = match[1]; // 例如: "Sep 2"
                        const today = new Date();
                        const yesterday = new Date();
                        yesterday.setDate(today.getDate() - 1);
                        const arrivalDate = new Date(`${dateString} ${today.getFullYear()}`);
                        today.setHours(0, 0, 0, 0); yesterday.setHours(0, 0, 0, 0); arrivalDate.setHours(0, 0, 0, 0);

                        const isDateValid = (arrivalDate.getTime() === today.getTime() || arrivalDate.getTime() === yesterday.getTime());
                        if (isDateValid) {
                            // 2. 如果日期有效，则查找包含具体时间（例如 "11:55 AM"）的元素。
                            const arrivalLabels = ['Estimated arrival', 'Scheduled arrival', 'Arrived'];
                            const timeRegex = /\d{1,2}:\d{2}\s(AM|PM)/;
                            const timeContainer = Array.from(mainContainer.querySelectorAll('div, span')).find(el => {
                                const text = el.textContent;
                                return arrivalLabels.some(label => text.includes(label)) && timeRegex.test(text);
                            });

                            if (timeContainer) {
                                const timeMatch = timeContainer.textContent.match(timeRegex);
                                if (timeMatch) {
                                    // 格式化时间文本，去除多余的空白字符。
                                    arrivalTime = timeMatch[0].replace(/\s+/g, ' ');
                                }
                            }
                        } else {
                            arrivalTime = '日期不符';
                        }
                    } else {
                        arrivalTime = '未找到日期抬头';
                    }
                } else {
                    arrivalTime = '未找到航班主区块';
                }
            } catch (e) {
                console.error("抓取时发生错误:", e);
                arrivalTime = "抓取异常";
            }

            // 将抓取到的结果存入 resultsMap。
            let resultsMap = JSON.parse(sessionStorage.getItem('resultsMap')) || {};
            resultsMap[currentFlightNumber] = arrivalTime;
            sessionStorage.setItem('resultsMap', JSON.stringify(resultsMap));

            // 处理队列中的下一个航班。
            processNextFlight();
        }, 1500); // 1.5秒的延时
    }

    /**
     * @description 检查 sessionStorage 中是否有最终结果，如果有，则显示在文本框中。
     * 这个函数在页面加载时运行，用于接收从搜索页面返回的结果。
     */
    function checkAndDisplayFinalResults() {
        const finalOutputText = sessionStorage.getItem('finalOutputText');
        if (finalOutputText) {
            inputArea.value = finalOutputText;
            sessionStorage.removeItem('finalOutputText'); // 显示后立即清除

            // 恢复UI按钮的初始状态。
            startButton.disabled = false;
            startButton.textContent = '开始查询';
            stopButton.style.display = 'none';
        }
    }

    // --- [5] 脚本启动 ---
    // 当脚本加载时，执行以下初始化操作。

    // 使UI面板可以被拖动。
    makeDraggable(panel, panel.querySelector('#gsh-header'));
    // 检查是否有从上一个页面传回的最终结果需要显示。
    checkAndDisplayFinalResults();
    // 如果当前页面是搜索结果页，则执行抓取操作。
    scrapeAndContinue();

    /**
     * @description 使一个元素可以通过其句柄被拖动。
     * @param {HTMLElement} el - 需要被拖动的元素。
     * @param {HTMLElement} handle - 用于拖动的句柄元素。
     */
    function makeDraggable(el, handle) {
        let isDragging = false, startX = 0, startY = 0, elStartX = 0, elStartY = 0;
        handle.addEventListener('mousedown', (e) => {
            isDragging = true; startX = e.clientX; startY = e.clientY;
            const rect = el.getBoundingClientRect(); elStartX = rect.left; elStartY = rect.top;
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
            e.preventDefault();
        });
        function onMove(e) {
            if (!isDragging) return;
            const dx = e.clientX - startX, dy = e.clientY - startY;
            el.style.left = `${elStartX + dx}px`; el.style.top = `${elStartY + dy}px`;
            el.style.right = 'auto'; el.style.bottom = 'auto';
        }
        function onUp() {
            isDragging = false;
            document.removeEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        }
    }
})();