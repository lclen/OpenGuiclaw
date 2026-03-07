# 3D 虚拟形象显示开关功能文档 (VRM Display Toggle)

此功能允许用户在系统设置中开启或关闭右侧的 3D VRM 虚拟形象渲染区域，关闭后聊天界面自动扩展填满全屏，并联动隐藏相关 UI 入口。

## 1. 功能概述

- **系统级启用 (`vrmSystemEnabled`)**：默认**开启**。若在系统设置中**关闭**此项，整个 VRM 系统将被禁用，侧边栏的「角色配置」和「资源商店」入口将会隐藏，聊天界面的 VRM 面板抽屉按钮也被移除。
- **页面面板展开 (`showVrm`)**：仅当系统级启用的前提下有效。聊天界面顶部会提供一个展开/收起按钮。**开启**时右侧出现 30% 宽度的渲染区域，**关闭**时则利用 CSS transition 平滑收缩至 0，聊天区域扩展至全屏。
- **状态持久化**：两者状态均通过 `localStorage` 保存，互不干扰，刷新页面后保持上次的独立状态。

---

## 2. 前端实现细节 (双层控制架构)

为了优化聊天界面的体验，VRM 状态被拆分为两个独立层级：

1. **`vrmSystemEnabled`（系统级功能大开关）**：控制相关附带功能（如侧边栏入口）的开启与彻底关闭。
2. **`showVrm`（UI 层面的抽屉开关）**：专门在聊天面板，不影响系统其它功能，仅临时伸缩右侧 30% 渲染区域。

### 状态管理 (`static/js/app-logic.js`)

- `mainApp()` 中新增了双层状态控制，均从 `localStorage` 读取：
  ```js
  vrmSystemEnabled: localStorage.getItem('vrmSystemEnabled') !== 'false', // 默认 true
  showVrm: localStorage.getItem('showVrm') !== 'false',                   // 默认 true
  ```
- **系统切换方法 (`toggleVrmSystem`)** 负责切换系统大状态、持久化，当系统被禁用时，如果用户正好处于 `persona` (角色) 或 `store` (资源) 面板，会自动跳转回主聊天界面 `chat`，并触发 resize：
  ```js
  toggleVrmSystem() {
      this.vrmSystemEnabled = !this.vrmSystemEnabled;
      localStorage.setItem('vrmSystemEnabled', this.vrmSystemEnabled);
      // ...自动面板跳回与 resize 逻辑
  }
  ```
- **视图收缩方法 (`toggleVrm`)** 仅执行伸缩并持久化折叠状态：
  ```js
  toggleVrm() {
      this.showVrm = !this.showVrm;
      // ...处理画布容器展开动画的缓冲时机，执行 resize
  }
  ```

### 布局控制 (`templates/index.html`)

- VRM canvas 容器：必须系统正常启用，且伸缩抽屉为开启状态时，才会占据 30% 并显示：
  ```html
  :class="(vrmSystemEnabled && showVrm) ? 'w-[30%] opacity-100' : 'w-0 opacity-0 pointer-events-none'"
  ```
- 主布局容器：收缩至 `w-[70%]` 或延展为全屏 `w-full` 依赖于同样条件：
  ```html
  :class="(vrmSystemEnabled && showVrm) ? 'w-[70%]' : 'w-full'"
  ```

### UI 入口联动 (`templates/panels/sidebar.html`)

侧边栏按钮的 `x-show` 条件现在强关联功能彻底被启用的系统大开关（`vrmSystemEnabled`），而不受用户临时展开或收缩右侧边栏（`showVrm`）的影响。当在聊天界面关闭右屏幕时，不至于找不到入口。

```html
x-show="(btn.panel !== 'persona' || vrmSystemEnabled)
     && (btn.panel !== 'store'   || vrmSystemEnabled)
     && (btn.panel !== 'diary'   || config.journal.enable_diary)"
```

### 聊天顶部抽屉按钮 (`templates/panels/chat_area.html`)

聊天顶部的展开/收起按钮本身是否显示依赖于：
```html
<button x-show="vrmSystemEnabled" @click="toggleVrm()" title="切换3D形象显示">
```
即系统关闭时，伸缩按钮不渲染；系统开启但被用户点掉收缩时，按钮依然存活以供再次点击展开。

在「系统设置 → 系统环境」选项卡顶部新增「3D 虚拟形象」开关卡片，这里绑定的是**系统大开关（`vrmSystemEnabled`）**：

```html
<label @click.prevent="toggleVrmSystem()">
    <input type="checkbox" :checked="vrmSystemEnabled" class="sr-only peer" readonly>
    <!-- toggle UI -->
</label>
```

### Three.js Resize 保护 (`static/js/vrm-manager.js`)

`onWindowResize()` 在 container 宽度为 0 时直接返回，防止 VRM 关闭期间 resize 事件破坏渲染器状态：

```js
onWindowResize() {
    if (!this.camera || !this.renderer) return;
    if (this.container && this.container.clientWidth === 0) return;  // VRM 已隐藏，跳过
    // ...正常 resize 逻辑
}
```

---

## 3. 如何使用

1. 打开左侧菜单底部的**系统设置**。
2. 切换至**系统环境**选项卡。
3. 找到「3D 虚拟形象」开关进行切换，效果立即生效。

---

*功能实现时间: 2026-03-05 14:58*
*文档更新日期: 2026-03-05*
