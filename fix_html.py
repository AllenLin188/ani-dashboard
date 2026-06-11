#!/usr/bin/env python3
"""
fix_html.py  v3  — 只移除 Live Server，其餘完全不動
"""
import shutil, argparse
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

MARKER = '<!-- Code injected by live-server -->'

def fix_file(filepath: Path, dry_run: bool) -> dict:
    if not filepath.exists():
        return {'file': filepath.name, 'status': 'SKIP'}

    original = filepath.read_text(encoding='utf-8')

    if MARKER not in original:
        return {'file': filepath.name, 'status': 'NO CHANGE'}

    # 找到 marker 位置，往前找最後一個 <script 開始的行
    idx = original.index(MARKER)
    
    # 往前找到這個 <!-- 所在行的起始位置
    # 通常 Live Server 注入的格式是：
    # \n<!-- Code injected by live-server -->\n<script>...
    # 我們要保留 </body>\n</html> 結尾
    
    # 先截到 marker 之前
    before = original[:idx].rstrip()
    
    # 確認 before 是否已有 </body> 和 </html>
    if '</body>' not in before and '</html>' not in before:
        # 加回正確結尾
        new_content = before + '\n\n</body>\n</html>\n'
    else:
        # 已有結尾，直接截斷
        new_content = before + '\n'

    if dry_run:
        return {'file': filepath.name, 'status': 'DRY RUN', 'removed': True}

    shutil.copy2(filepath, filepath.with_suffix('.html.bak'))
    filepath.write_text(new_content, encoding='utf-8')
    return {'file': filepath.name, 'status': 'FIXED'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default='.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    base = Path(args.dir)
    print(f'\n🔧 fix_html v3 — Live Server Remover Only')
    print(f'   模式: {"DRY RUN" if args.dry_run else "實際修改"}')
    print('─' * 55)

    fixed = 0
    for fn in HTML_FILES:
        r = fix_file(base / fn, args.dry_run)
        icon = {'FIXED':'✅','NO CHANGE':'⚪','SKIP':'⚠️','DRY RUN':'🔍'}.get(r['status'],'?')
        print(f"  {icon} {r['file']:<45} {r['status']}")
        if r['status'] in ('FIXED','DRY RUN'):
            fixed += 1

    print('─' * 55)
    if not args.dry_run and fixed:
        print(f'✅ {fixed} 個檔案已修改（備份 .bak）')
        print('\n📤 下一步：')
        print('   git add .')
        print('   git commit -m "fix: remove Live Server code only"')
        print('   git push origin main')
    elif args.dry_run:
        print(f'💡 {fixed} 個檔案需要修改，移除 --dry-run 執行')
    else:
        print('⚪ 所有檔案無 Live Server 代碼')

if __name__ == '__main__':
    main()
