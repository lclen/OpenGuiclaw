path = 'templates/panels/settings_overlay.html'
content = open(path, encoding='utf-8').read()

old = '''        <div class="settings-main-header">
          <div>
            <div class="settings-main-kicker">Workspace Preferences</div>
            <h3 x-text="(settingsTabs.find(tab => tab.id === settingsTab) || settingsTabs[0]).title"></h3>
            <p x-text="(settingsTabs.find(tab => tab.id === settingsTab) || settingsTabs[0]).description"></p>
          </div>
          <button class="settings-close" @click="showSettings = false">关闭</button>
        </div>'''

new = '''        <!-- React settings main header (replaces Alpine x-text title/close) -->
        <div data-react-settings-header-root></div>
        <!-- Legacy Alpine settings main header (hidden once React mounts) -->
        <div data-legacy-settings-header class="settings-main-header">
          <div>
            <div class="settings-main-kicker">Workspace Preferences</div>
            <h3 x-text="(settingsTabs.find(tab => tab.id === settingsTab) || settingsTabs[0]).title"></h3>
            <p x-text="(settingsTabs.find(tab => tab.id === settingsTab) || settingsTabs[0]).description"></p>
          </div>
          <button class="settings-close" @click="showSettings = false">关闭</button>
        </div>'''

if old in content:
    content = content.replace(old, new)
    open(path, 'w', encoding='utf-8').write(content)
    print('OK')
else:
    print('ERROR: pattern not found')
    # 调试：打印实际内容片段
    idx = content.find('settings-main-header')
    print(repr(content[idx:idx+400]))
