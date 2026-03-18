import re

# home_view.html — Projects / Recent kicker
path = 'templates/panels/home_view.html'
with open(path, encoding='utf-8') as f:
    text = f.read()
text = text.replace('>Projects<', '>项目<')
text = text.replace('>Recent<', '>最近<')
with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print('home_view.html done')

# sidebar_shell.html — Workspace Hub
path2 = 'templates/panels/sidebar_shell.html'
with open(path2, encoding='utf-8') as f:
    text2 = f.read()
text2 = text2.replace('<small>Workspace Hub</small>', '<small>工作台</small>')
with open(path2, 'w', encoding='utf-8') as f:
    f.write(text2)
print('sidebar_shell.html done')

print('All HTML patches applied.')
