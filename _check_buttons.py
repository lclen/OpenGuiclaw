import re

html = open('templates/panels/panel_config.html', encoding='utf-8').read()
js = open('static/js/app-logic.js', encoding='utf-8').read()

# Extract all @click / @click.stop / @click.prevent handler expressions
click_exprs = re.findall(r'@click(?:\.\w+)*\s*=\s*"([^"]+)"', html)
change_exprs = re.findall(r'@change\s*=\s*"([^"]+)"', html)
init_exprs = re.findall(r'x-init\s*=\s*"([^"]+)"', html)

all_exprs = click_exprs + change_exprs + init_exprs

# Extract called function names from expressions
called = set()
for expr in all_exprs:
    names = re.findall(r'\b([a-z][a-zA-Z0-9_]*)\s*\(', expr)
    called.update(names)

# Extract defined names in app-logic.js (function keys in object literal)
defined = set(re.findall(r'\b([a-z][a-zA-Z0-9_]*)\s*\(', js))

# Known globals / builtins to ignore
ignore = {
    'true','false','null','undefined','parseInt','parseFloat','isNaN','isFinite',
    'encodeURIComponent','decodeURIComponent','setTimeout','clearTimeout','setInterval',
    'clearInterval','alert','confirm','prompt','fetch','console','window','document',
    'Object','Array','Set','Map','JSON','Math','Promise','Error','String','Number',
    'Boolean','Date','RegExp','Symbol','Proxy','Reflect','WeakMap','WeakSet',
    'find','filter','map','forEach','includes','some','every','push','pop','shift',
    'unshift','splice','slice','join','split','replace','trim','toLowerCase','toUpperCase',
    'toString','valueOf','hasOwnProperty','keys','values','entries','assign','freeze',
    'log','warn','error','info','debug','dispatchEvent','addEventListener','removeEventListener',
    'initTree','nextTick','dispatch','watch',
}

missing = sorted(f for f in called if f not in defined and f not in ignore)
present = sorted(f for f in called if f in defined)

print("=== 已定义 (可正常点击) ===")
for f in present:
    print(f"  ✓ {f}")

print()
print("=== 未找到定义 (可能无法点击) ===")
for f in missing:
    print(f"  ✗ {f}")
