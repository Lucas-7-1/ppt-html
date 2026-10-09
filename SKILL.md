---
name: ppt-agent-v7
description: 以美观、凝练、精简为核心制作或重构演示文稿，延续已认可的视觉基准。用于 PPT、PPTX、汇报、路演、培训、案例美化、SVG 演示及 HTML 网页演示。未指定格式时交付原生可编辑 PPTX 和逐页 SVG；明确要求 HTML 时交付独立 HTML 演示。用户提到 PPT agent、PPT 太普通或死板、保持上次审美效果、全矢量 PPT 时使用。
---

# PPT Agent v7

版本 7.3。**同一套审美，两条原生交付链路。** 先把内容编辑成值得看的作品，再按用户要的格式制作。美观、凝练、精简是目标；事实准确、可读、可编辑是底线。技术检查不能证明好看。

## 1. 先确定交付，不让工具决定作品

从本次明确要求与正在修改的目标判断格式，不因用户提过 HTML、材料来自网页或某工具更方便而切换。

| 用户要求 | 交付 |
| --- | --- |
| 做演示、做 PPT、没说格式 | 原生可编辑 PPTX + 逐页 SVG + 实际 PPT 预览 |
| 明确说 HTML、网页演示、浏览器播放，包括“用 HTML 展示 PPT” | 独立 HTML 演示 + 实际网页预览 |
| PPT 和 HTML 都要 | 同一内容与视觉方向，分别完成两种原生成品 |
| 正在修改已有稿件，没改格式 | 延续当前稿件格式；新建任务重新按上述默认规则 |

用户仅提供 HTML 作参考、说“不一定是 HTML”或“不要 HTML”，不视作要求 HTML。明确只要 PDF、SVG 等特定文件时尊重要求，不额外强塞另一种交付；按合适原生链路制作后导出。HTML 文件不等于网站发布授权。

在 deck.json 记录 `deliverables: ["pptx"]` 或 `["html"]`；同时需要时记录两项。不写该字段也默认 PPT。构建入口：

```bash
python3 SKILL_DIR/scripts/presentation.py build PROJECT_DIR
```

它只构建指定格式，仍须完成对应的渲染与视觉验收。项目结构见 [references/project.md](references/project.md)，按分支读取 [references/runtime.md](references/runtime.md) 准备依赖；HTML 不先安装整套 PPT 依赖。

## 2. 共用内容和审美决策

制作前读 [references/design.md](references/design.md) 与 [references/approved-style.md](references/approved-style.md)，**实际打开 [成对参考预览](assets/approved-style/reference.png)**，再看最相关的 SVG / HTML 源稿。默认采用这套已认可方向，不每次重新随机探索风格。新品牌规范、用户明确的参考或视觉指令优先。

从材料提炼观众要记住或决定的事，确定主张、最少充分证据、必要口径及备注。已有信息足够就直接做，只询问确实会改变作品的缺口。保留事实、计算、推断与建议的区别，不用虚构数字或行业套话填空。

先决定每页的作用与内容关系，再决定构图。时间交叠画在共同轴上；决策用建议、证据、条件和请求构成一份完整对象；比较保留统一尺度；数据页保留单位与基准。主视觉不能只是标题换大字号。精简不能删掉证据、必要细节或叙事节奏，不给所有任务预设页数、卡片数或固定章节。

使用共用的 [视觉参数](assets/approved-style/tokens.json) 建立字体、颜色职责、边距与尺度关系。保留编辑式排版、明确的主次、具体的工作对象和有作用的空间深度。复用语义对象与图形原语，不让统一的 title/body/rows 模板决定每页形状。具体造型、页面密度与图表种类由新内容决定；不要求所有封面都画拱门。

较长作品先做好主视觉页和最复杂的代表内页，实际渲染后再扩展整套。基准适用且方向明确时直接沿用；用户否定方向或新题材明显不适配时，按 [references/aesthetic-method.md](references/aesthetic-method.md) 用相同事实比较真正不同的构图。不是换两种颜色。深度方法论或原则任务另读 [references/principles.md](references/principles.md)，不要把方法报告塞进演示正文。

## 3A. PPT：原生编辑链路（默认）

读 [references/vector-contract.md](references/vector-contract.md)。用 1280×720 SVG 创作，按同一视觉基准换算尺度，保留 SVG text、真实曲线、图形与语义分组。稳定页面和对象 ID，便于局部修改。

```bash
python3 SKILL_DIR/scripts/doctor.py
python3 SKILL_DIR/scripts/fonts.py --ensure
python3 SKILL_DIR/scripts/deck.py build PROJECT_DIR
```

编译器优先用环境内 JavaScript artifact-tool 创建容器，环境外可用公开的 PptxGenJS，将 SVG 转为原生 OOXML。执行字形、内容、对象、结构检查，并渲染实际 PPT。

将纸张偏移、空间层次、线条与裁切关系用原生几何实现。HTML 的布局与 CSS 效果不能直接粘成 PPT，也不能因为转换受限就删掉主体或摊成普通条目。禁止整页截图、文字轮廓或“插入 SVG 图片”冒充原生可编辑对象。

需要照片或截图时按用户要求使用真实图片，并如实说明其编辑边界。矢量图表默认是形状级编辑；用户需要双击改 Excel 数据时使用原生 chart API。不能将两者混称，也不因“全矢量”拒绝必要证据。

## 3B. HTML：网页原生链路（明确要求时）

读 [references/html-delivery.md](references/html-delivery.md)。以 DOM 文字、CSS 与内联 SVG 构图，使用同一视觉基准，不把 PPT 整页截图包进网页。复用现成查看器与样式，但按内容设计页面。

```bash
python3 SKILL_DIR/scripts/html_deck.py build PROJECT_DIR --fonts-dir FONT_DIR
node SKILL_DIR/scripts/render_html.mjs PROJECT_DIR
```

默认单文件离线可开，嵌入字体与许可，提供翻页、目录、备注、文字编辑与保存副本。桌面保持完整 16:9 构图；手机重排成可读内容。导航位于画布之外，不把演示做成网站面板集合。HTML 源码中的文字和图形可改，不宣称提供 PowerPoint 的拖拽编辑。

两种都要时，共用同一份事实、页序、结论、备注和视觉决策，各自保存 `svg` 与 `html` 源稿。分别构建，修复任何内容或视觉落差；不存在默认可靠的任意 HTML 到原生 PPT 自动转换。

## 4. 对照已认可作品验收

先看作品，再看文件是否能用。必须查看请求格式的实际成品：PPT 看实际 PPT 渲染，HTML 看真实浏览器渲染。不能用另一分支的预览代替。

1. **比较主视觉页与复杂内页**：并排放新稿和视觉基准，观察主体、比例、证据关系、空间层次。修改已认可稿件时还要比较修改前后的同页。更整齐或更少字不自动代表更好看。
2. **看整套缩略图**：检查气质、深浅、密度、主视觉轮廓与叙事节奏。不能只做好封面，也不要机械轮换布局和背景。
3. **逐页看正常尺寸和局部**：检查中文断行、字重、光学对齐、图形交接、裁切、溢出及必要口径。信息过满时先重编与改构图，别缩字硬塞。
4. **验证交付能力**：PPT 核对原生文本、形状、分组、字体及 SVG 一致性；HTML 核对桌面、手机、翻页、目录、备注、离线、编辑保存后重开。两种都要时并排看对应页。

发现退步时，按内容组织、构图与主次、整套节奏、细节的顺序处理。不要只靠换配色、加图标、堆卡片修补。已有方向的精修没有明显改善就保留原稿；不要为了减少页数删掉关键节奏。

实际看完后记录当前版本：

```bash
python3 SKILL_DIR/scripts/deck.py approve PROJECT_DIR --note "具体的内容、构图取舍和修复结果"
python3 SKILL_DIR/scripts/html_deck.py approve PROJECT_DIR --note "具体的桌面、手机与交互检查结果"
```

只执行所选分支对应的 approve。它记录 agent 的检查，不要求用户审批。源稿或成品改变后须重建重看，旧检查失效。不要编造审美分数、假装计时或仅写“高级、精美、已通过”。

交付请求格式的最终文件和真实预览，必要时简述最关键的设计取舍。缺少实际渲染或存在影响使用的限制必须说明。不要以对象数量、零图片或技术通过代替美感证据，不自封大师级。

## 修改与延续

普通改字改数：保留其他事实、设计与 ID，重建并看受影响页。`deck.py edit` 可按文本 ID 局部更新 SVG。只有外部 PPTX 时先读取，不假定有源稿。

继续提升已认可作品：保留已成立的视觉意图，针对实际缺陷做可逆对照。整体被否定时保留事实，重做编辑与构图。这套默认基准源于用户明确要求长期延续；其他单次赞许不自动改变默认风格，新的明确指令则覆盖默认。

公开示例仅放清楚标记的虚构内容。不要把用户姓名、公司、项目数据或私有作品直接复制进公开仓库。
