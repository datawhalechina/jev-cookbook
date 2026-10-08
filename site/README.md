# 课程站维护

GitHub Pages 首页以 Jev Cookbook 课程为主，配套 TypeSafe 中文参考文档保留在原路径。

| 入口 | 来源 | 维护方式 |
|---|---|---|
| `/` | `site/home.html`、`site/course.json` | 首页介绍、学习路线与十一章概览 |
| `/course/01/` 至 `/course/11/` | `main/` 各章 `README.md` 与章节元数据 | 在线导读随 README 重建；Notebook、工程和补充文档链接到仓库 |
| `/introduction/` 等文档路径 | `content/` | 保留社区翻译、原文入口、实验室与配套材料 |
| `/materials/` | `site/reading.json`、`main/11_知识库/jev-cookbook/` | 全部知识库按主题展示，Markdown 自动挂载并进入全站搜索 |

增加或调整章节时，修改 `course.json` 中的标题、目录、摘要、主题与学习目标，再同步首页的课程说明。章节页完整渲染当前 README；课程搜索也使用这些内容。Notebook 默认从章节目录读取，第八章和第十章使用元数据指定的子目录。

拓展阅读覆盖 01–34 与 `laya-model` 全部板块：当前共 251 份 Markdown（含总览和来源清单）。各板块的子文档、研究笔记与目录自动发现，官方中文文档复用现有阅读地址；六篇早期拓展文章地址保持兼容。首页按主题折叠展示全部入口，知识库总页展开全部板块。增加板块时更新 `reading.json` 的目录、标题、分类和摘要；新增板块内的 Markdown 无需逐项登记。构建会检查目录清单一致性，避免新增板块遗漏。

资料之间的链接接到站内文档；代码、Notebook、PDF 等附件保留仓库入口。只复制实际引用的本地图片到 `dist/assets/reading/`，不复制训练数据、模型权重或应用环境。快照没有收录的工程附件指向原上游，缺少的配图保留原始材料说明。原始正文、来源、版权及许可说明保持可查阅。

构建仅使用 Python 标准库：

```bash
python3 build.py --check
```

构建会校验课程 README 的相对链接、全站内链和图片资源；校验失败返回非零退出码，阻止发布。课程 README 中引用的本地图片复制到 `dist/assets/course/`，不复制模型、数据集或应用运行环境。

推送 `main` 后，Pages 工作流先重建并校验，再上传 `dist/`。本地构建产物也保留在仓库中，便于预览与审查。构建不会执行 Notebook 或调用模型 API；生成页面不代表完成实时实验验收。

预览：

```bash
python3 -m http.server 8000 --directory dist
```

检查首页、各章入口、课程搜索、深浅色和手机导航。页面全部使用相对站内链接，发布到 `/jev-cookbook/` 子路径时无需额外配置。
