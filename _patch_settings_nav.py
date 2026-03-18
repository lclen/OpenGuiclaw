import re

path = 'templates/panels/settings_overlay.html'
content = open(path, encoding='utf-8').read()

# 找到 <aside class="settings-nav"> ... </aside> 整块，替换为 React 挂载点 + legacy aside
old_marker_start = '      <aside class="settings-nav">'
old_marker_end = '      </aside>'

start_idx = content.find(old_marker_start)
if start_idx == -1:
    print('ERROR: start marker not found')
    exit(1)

end_idx = content.find(old_marker_end, start_idx)
if end_idx == -1:
    print('ERROR: end marker not found')
    exit(1)

end_idx += len(old_marker_end)

old_block = content[start_idx:end_idx]

new_block = '''      <!-- React settings nav (replaces Alpine x-for tab list) -->
      <div data-react-settings-nav-root></div>
      <!-- Legacy Alpine settings nav (hidden once React mounts) -->
      <aside data-legacy-settings-nav class="settings-nav">''' + old_block[len(old_marker_start):]

content = content[:start_idx] + new_block + content[end_idx:]

open(path, 'w', encoding='utf-8').write(content)
print('OK')
