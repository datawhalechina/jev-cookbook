# 课程站维护

GitHub Pages 首页以 Jev Cookbook 课程为主，配套 TypeSafe 中文参考文档保留在原路径。

| 入口 | 来源 | 维护方式 |
|---|---|---|
| `/` | `site/home.html`、`site/course.json` | 首页介绍、学习路线与十一章概览 |
| `/course/01/` 至 `/course/11/` | `main/` 各章 `README.md` 与章节元数据 | 在线导读随 README 重建；Notebook、工程和补充文档链接到仓库 |
| `/introduction/` 等文档路径 | `content/` | 保留社区翻译、原文入口、实验室与配套材料 |

增加或调整章节时，修改 `course.json` 中的标题、目录、摘要、主题与学习目标，再同步首页的课程说明。章节页完整渲染当前 README；课程搜索也使用这些内容。Notebook 默认从章节目录读取，第八章和第十章使用元数据指定的子目录。

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
