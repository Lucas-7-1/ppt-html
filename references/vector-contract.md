# 全矢量交付契约

默认 SVG 画布为 viewBox="0 0 1280 720"，宽高匹配。使用真实文字、基础图形和路径，自包含且可重建。

支持 svg/g/defs/linearGradient/radialGradient/stop/rect/text/tspan/circle/ellipse/line/path/polygon/polyline/use；路径的 SVG 指令由 fontTools 解析成原生自由曲线，弧线转贝塞尔。常规渐变转换成 DrawingML 渐变，复杂渐变需要实际导出对照。组合支持平移和等比缩放，旋转等其他变换先落实到坐标/路径；不支持的可见特性阻止构建，不忽略。

禁止 image（当前全矢量模式）、foreignObject、script、filter、mask、clipPath、pattern、CSS 样式表、inline style、远程引用、文字轮廓伪装，以及整页图片。通过坐标、填色和路径实现所需视觉；遇到无法忠实表达的效果，换等效构图，不降级为截图。

## 文字和可修改性

文字用明确的 x/y、font-size、font-family、fill。可以在 g 继承字体和填色。换行使用独立 text 或有明确坐标的 tspan；不要混合 text 直接内容与 tspan，不用 textLength 压缩文字。默认 baseline；多行正文用稳定的语义 ID，别把每个字拆成对象。

不要把文本改成路径来解决字体问题。使用含对应字形的字体；构建时检测，交付源稿附所用字体和开放许可。PPT 并非自动安装字体；使用者需安装字体才能在另一台设备上保持同样的排版。

每页、主要组合、可编辑文本和数据图形使用稳定 ID。PPT 选择窗格保留名称；相应组合可以取消组合继续改。每个对象都可编辑不等于用户能方便找到它，要按语义组织。

当前全矢量图表保留可编辑的线、柱、点和标签，不提供双击编辑 Excel 数据表。用户要求这种原生图表能力时，额外用原生 chart API，并检查实际 PPT 导出，不以截图或自由曲线冒充。

## 导出后实际核验

必须检查原生文本/形状、零图片、内容文字一致、唯一对象名称、字体和缺字、无跳过对象/不支持项，以及最终 PPT 实际渲染。XML 正常只是技术底线；全套视觉还需 agent 查看。
