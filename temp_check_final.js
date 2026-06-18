
  console.log('[ask] script start');
  window.onerror = function(msg, url, line) {
    console.error('[ask] JS ERROR:', msg, 'at line', line);
  };
  var _askInit = JSON.parse(document.getElementById('ask-init-data').textContent);
  console.log('[ask] init data loaded, rows=' + (_askInit.results || []).length);
  var currentColumns = _askInit.columns || [];
  var currentRows = _askInit.results || [];
  try {
    var history = JSON.parse(localStorage.getItem('ask_history') || '[]');
  } catch(e) {
    var history = [];
  }
  var _chartInstance = null;
  var _chartResizeHandler = null;

  // Init theme
  if (typeof initThemeIcon === 'function') initThemeIcon('themeIcon');

  /* ── Column name beautifier ── */
  function beautyCol(raw) {
    var map = {
      id: '编号', title: '标题', name: '名称', content: '内容', url: '链接',
      summary: '摘要', keywords: '关键词', sentiment: '情感倾向', risk: '风险指数',
      status: '状态', created_at: '创建时间', updated_at: '更新时间',
      collected_at: '采集时间', published_at: '发布时间', deep_collected_at: '深度采集时间',
      is_deep_collected: '是否深度采集', source_id: '来源ID', source_name: '来源名称',
      source_type: '来源类型', fetch_interval: '采集间隔', last_fetched: '最后采集',
      item_count: '条目数量', count: '数量', total: '总计',
      model_id: '模型ID', model_name: '模型名称', employee_id: '员工ID',
      skill_type: '技能类型', config_json: '配置',
      category: '分类', description: '描述', sql_query: 'SQL查询',
      province: '省份', city: '城市', district: '区县',
    };
    // Try direct match first
    if (map[raw]) return map[raw];
    // Try lowercase
    var lower = raw.toLowerCase();
    if (map[lower]) return map[lower];
    // Handle _count, _total suffixes (slice suffix off, preserve original case in fallback)
    if (lower.endsWith('_count')) { var stem = lower.slice(0, -6); return (map[stem] || raw.slice(0, -6)) + '数量'; }
    if (lower.endsWith('_total')) { var stem = lower.slice(0, -6); return (map[stem] || raw.slice(0, -6)) + '合计'; }
    if (lower.endsWith('_at') || lower.endsWith('_time')) return (map[lower] || raw) + '';
    // Fallback: prettify snake_case
    return raw.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
  }

  /* ── History ── */
  function addHistory(query) {
    history.unshift({
      query: query, columns: currentColumns.slice(), rowCount: currentRows.length,
      ts: new Date().toLocaleTimeString()
    });
    if (history.length > 50) history.pop();
    try { localStorage.setItem('ask_history', JSON.stringify(history)); } catch(e) { /* quota */ }
    renderHistory(0);
  }

  function renderHistory(activeIdx) {
    if (activeIdx === undefined) activeIdx = 0;
    var el = document.getElementById('historyList');
    el.innerHTML = history.map(function(h, i) {
      return '<div class="history-item' + (i === activeIdx ? ' active' : '') + '" onclick="loadHistory(' + i + ')">'
        + h.query.substring(0, 40) + (h.query.length > 40 ? '...' : '')
        + '<span class="ts">' + h.ts + ' · ' + (h.rowCount || 0) + '条</span></div>';
    }).join('') || '<div style="color:var(--text-muted);font-size:12px;padding:8px;">暂无查询记录</div>';
  }

  function loadHistory(idx) {
    var h = history[idx];
    if (!h) return;
    document.getElementById('queryInput').value = h.query;
    renderHistory(idx);
    // Auto re-execute the query
    submitQuery();
  }

  /* ── Pipeline ── */
  function resetPipeline() {
    document.querySelectorAll('.pipeline-step').forEach(function(el) { el.className = 'pipeline-step'; });
    document.querySelectorAll('.pipeline-arrow').forEach(function(el) { el.classList.remove('done'); });
  }

  async function runPipelineAnimation() {
    resetPipeline();
    var sleep = function(ms) { return new Promise(function(r) { setTimeout(r, ms); }); };
    var steps = ['step-nl', 'step-sql', 'step-exec'];  // only first 3 auto-complete
    for (var i = 0; i < steps.length; i++) {
      var el = document.getElementById(steps[i]);
      el.classList.add('active');
      await sleep(350);
      if (document.getElementById('loading').style.display === 'none') return;
      el.classList.remove('active');
      el.classList.add('success');
      var arrow = document.querySelectorAll('.pipeline-arrow')[i];
      if (arrow) arrow.classList.add('done');
    }
    // Step 4 stays active (pulsing) until fetch resolves
    var renderEl = document.getElementById('step-render');
    if (renderEl && document.getElementById('loading').style.display !== 'none') {
      renderEl.classList.add('active');
    }
  }

  /* ── Submit ── */
  async function submitQuery() {
    var q = document.getElementById('queryInput').value.trim();
    if (!q) return;
    console.log('[ask] submitQuery called, q=' + q);
    var btn = document.getElementById('submitBtn');
    try {
      btn.disabled = true;
      document.getElementById('loading').style.display = 'flex';
      document.getElementById('resultArea').style.display = 'none';
      document.getElementById('chart').style.display = 'none';
      document.getElementById('chartInfo').style.display = 'none';
      document.getElementById('errorArea').style.display = 'none';
      document.getElementById('emptyState').style.display = 'none';
      var thinkBubble = document.getElementById('thinkBubble');
      thinkBubble.style.display = 'none'; thinkBubble.innerHTML = '';
      document.querySelectorAll('.tool-mini').forEach(function(el) { el.remove(); });
      if (_chartInstance) { if (_chartResizeHandler) { window.removeEventListener('resize', _chartResizeHandler); _chartResizeHandler = null; } _chartInstance.dispose(); _chartInstance = null; }
      runPipelineAnimation();
    } catch(initErr) {
      // If setup fails, still try the fetch
    }

    var thinkContent = '';
    try {
      var resp = await fetch('/ask/query', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-XSRFToken': getCookie('_xsrf') },
        body: JSON.stringify({ query: q })
      });
      if (!resp.ok) {
        var errText = await resp.text();
        throw new Error('HTTP ' + resp.status + ': ' + errText);
      }
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';

      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        var lines = buffer.split('\n');
        buffer = lines.pop();
        for (var i = 0; i < lines.length; i++) {
          var line = lines[i].trim();
          if (!line.startsWith('data: ')) continue;
          var jsonStr = line.substring(6);
          if (jsonStr === '[DONE]') continue;
          try {
            var parsed = JSON.parse(jsonStr);
            if (parsed.type === 'text') {
              thinkContent += parsed.content;
              var assembled = thinkContent.replace(/\n/g, '<br>');
              thinkBubble.innerHTML = '<div class="think-label">🤖 AI 思考中…</div>' + assembled;
              thinkBubble.style.display = 'block';
            } else if (parsed.type === 'tool_call') {
              var tm = document.createElement('div');
              tm.className = 'tool-mini';
              tm.innerHTML = '<span class="tm-icon">🔧</span><span>' + (parsed.name || 'tool') + '</span><span class="tm-status">执行中…</span>';
              thinkBubble.parentNode.insertBefore(tm, thinkBubble.nextSibling);
            } else if (parsed.type === 'tool_result') {
              var cards = document.querySelectorAll('.tool-mini:not(.success):not(.error)');
              var lastCard = cards[cards.length - 1];
              if (lastCard) {
                lastCard.classList.add(parsed.name === 'warehouse_query' ? 'success' : 'error');
                lastCard.querySelector('.tm-status').textContent = parsed.name === 'warehouse_query' ? '✓' : '✗';
              }
            } else if (parsed.type === 'done') {
              document.getElementById('loading').style.display = 'none';
              var rArrow = document.querySelectorAll('.pipeline-arrow')[2];
              var rStep = document.getElementById('step-render');
              if (rArrow) rArrow.classList.add('done');
              if (rStep) { rStep.classList.remove('active'); rStep.classList.add('success'); }
              currentColumns = parsed.columns || [];
              currentRows = parsed.rows || [];
              if (thinkContent) thinkBubble.innerHTML = '<div class="think-label">✅ 查询完成</div>' + thinkContent.replace(/\n/g, '<br>');
              showResults();
              addHistory(q);
            } else if (parsed.type === 'error') {
              document.getElementById('loading').style.display = 'none';
              var rArrow2 = document.querySelectorAll('.pipeline-arrow')[2];
              var rStep2 = document.getElementById('step-render');
              if (rArrow2) rArrow2.classList.remove('done');
              if (rStep2) { rStep2.classList.remove('active'); rStep2.classList.add('error'); }
              document.getElementById('errorArea').textContent = parsed.message || '查询失败';
              document.getElementById('errorArea').style.display = 'block';
            }
          } catch(e) { /* skip malformed JSON */ }
        }
      }
    } catch(e) {
      document.getElementById('loading').style.display = 'none';
      var rArrow3 = document.querySelectorAll('.pipeline-arrow')[2];
      var rStep3 = document.getElementById('step-render');
      if (rArrow3) rArrow3.classList.remove('done');
      if (rStep3) { rStep3.classList.remove('active'); rStep3.classList.add('error'); }
      document.getElementById('errorArea').textContent = '请求失败：' + (e.message || '未知错误');
      document.getElementById('errorArea').style.display = 'block';
    }
    btn.disabled = false;
  }

  function showResults() {
    document.getElementById('resultArea').style.display = 'block';
    document.getElementById('emptyState').style.display = 'none';
    renderTable(currentColumns, currentRows);
    buildCsvLink(currentColumns, currentRows);
    // Auto-render chart
    setTimeout(function() { renderChart(); }, 200);
  }

  /* ── Table ── */
  function renderTable(cols, rows) {
    var thead = document.getElementById('thead');
    var tbody = document.getElementById('tbody');
    thead.replaceChildren(); tbody.replaceChildren();
    var tr = document.createElement('tr');
    cols.forEach(function(c) {
      var th = document.createElement('th');
      th.innerHTML = beautyCol(c) + '<span class="col-tip">🔑 ' + c + '</span>';
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    rows.forEach(function(row) {
      var tr2 = document.createElement('tr');
      cols.forEach(function(c) {
        var td = document.createElement('td');
        var val = row[c] != null ? String(row[c]) : '';
        td.textContent = val;
        td.title = val;
        tr2.appendChild(td);
      });
      tbody.appendChild(tr2);
    });
    document.getElementById('rowCount').textContent = '共 ' + rows.length + ' 条结果';
  }

  function buildCsvLink(cols, rows) {
    var headerRow = cols.map(function(c) {
        var v = String(c);
        return v.includes(',') || v.includes('"') || v.includes('\n') ? '"' + v.replace(/"/g, '""') + '"' : v;
      }).join(',');
    var lines = [headerRow];
    for (var i = 0; i < rows.length; i++) {
      lines.push(cols.map(function(c) {
        var v = rows[i][c] != null ? String(rows[i][c]) : '';
        return v.includes(',') || v.includes('"') ? '"' + v.replace(/"/g, '""') + '"' : v;
      }).join(','));
    }
    var blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    var link = document.getElementById('csvLink');
    if (link.href && link.href.startsWith('blob:')) URL.revokeObjectURL(link.href);
    link.href = URL.createObjectURL(blob);
    link.download = 'result.csv';
    link.style.display = 'inline-block';
  }

  /* ── Chart ── */
  function renderChart() {
    if (!currentRows.length || !currentColumns.length) return;
    var chartEl = document.getElementById('chart');
    chartEl.style.display = 'block';
    document.getElementById('chartInfo').style.display = 'block';
    if (_chartResizeHandler) window.removeEventListener('resize', _chartResizeHandler);
    if (_chartInstance) _chartInstance.dispose();

    var chart = echarts.init(chartEl);
    _chartInstance = chart;

    var catCol = currentColumns[0];
    var numCols = currentColumns.slice(1).filter(function(c) {
      return currentRows.some(function(r) { return !isNaN(parseFloat(r[c])); });
    });
    if (!numCols.length && currentColumns.length >= 2) numCols = [currentColumns[1]];
    if (!numCols.length) { chartEl.style.display = 'none'; return; }

    var isLight = document.documentElement.getAttribute('data-theme') === 'light';
    var colors = isLight
      ? ['#6366f1','#8b5cf6','#ec4899','#10b981','#f59e0b']
      : ['#818cf8','#a78bfa','#f472b6','#34d399','#fbbf24'];
    var textColor = isLight ? '#4d4a70' : '#c4b5fd';
    var gridColor = isLight ? 'rgba(99,102,241,.08)' : 'rgba(139,130,255,.08)';
    var tooltipBg = isLight ? 'rgba(255,255,255,.95)' : 'rgba(20,18,48,.95)';
    var tooltipText = isLight ? '#2d2a4a' : '#e0e0f8';

    var numBars = numCols.length;
    var barWidth = numBars > 2 ? '60%' : '40%';

    var series = numCols.map(function(c, idx) {
      var color = colors[idx % colors.length];
      return {
        name: beautyCol(c),
        type: 'bar',
        barWidth: barWidth,
        barGap: '20%',
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: color } },
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: color }, { offset: 1, color: color + '44' }
          ]),
          borderRadius: [5, 5, 0, 0]
        },
        label: {
          show: true,
          position: 'top',
          color: textColor,
          fontSize: 10,
          fontWeight: 600,
          rotate: numBars > 2 ? 0 : 0
        },
        data: currentRows.map(function(r) {
          var v = parseFloat(r[c]);
          return isNaN(v) ? 0 : v;
        })
      };
    });

    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: '5%', right: '5%', bottom: '14%', top: '16%', containLabel: true },
      tooltip: {
        trigger: 'axis',
        backgroundColor: tooltipBg,
        borderColor: isLight ? 'rgba(99,102,241,.2)' : 'rgba(139,130,255,.2)',
        borderWidth: 1, padding: [10, 14],
        textStyle: { color: tooltipText, fontSize: 13 },
        axisPointer: { type: 'shadow', shadowStyle: { color: gridColor } },
        formatter: function(params) {
          var html = '<strong>' + params[0].axisValue + '</strong><br/>';
          params.forEach(function(p) {
            html += '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + p.color + ';margin-right:6px;"></span>';
            html += beautyCol(p.seriesName) + ': <strong>' + p.value + '</strong>';
            html += '<br/><span style="font-size:10px;color:' + (isLight ? '#9ca3af' : '#6b6b9e') + ';">字段: ' + p.seriesName + '</span><br/>';
          });
          return html;
        }
      },
      legend: {
        data: numCols.map(function(c) { return beautyCol(c); }),
        bottom: 0, textStyle: { color: textColor, fontSize: 12 },
        itemWidth: 12, itemHeight: 12, itemGap: 20
      },
      xAxis: {
        type: 'category',
        data: currentRows.map(function(r) {
          var v = r[catCol] != null ? String(r[catCol]) : '';
          return v.length > 12 ? v.substring(0, 11) + '…' : v;
        }),
        axisLine: { lineStyle: { color: isLight ? 'rgba(99,102,241,.25)' : 'rgba(139,130,255,.25)' } },
        axisTick: { show: false },
        axisLabel: {
          color: textColor, fontSize: 11,
          rotate: currentRows.length > 5 ? 25 : 0,
          interval: 0
        },
        name: beautyCol(catCol),
        nameTextStyle: { color: textColor, fontSize: 11, fontWeight: 600, padding: [10, 0, 0, 0] }
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: gridColor, type: 'dashed' } },
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: textColor, fontSize: 11 },
        name: numCols.length === 1 ? beautyCol(numCols[0]) : '数值',
        nameTextStyle: { color: textColor, fontSize: 11, fontWeight: 600, padding: [0, 0, 0, 10] }
      },
      series: series
    });

    chartEl.scrollIntoView({ behavior: 'smooth', block: 'center' });

    _chartResizeHandler = function() { chart.resize(); };
    window.addEventListener('resize', _chartResizeHandler);
  }

  function getCookie(name) {
    var v = document.cookie.split('; ').find(function(r) { return r.startsWith(name + '='); });
    return v ? decodeURIComponent(v.split('=')[1]) : '';
  }

  // Load initial data
  if (currentRows.length) {
    showResults();
    document.querySelectorAll('.pipeline-step').forEach(function(el) { el.classList.add('success'); });
  }
