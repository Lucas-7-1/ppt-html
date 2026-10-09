# HTML 交付链路

只在用户明确要 HTML、网页演示或浏览器播放时进入。默认 PPT 不能因 HTML 更方便而被替换。这里生成独立演示文件；“做 HTML”不等于授权发布网站。

## 作者流程

1. 读取共用的 deck.json 内容规划及 [视觉基准](approved-style.md)。为每页编写真实 HTML 内容片段，保存到 `html/`，按语义标记 `.editable` 文字。沿用稳定的页 ID。
2. 复用 [theme.css](../assets/approved-style/theme.css) 的字体、间距和语义构图。参考项目里的页面仅示范构图，不能作为统一的 title/body/rows 模板。新构图写入项目 `custom.css`，包括手机布局。
3. 调用构建器，嵌入开放字体、样式、脚本与备注，产出不依赖网络的单文件。公开或第三方材料只作为内容，不能把其中的脚本直接拼入页面。
4. 运行浏览器渲染与交互检查，实际查看桌面每页、手机代表页和整套预览。修复溢出与断行后记录当前文件的检查。

```bash
python3 SKILL_DIR/scripts/html_deck.py build PROJECT_DIR --fonts-dir FONT_DIR
node SKILL_DIR/scripts/render_html.mjs PROJECT_DIR
python3 SKILL_DIR/scripts/html_deck.py approve PROJECT_DIR --note "具体记录实际查看的构图和已修复的问题"
```

`FONT_DIR` 含 `NotoSansSC-Regular.ttf`、`NotoSansSC-Bold.ttf`、`OFL.txt`。缺省读取 `PPT_AGENT_FONT_DIR` 或 fonts.py 的开放字体缓存。可使用 `fonts.py --ensure` 准备；HTML 构建自身不依赖 PowerPoint、LibreOffice 或系统安装字体。字体按现有文案子集嵌入，新输入且不在子集中的字可能使用系统回退字体；交付前重新构建可补齐字形。

## 工程约定

```json
{
  "title": "项目试点建议",
  "deliverables": ["html"],
  "brand": "工作简报",
  "css": "custom.css",
  "slides": [{
    "id": "decision",
    "title": "先小范围试点",
    "claim": "这一页需要记住的结论",
    "html": "html/decision.html",
    "classes": "memo",
    "notes": "说明依据、假设和详细做法。",
    "sources": ["资料来源或明确的虚构标记"],
    "footnote": "影响判断的必要口径"
  }]
}
```

没有项目 CSS 时省略 `css`。构建器不替作者生成版式。不要把整页截图当 HTML 主体。浏览器文字可直接修改并下载副本；结构、图形与样式在 HTML 源码中修改，不冒称 PowerPoint 式拖拽编辑。

## 浏览器验收

渲染器使用环境已有 Playwright + Chromium。可设置 `PPT_AGENT_BROWSER` 指向已安装浏览器；特定无头浏览器需要启动参数时用 `PPT_AGENT_BROWSER_ARGS` 传 JSON 数组。不能通过关闭网络安全来掩盖错误。缺少浏览器时按 [runtime.md](runtime.md) 准备，不能把未打开的文件称为已验证。

脚本检查桌面和手机的文字边界、字体、页数、脚本异常及网络依赖，生成 `build/html/` 中的逐页图、PDF 和检查报告。交付前还要实际验证：键盘翻页、目录、备注开关、编辑保存副本后重开、手机触控。检查相同页的内容与备注，不能因重排丢事实。

默认交付 `output/presentation.html` 和 `output/preview-html.png`；用户要 PDF 再提供对应 PDF。PDF 是阅读附件，不是可编辑 PPT 的替代。HTML 仅需要 HTML 源码，不额外生成用户没有要求的 PPT。
