# 运行依赖与兼容范围

在有 Codex 主运行时的环境中，优先使用已提供的依赖，不重复安装。不假设存在其他 presentation skill；本技能自带矢量编译、字体核验、增量构建与导出检查。

先运行：`python3 SKILL_DIR/scripts/doctor.py`。检查失败时修复明确缺项，再构建。doctor 只检测，不下载、不安装。

## 普通 Linux / WSL 环境

运行依赖：Python 3.10+、Node.js 22+、LibreOffice、Poppler（pdftoppm）、fontconfig（fc-match / fc-cache）。验证在 Linux 完成；Windows 原生与 macOS 尚未验证。Windows 可优先在 WSL 安装同样的依赖，不能宣称跨平台全部通过。

在技能目录使用项目自己的 Python 虚拟环境安装 requirements.txt，运行 `npm install` 安装 package.json 的公开依赖。系统软件由用户或已获授权的环境管理方式安装，不用 npm 代替系统依赖。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm install
.venv/bin/python scripts/fonts.py --ensure
.venv/bin/python scripts/doctor.py
```

fonts.py 下载 Google Fonts 的 Noto Sans SC 与 OFL 许可，写入用户缓存。离线时使用 `--ensure --source /absolute/path/NotoSansSC-variable.ttf`，并将官方 OFL.txt 放在字体旁。任意商业字体不会被自动打包；交付时按其许可处理。

## 两种容器使用同一矢量编译器

- 自动模式：已安装 `@oai/artifact-tool` 时优先使用；否则使用公开的 PptxGenJS。
- PptxGenJS 仅负责 PPT 包结构与讲者备注，SVG 仍转换为原生 DrawingML 文本、形状与分组。
- `PPT_AGENT_CONTAINER=artifact` 或 `PPT_AGENT_CONTAINER=pptxgenjs` 可明确选择。错误或缺依赖会中止，不能切换为整页图片。
- `CODEX_PRIMARY_RUNTIME_NODE` / `CODEX_PRIMARY_RUNTIME_NODE_MODULES` / `CODEX_PRIMARY_RUNTIME_ROOT` 优先定位宿主依赖；普通环境从 PATH 与本技能 node_modules 查找。
- 引擎、Node 和预览库版本参与缓存指纹，切换后会重建并使旧审阅失效。
- 实际 PPT 必须经过 LibreOffice 渲染，再用 Poppler 产生核对图片。并行构建使用独立 LibreOffice 配置目录。

PptxGenJS API 参考：[布局](https://gitbrent.github.io/PptxGenJS/docs/usage-pres-options.html)、[写入文件](https://gitbrent.github.io/PptxGenJS/docs/usage-saving.html)。

## HTML 分支

HTML 作者与打包需要 Python、lxml、fontTools 及有许可的 Noto Sans SC 400/700 字体。字体通过 `--fonts-dir` 或 `PPT_AGENT_FONT_DIR` 指定，无需 LibreOffice 或系统字体安装。实际网页渲染需要 Node、Playwright、Chromium 和 sharp。优先使用运行环境已有依赖；外部环境用 npm install 后按 Playwright 自带安装命令准备 Chromium，或将 `PPT_AGENT_BROWSER` 指向现有浏览器。只有请求 HTML 时才准备这套依赖。详见 [html-delivery.md](html-delivery.md)。
