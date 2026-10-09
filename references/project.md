# 一份内容规划，两条原生交付链路

项目共用 `deck.json`，记录事实、目标、页序、结论、备注与所需格式。布局由作者判断，不增加强制卡片、章节或页面配额。

```json
{
  "title": "演示数据：项目试点建议",
  "audience": "项目负责人",
  "goal": "决定是否进入小范围验证",
  "deliverables": ["pptx"],
  "style_profile": "approved-editorial",
  "slides": [{
    "id": "decision",
    "title": "先验证一个场景",
    "claim": "先用小范围验证决定后续投入",
    "svg": "svg/decision.svg",
    "notes": "虚构示例，不代表真实业务。此处补充必要说明。",
    "sources": ["虚构演示数据"],
    "depends_on": []
  }]
}
```

默认 PPT 只需要 `svg`。HTML 分支改为 `deliverables: ["html"]`，填写 `html`、`classes` 等字段，见 [html-delivery.md](html-delivery.md)。两种都要时填写两个源稿路径及 `deliverables: ["pptx", "html"]`。同页保持相同事实、结论、备注和视觉关系，不从参考样例复制业务内容。

可选 `theme`、`facts`、`style_profile` 记录共同决策；它们不会自动重画 SVG 或修改图表比例。颜色与比例从 [tokens.json](../assets/approved-style/tokens.json) 取值。显式品牌或参考优先。

```bash
python3 SKILL_DIR/scripts/presentation.py route PROJECT_DIR
python3 SKILL_DIR/scripts/presentation.py build PROJECT_DIR
```

`route` 只报告选择；没写格式时输出 pptx。`build` 执行所选分支，失败不会悄悄换另一种格式。HTML 可传 `--fonts-dir FONT_DIR`；浏览器渲染和两种视觉审阅另行完成。

## PPT 工程

`svg/` 保存源稿；`build/` 保存缓存、诊断、实际 PPT 预览；`output/` 保存 `presentation.pptx`、`svg-source.zip`、`preview.png`。

```bash
python3 SKILL_DIR/scripts/fonts.py --ensure
python3 SKILL_DIR/scripts/deck.py build PROJECT_DIR
python3 SKILL_DIR/scripts/deck.py edit PROJECT_DIR --slide decision --id request --text "请确认试点范围"
python3 SKILL_DIR/scripts/deck.py build PROJECT_DIR
python3 SKILL_DIR/scripts/deck.py approve PROJECT_DIR --note "写明当前版本的实际检查与取舍"
```

首次编译所有页，后续按内容、公共事实、字体和工具指纹重做变化页。页序与备注变化会更新 PPT 容器。SVG ZIP 包含逐页源稿、deck.json、所需开放字体与许可及重建说明；仅包含 PPT 重建材料，不宣称它包含 HTML 的完整源项目。实际 PDF 预览位于 `build/render/`。

`build/report.json` 保存结构、文字核对、渲染及审阅记录。approve 验证当前源稿、工具、字体、成品和预览仍属于本次构建；它不能代替 agent 看图。

## HTML 工程

`html/` 保存每页内容片段，`custom.css` 按需保存项目布局；共用查看器来自技能。`build/html/` 保存实际桌面和手机截图、PDF、构建与浏览器报告；`output/` 保存 `presentation.html`、`preview-html.png`。

单文件 HTML 已内嵌样式、脚本、文字和子集字体，用户直接打开即可。如用户需要重新生成的工程包，再附 deck.json、html/ 和 custom.css；不要把草稿、依赖或缓存混成交付。

## 成对基准

[reference/deck.json](../assets/approved-style/reference/deck.json) 保存同一组虚构示例的 SVG 与 HTML。它用于学习比例和实际比较，不规定新作品页数或章节。基准中的文案与信息密度可以变；真正要保留的是主次、关系、空间与整套气质。
