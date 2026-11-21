---
name: wechat-miniprogram-silent-failure
description: "排查小程序点击无反馈、loading 不结束、列表不刷新及异步交互异常。根据运行证据检查状态、事件、超时与错误反馈，不将某次平台差异或延时补丁当作通用修复。"
agent_created: true
---

# 小程序「点了没反应」排查手册

## 核心认知（先看这段）

这类 Bug 的共同点是：**代码没有报错，业务逻辑也全是对的，错的是用户没看见任何东西。**
所以排查方向不是"找异常"，而是"找哪条出口没说话"，以及"话是不是被自己下一行抹掉了"。

优先级按命中率排：

| # | 根因 | 特征 | 命中率 |
|---|---|---|---|
| 1 | Loading 吞掉 Toast | 操作有网络往返，特定分支没提示 | **最高** |
| 2 | 异步链无总闸 | 要等好几秒/十几秒才动 | 高 |
| 3 | 假按钮（有样式无 `bindtap`） | 怎么点都不动，且完全没有按压反馈 | 高 |
| 4 | iOS 横向溢出 | 只在苹果机上、只在滑动时 | 中（但表现很怪，容易误判） |
| 5 | 抛异常打断后续流程 | 前一步成功、后一步没执行 | 中 |
| **6** | **真机交互层四件套**（见下） | **「JS 全对、提示也写了，用户还是说没反应」** | **高——第二轮才查出来的那批** |

> ⚠️ **做完了 1~5 还被反馈「依旧没反应」时，别再逐行审 JS 了。**
> 那时逻辑通常已经没问题，问题在模板 / 样式 / 系统行为层，直接跳到根因 6。

---

## 根因 1：Toast 被 Loading 吞掉（最常见）

微信把 `wx.showToast` 和 `wx.showLoading` 放在**同一块系统视图**上。
"同时只能存在一个"这条约束在**部分机型/部分基础库**上严格生效，于是：

```js
wx.showLoading({ title: '发布中', mask: true });
try {
  const r = await api.check();
  if (!r.ok) { wx.showToast({ title: '驳回' }); return; }  // ← 弹了
} finally {
  wx.hideLoading();                                        // ← 立刻把它抹了
}
```

用户看到：**一片安静**。而且因为机型差异，必然表现为「偶发」——这是最难复现的一类。

### 修复模板：统一反馈层

```js
// utils/feedback.js
let loadingOn = false;
const TOAST_DELAY_MS = 30;

function loading(title, mask) {
  wx.showLoading({ title: title || '处理中', mask: !!mask });
  loadingOn = true;
}
function hideLoading() {
  if (!loadingOn) return;          // 幂等，避免冗余调用
  wx.hideLoading();
  loadingOn = false;
}
function toast(msg, opt) {
  const text = String(msg || '').trim() || '没成功，再试一次';   // 空文案必须兜底
  hideLoading();                                                  // ① 先收 Loading
  return new Promise((resolve) => {
    setTimeout(() => { wx.showToast({ title: text, icon: 'none' }); resolve(); }, TOAST_DELAY_MS);
  });                                                             // ② 隔一帧再弹 Toast
}
```

**关键不变式：`toast()` 必须晚于 `hideLoading()` 至少一个 tick。**

### 检查手法

全项目搜裸调：`grep -rn "wx.showToast\|wx.showLoading\|wx.hideLoading" pages utils`
凡是同一函数里同时出现 `showLoading` 和 `showToast`，都要查先后顺序。

---

## 根因 2：异步链没有总闸

单看每段都有超时，加起来能到几十秒：

```
checkText(12s) + waitOpenid(15s) + postAdd(12s) = 39s，全程挂 mask
```

**用户观感 = 卡死。** 而且不能相信注释：`waitOpenid` 曾经注释写着「最多 2.5 秒」，
代码里一个超时都没有，实际能等 15 秒。**注释里的秒数不算数，要有 `Promise.race` / `withTimeout` 在那儿才算。**

### 修复模板：给整条链加总闸

```js
function deadline(promise, fallback, ms) {
  let timer = null, done = false, settle;
  const gate = new Promise((r) => { settle = (v) => { done = true; clearTimeout(timer); r(v); }; });
  timer = setTimeout(() => { if (!done) settle(fallback); }, ms);
  Promise.resolve(promise).then((v) => !done && settle(v), () => !done && settle(fallback));
  return gate;                       // 用 resolve 而非 reject，调用方少一层 try
}

async function run({ task, ms, timeoutValue, timeoutMsg }) {
  const value = await deadline(task, undefined, ms);
  if (value === undefined) {
    await toast(timeoutMsg || '处理时间有点长，稍后再看看');
    return { value: timeoutValue, timedOut: true };
  }
  return { value, timedOut: false };
}
```

配套：**慢了要改文案**。6 秒还没动静就把"发布中"换成"网络有点慢，还在处理…"——
一句永远不变的 loading 文案，看久了和死机一模一样。

---

## 根因 3：假按钮（只有样式没有事件）

典型现场：一排胶囊/标签看着能点，点了纹丝不动。

**先排除遮挡**：查所有 `position: absolute/fixed` 的兄弟层有没有 `pointer-events: none`，
以及目标元素有没有足够的 `z-index`。如果都没问题 —— 那就是**压根没绑 `bindtap`**。

```html
<!-- 假按钮 -->
<view class="tag" wx:for="{{tags}}">{{item}}</view>
<!-- 真按钮 -->
<view class="tag tap" wx:for="{{tags}}" data-k="{{item}}" bindtap="onTag">{{item}}</view>
```

顺手：给不少于 **64rpx** 的热区，并加 `:active` 按压反馈。
**一个点下去既不变色也不缩一下的按钮，用户会以为是自己没点准，然后连点十次。**

---

## 根因 4：iOS 左右滑动多出额外内容

按置信度从高到低修，三件套：

1. **`app.wxss` 的 `page` 加 `overflow-x: hidden`** —— iOS 页面支持横向橡皮筋回弹，
   超出屏宽的内容会被拉出来。**只能锁 X，锁 Y 会把下拉刷新一起废掉。**
2. **横向 `scroll-view` 里的行必须 `display: inline-flex` + `white-space: nowrap`** ——
   只用 `display: flex` 时，iOS 部分 WebView 会让超宽的一排**换行**，
   被裁掉的第二行在横向滑动时从边缘漏出来，就是"额外的文字"。
3. **收起的折叠面板不能带 `transform`** —— 里面有 `<textarea>` 这类原生组件时，
   原生组件画在独立图层、**不受父级 `overflow: hidden` 裁剪**，
   父容器一 transform，横向重绘就会把内容画到容器外面。
   改用 `max-height + opacity + visibility` 承担动画，`visibility: hidden` 作为第二道保险。

### ⚠️ iOS 边缘返回手势：改不了，别白费力气

`popGesture` / `popGestureDirection` 是 **Skyline 渲染引擎 + 自定义路由**的配置
（`wx.navigateTo` 的 `routeConfig`）。默认 **WebView 渲染**的项目加了也不生效。
`disableSwipeBack` 已废弃，且按官方社区答复对 iOS 侧滑返回本就不生效。

**凡是"看着该有个开关"的需求，先查证它到底存不存在，别往 json 里塞无效字段。**

---

## 根因 5：异常打断后续流程

`wx.setStorageSync` 在**存储满时会抛异常**。它经常写在成功流程中间：

```js
if (ok) {
  store.removeDraft(id);   // ← 抛了
  wx.navigateBack();        // ← 就不执行了，用户以为没成功
}
```

凡是「成功之后还要做几件事」的地方，清理类调用一律包 `try`。

---

## 根因 6：真机交互层四件套（第二轮必查）

这四个的共同点是：**JS 一行都没错，提示也真弹了，用户依然什么都感知不到。**
逐个排查时优先看 WXML / WXSS，不要再去翻业务代码。

### 6.1 按钮被 `disabled` 卡死 —— 事件根本不触发

```html
<!-- 致命：submitting 一旦卡住，按钮连 tap 事件都不派发，一句提示都没有 -->
<button bindtap="submit" disabled="{{submitting}}">发布</button>
```

`submitting` 解不开的场景：**真机切后台 / 锁屏时 `setTimeout` 会被系统暂停**，
`finally` 里的复位、以及链路的超时总闸**全部哑火**，回到前台后按钮永久失灵。

修法两条，缺一不可：

```html
<!-- 按钮永远可点，判断交给 JS -->
<button class="submit tap" hover-class="submit--press" hover-start-time="0" bindtap="submit">发布</button>
```

```js
async submit() {
  if (this.data.submitting) {
    // 用「上次点击过去了多久」判断，不要用定时器复位 —— 定时器在后台不响
    if (Date.now() - (this._submitAt || 0) > 30 * 1000) {
      this.setData({ submitting: false });   // 卡死了就自己放开
    } else {
      feedback.toast('还在发上一条，稍等一下');
      return;
    }
  }
  this._submitAt = Date.now();
  // ...
}
```

顺带把 `onShow` 也补上复位（切回来时清掉残留的"处理中"状态）。

### 6.2 Toast 被软键盘挡住

用户是"打完字直接点发送"，软键盘占着下半屏，**Toast 弹在键盘后面**。
提示真弹了，用户一个字没看到 —— 结论还是"没反应"。

```js
function toast(msg) {
  hideLoading();
  try { wx.hideKeyboard(); } catch (e) {}   // ← 先收键盘，再隔一帧弹
  setTimeout(() => wx.showToast({ ... }), 30);
}
```

没有键盘时 `hideKeyboard` 是空操作，可以无条件调。

### 6.3 系统弹窗抢屏幕（订阅授权 / Modal 盖掉 Toast）

`wx.requestSubscribeMessage`、`wx.showModal` 和 Toast 抢同一块屏幕，谁后弹谁赢。
"发布成功"刚弹出来就被订阅授权框盖掉，用户只看到一个莫名其妙的授权框。

**凡是"成功后还要弹系统窗"，一律排在页面跳转之后**：

```js
setTimeout(() => {
  wx.navigateBack({ complete: () => setTimeout(() => notify.request('reply'), 600) });
}, 900);   // 别用 400ms：Toast 会被页面卸载一起带走
```

### 6.4 按下那一帧没有任何反馈

小程序里 **`view` 的 `:active` 伪类不可靠**，必须有 `hover-class`；
而且 iOS 收键盘那一帧**偶尔会吞掉第一次点击** —— 没有按压反馈时，
用户连"按到了没"都不知道，只会觉得这按钮坏了。

```html
<view class="send tap" hover-class="send--press" hover-start-time="0" bindtap="send">发送</view>
```

### 6.5 兜底：看门狗（总闸之上的总闸）

链路的超时总闸靠 `setTimeout`，而它在后台可能被暂停。
给每条提交链再挂一个"没有结论就自己说话"的看门狗：

```js
function watchdog({ ms, msg }) {
  const base = lastToastAt;                 // 起跑前的最后结论时间
  const timer = setTimeout(() => {
    if (lastToastAt > base) return;         // 期间给过结论就不打扰
    hideLoading();
    toast(msg || '这条卡太久了，先看看网络');
  }, ms);
  return { cancel: () => clearTimeout(timer) };
}

// 用法：链路开头挂，finally 里 cancel
const wd = feedback.watchdog({ ms: 33000, msg: '…' });
try { /* ... */ } finally { wd.cancel(); }
```

注意 `lastToastAt` **只统计 Toast，不统计 Loading** —— Loading 只说明"还在跑"，
看门狗要盯的是"整件事有没有一个交代"。

### 6.6 顺手查：置灰条件与判据是否一致

```html
<!-- 置灰只看 content，但 send() 里是 title || content —— 只写标题的人看到灰按钮不敢点 -->
<view class="send {{content ? '' : 'send--off'}}">发送</view>
```

**置灰条件必须和提交函数的校验判据逐字一致**，否则就是"看着禁用其实能点"或反过来。

### 排查手法（第二轮专用）

```bash
# 1. 找被状态禁用的按钮（disabled 绑定了变量）
grep -rn 'disabled="{{' --include=*.wxml pages
# 2. 找没有 hover-class 的可点元素（class 里有 tap 却没有按压态）
grep -rn 'class="[^"]*tap[^"]*"' --include=*.wxml pages | grep -v hover-class
# 3. 找系统弹窗与 Toast 的相对顺序
grep -rn 'requestSubscribeMessage\|showModal' --include=*.js pages utils
```

---

## 验证：冒烟脚本要记录调用顺序

光做语法检查永远发现不了这些问题 —— 因为代码没报错。
必须把 wx 调用**连时间戳**记下来做断言：

```js
const log = [];
const wx = {
  showToast:  (o) => log.push({ api: 'toast',   title: o.title, t: Date.now() }),
  showLoading:(o) => log.push({ api: 'loading', title: o.title, t: Date.now() }),
  hideLoading:() => log.push({ api: 'hideLoading', t: Date.now() })
};

// 断言 1：Loading 之后 Toast 仍在
feedback.loading('发布中', true);
await feedback.toast('出错了');
assert(seq(log), ['loading', 'hideLoading', 'toast']);

// 断言 2：两者之间必须有时间间隔
assert(log[2].t - log[1].t >= 30, true);
```

加载页面模块：模块 Napkin 用 `Page()` 注册，用假的 `Page` 捕获 options，
再配上桩对象驱动它的方法：

```js
let captured;
const loader = makeLoader({ __wx: wx, __Page: (o) => { captured = o; }, 'store.js': {...} });
loader(path.resolve(ROOT, 'pages/forum/post/post.js'));
const inst = Object.assign({}, captured, {
  data: JSON.parse(JSON.stringify(captured.data)),   // 深拷贝初始 data
  setData(patch) { this.data = Object.assign(this.data, patch); }
});
```

**必须覆盖的用例**：每个 `return` 分支都要断言「有 Toast」；超时路径要断言「喊了话」；
重复点击要断言「第二次有说法」。

### 写脚本时常犯的错（我踩过）

- **忘了等 `toast` 的 30ms 延迟**就去断言「Toast 出现了」——测的是一个永远不会成立的时刻。
  断言前一律 `await sleep(60)`。
- **静态扫描没剥注释**，把注释里的反例（`// 以前裸调 wx.showToast`）当成真的裸调。
- **正则赌选择器后紧跟 `{`** —— 手写 CSS 里中间可能有换行和注释，改成逐字符扫 selector。
- **教训：如果冒烟脚本从不报错，多半是它根本没在测东西。**

---

## 交付前自检清单

- [ ] 提示全部走统一反馈层，没有裸调 `wx.showToast`
- [ ] 每条失败出口（含超时）都有文字反馈，没有静默 `return`
- [ ] 每个用户操作的 await 链都有总闸
- [ ] 长得像按钮的元素都绑了事件、有按压反馈、有热区
- [ ] `page` 锁了 `overflow-x`、横向滚动容器用 inline-flex + nowrap
- [ ] 冒烟脚本记录了调用顺序，且覆盖"每条出口"与"超时"
- [ ] 成功之后的清理调用包了 `try`
- [ ] **提交按钮没有用 `disabled="{{状态}}"`**（改成 JS 判断 + 时间戳过期自动放开）
- [ ] **每次 toast 前收了键盘**（键盘会挡住 Toast）
- [ ] **可点元素都写了 `hover-class`**（view 的 `:active` 不可靠）
- [ ] **成功后的系统弹窗排在页面跳转之后**（否则盖掉成功提示）
- [ ] **置灰条件与提交函数的判据逐字一致**
- [ ] 提交链挂了看门狗，且 `finally` 里 `cancel()`
