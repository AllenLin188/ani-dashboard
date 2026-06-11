#!/usr/bin/env python3
"""
fix_html.py  v2
用途（不需要 Cloudflare Worker / Anthropic API Key）：
  1. 移除 VS Code Live Server 注入的 WebSocket 代碼
  2. 停用 syncIB() — 改成靜態提示（IB 同步只能在 Claude.ai 執行）
  3. 把所有 Ani AI 評語區塊改成靜態規則提示卡（不呼叫 API）
  4. 停用 Ani Chat（hub.html 的 sendChat）— 改成靜態提示

使用方式：
  把此檔案放到 ani-dashboard 資料夾，執行：
    python fix_html.py            （實際修改，備份為 .bak）
    python fix_html.py --dry-run  （預覽，不修改）
"""

import os, re, shutil, argparse
from pathlib import Path

HTML_FILES = [
    'hub.html',
    'allen_trading_dashboard.html',
    'opening_decision_engine.html',
    'roll_evaluation_engine.html',
    'box_spread_manager.html',
    'daily_pnl_report.html',
    'portfolio_greeks.html',
]

LIVE_SERVER_MARKER = '<!-- Code injected by live-server -->'

# ── 靜態 Ani 評語卡（替換各子頁面的 getAniComment / getAiBriefing 函式）
STATIC_ANI_COMMENT_JS = """
// [GitHub Pages] Ani AI 評語已停用（需要 Anthropic API Key）
// 請在 Claude.ai 開啟 Hub 使用完整 AI 功能
function getAniComment() {
  const boxes = document.querySelectorAll('#ani-box, #ani-comment, #ani-briefing, #ani-analysis');
  boxes.forEach(el => {
    if (!el) return;
    el.innerHTML = `
      <div style="padding:12px 14px;background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.25);border-radius:8px;font-size:11px;line-height:1.8;color:#a5b4fc">
        <div style="font-weight:700;margin-bottom:6px">📋 靜態規則提示（GitHub Pages 版）</div>
        <div>① <strong>EL &lt; 20% NLV</strong> → 禁開 CSP / CC，只能 BPS（廣基指數）</div>
        <div>② <strong>Delta 上限</strong>：單腿 &lt; 0.30，組合淨 Delta &lt; ±200</div>
        <div>③ <strong>TIMS 壓測</strong>：個股 ±15%，廣基 +6% / −8%</div>
        <div>④ <strong>IB 無 Margin Call</strong>，Excess Liquidity → 0 即自動砍倉</div>
        <div>⑤ <strong>CC / CSP Roll</strong>：必須 Combo Order 同步執行，禁止分腿</div>
        <div style="margin-top:8px;color:#6366f1">💡 完整 Ani AI 分析請在 Claude.ai 中使用</div>
      </div>`;
  });
}
function getAiBriefing() { getAniComment(); }
function getAiComment()   { getAniComment(); }
"""

# ── 靜態 syncIB（hub.html）
STATIC_SYNC_IB_JS = """
// [GitHub Pages] IB 同步已停用
// IB MCP 只能在 Claude.ai 環境執行
function syncIB() {
  const btn = document.getElementById('sync-btn');
  if (btn) {
    btn.textContent = '請在 Claude.ai 同步';
    btn.style.background = 'var(--yellow, #f59e0b)';
    btn.style.color = '#000';
    setTimeout(() => {
      btn.textContent = '⟳ 同步 IB';
      btn.style.background = '';
      btn.style.color = '';
    }, 3000);
  }
  // Show toast
  const label = document.getElementById('ib-label');
  if (label) {
    label.textContent = '⚠️ GitHub版：請用 Claude.ai';
    label.style.color = 'var(--yellow, #f59e0b)';
  }
}
"""

# ── 靜態 sendChat / loadDashboard（allen_trading_dashboard.html）
STATIC_CHAT_JS = """
// [GitHub Pages] AI Chat 已停用
function sendMessage() {
  const input = document.getElementById('ai-input');
  if (input) input.value = '';
  const msgs = document.getElementById('ai-messages');
  if (msgs) {
    const d = document.createElement('div');
    d.className = 'msg ai';
    d.innerHTML = '<div class="msg-avatar">🤖</div><div class="msg-bubble">⚠️ GitHub Pages 版不支援 AI 對話。<br>請至 <strong>Claude.ai</strong> 開啟 Hub 使用完整功能。</div>';
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
  }
}
function quickAsk(q) { sendMessage(); }
function loadDashboard() {
  const btn = document.getElementById('refresh-btn');
  if (btn) {
    btn.textContent = '請在 Claude.ai 使用';
    setTimeout(() => { btn.textContent = '⟳ 更新數據'; }, 3000);
  }
}
"""

# ── 靜態 sendChat（hub.html chat tab）
STATIC_SEND_CHAT_JS = """
// [GitHub Pages] Ani Chat 已停用
let chatHistory = [];
function sendChat() {
  const input = document.getElementById('chat-input');
  if (input) input.value = '';
  const c = document.getElementById('chat-msgs');
  if (c) {
    const d = document.createElement('div');
    d.className = 'msg ai';
    d.innerHTML = '<div class="msg-av">🤖</div><div class="msg-bubble">⚠️ GitHub Pages 版不支援 AI 對話。<br>請至 <strong>Claude.ai</strong> 開啟 Hub 使用完整功能。</div>';
    c.appendChild(d);
    c.scrollTop = c.scrollHeight;
  }
}
function quickQ(q) { sendChat(); }
"""


def remove_live_server(content):
    """移除 Live Server 注入的 WebSocket 代碼"""
    if LIVE_SERVER_MARKER not in content:
        return content, 0
    idx = content.index(LIVE_SERVER_MARKER)
    content = content[:idx].rstrip() + '\n</body>\n</html>\n'
    return content, 1


def replace_async_function(content, func_name, replacement_js):
    """
    用 regex 找到 async function funcName() { ... } 並替換成靜態版本。
    也處理非 async function funcName()。
    返回 (新content, 替換次數)
    """
    # 找 function 開頭（async 可選）
    pattern = re.compile(
        r'(?:async\s+)?function\s+' + re.escape(func_name) + r'\s*\([^)]*\)\s*\{',
        re.MULTILINE
    )
    match = pattern.search(content)
    if not match:
        return content, 0

    start = match.start()
    brace_pos = match.end() - 1  # 第一個 {

    # 用括號計數找到對應的 }
    depth = 0
    i = brace_pos
    while i < len(content):
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    else:
        return content, 0

    content = content[:start] + replacement_js.strip() + content[end:]
    return content, 1


def fix_file(filepath: Path, dry_run: bool = False) -> dict:
    if not filepath.exists():
        return {'file': filepath.name, 'status': 'SKIP', 'changes': []}

    original = filepath.read_text(encoding='utf-8')
    content = original
    changes = []

    # 1. 移除 Live Server
    content, n = remove_live_server(content)
    if n: changes.append('LiveServer removed')

    # 2. 依檔案名稱做特定替換
    name = filepath.name

    if name == 'hub.html':
        content, n = replace_async_function(content, 'syncIB', STATIC_SYNC_IB_JS)
        if n: changes.append('syncIB → static')
        content, n = replace_async_function(content, 'sendChat', STATIC_SEND_CHAT_JS)
        if n: changes.append('sendChat → static')
        # getAniComment in hub (overview tab)
        content, n = replace_async_function(content, 'getAniComment', STATIC_ANI_COMMENT_JS)
        if n: changes.append('getAniComment → static')

    elif name == 'allen_trading_dashboard.html':
        content, n = replace_async_function(content, 'loadDashboard', STATIC_CHAT_JS)
        if n: changes.append('loadDashboard → static')
        content, n = replace_async_function(content, 'sendMessage', '')
        # sendMessage handled inside STATIC_CHAT_JS already — skip double replace
        content, n = replace_async_function(content, 'getAniComment', STATIC_ANI_COMMENT_JS)
        if n: changes.append('getAniComment → static')

    elif name in ('opening_decision_engine.html', 'roll_evaluation_engine.html',
                  'box_spread_manager.html', 'daily_pnl_report.html', 'portfolio_greeks.html'):
        for fn in ('getAniComment', 'getAiBriefing', 'getAiComment'):
            content, n = replace_async_function(content, fn, STATIC_ANI_COMMENT_JS)
            if n: changes.append(f'{fn} → static')

    # 3. Catch-all: 任何殘留的 api.anthropic.com fetch 都替換成 console.warn
    api_count = content.count('https://api.anthropic.com')
    if api_count:
        content = content.replace(
            'https://api.anthropic.com/v1/messages',
            'https://DISABLED.anthropic.com/v1/messages'
        )
        changes.append(f'API URL disabled ×{api_count}')

    if content == original:
        return {'file': filepath.name, 'status': 'NO CHANGE', 'changes': []}

    if not dry_run:
        shutil.copy2(filepath, filepath.with_suffix('.html.bak'))
        filepath.write_text(content, encoding='utf-8')

    return {
        'file': filepath.name,
        'status': 'FIXED' if not dry_run else 'DRY RUN',
        'changes': changes
    }


def main():
    parser = argparse.ArgumentParser(description='Fix HTML files for GitHub Pages (no API key needed)')
    parser.add_argument('--dir', default='.', help='Directory with HTML files (default: .)')
    parser.add_argument('--dry-run', action='store_true', help='Preview only, no file changes')
    args = parser.parse_args()

    base = Path(args.dir)
    print(f'\n🔧 Ani Dashboard HTML Fixer v2  (No API Key Mode)')
    print(f'   目錄 : {base.resolve()}')
    print(f'   模式 : {"DRY RUN（預覽）" if args.dry_run else "實際修改（備份 .bak）"}')
    print('─' * 65)

    total_fixed = 0
    for fn in HTML_FILES:
        r = fix_file(base / fn, dry_run=args.dry_run)
        icon = {'FIXED':'✅','NO CHANGE':'⚪','SKIP':'⚠️','DRY RUN':'🔍'}.get(r['status'], '?')
        print(f"  {icon} {r['file']:<47} {r['status']}", end='')
        if r['changes']:
            print(f"  [{', '.join(r['changes'])}]", end='')
        print()
        if r['status'] in ('FIXED', 'DRY RUN') and r['changes']:
            total_fixed += 1

    print('─' * 65)
    if not args.dry_run and total_fixed:
        print(f'✅ {total_fixed} 個檔案已修改，原始備份為 .html.bak')
        print('\n📤 下一步：')
        print('   git add .')
        print('   git commit -m "fix: remove CORS errors, disable API calls for GitHub Pages"')
        print('   git push')
    elif args.dry_run:
        print('💡 確認無誤後，移除 --dry-run 執行實際修改')
    else:
        print('⚪ 所有檔案無需修改')

if __name__ == '__main__':
    main()
