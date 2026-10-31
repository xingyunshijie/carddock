# CardDock · 影像归仓 NAS

**云景数码影画 出品 · V1.0 构建2 · 测试版**

摄影存储卡导入、素材归档与内容校验。大疆全景序列、延时、普通 RAW/JPG 和视频代理按规则存储；主盘和备份进入程序后选择。

## 下载与安装

[下载新版统一安装包](https://github.com/xingyunshijie/carddock/releases/download/v1.0.0-nas.2/carddock-nas-1.0-b2-install.zip) · [新版发布页面](https://github.com/xingyunshijie/carddock/releases/tag/v1.0.0-nas.2)

**[完整安装说明：按参考教程的结构创建 Docker 项目](NAS安装说明.md)**

1. 创建项目：NAS 的 **Docker → 项目 → 创建**，项目名填 `carddock`。
2. 将安装说明中的完整配置粘贴进去，按实际情况修改路径。
3. 端口默认 `18080:8080`，被占用时只修改左侧主机端口。
4. 认证保持 `AUTHENTICATION_ENABLED=true`，将 `AUTHENTICATION_PASSWORD` 改成自己的12位以上登录密码。

程序文件准备、完整 YAML、端口与认证说明、首次访问和日常使用，均在安装说明中。主盘、备份和归档规则在软件内设置。

使用 Docker 官方 Python 运行镜像加载安装包内程序和 Linux amd64/arm64 校验依赖。首次需要拉取基础镜像。推荐下载 Releases 的安装包，解压后目录名为 `carddock-nas-1.0-b2`；源码下载目录需要按实际路径调整项目配置。

## 本次更新

- 大疆 `PANORAMA` → **全景序列/拍摄组/原文件**，保留组内 DNG、JPG、伴随元数据与内部目录，不拆 RAW/JPG。
- 延时序列保留组号，再按格式分开；代理平铺，可排除 LRF/LRV；索尼视频缩略图自动忽略。
- 先写入后集中校验，拷贝和校验分别显示文件计数。
- SHA-256、XXHash64、BLAKE3、MD5 和快速大小检查；已有文件重新复核后去重。
- 多目标、主盘接力备份、队列、暂停继续、终止、按原规则重试、预设和命名筛选。
- JSON/TXT/传输日志/校验清单、兼容算法 MHL 1.1；HTML 报告可打印为 PDF。
- 单用户密码登录；密码由安装人员在 Docker 项目配置中设置，旧密钥不会覆盖显式配置的密码。

## 其他说明

[完整配置](compose.project.yaml) · [升级说明](UPDATE.md) · [功能同步与平台差异](功能同步说明.md) · [测试范围](VALIDATION.md) · [更新记录](CHANGELOG.md)

本机86项自动测试与网页操作已通过。GitHub Actions 会继续验证测试和 Linux amd64/arm64 容器启动；NAS 卷权限、设备热插拔、断电和不同品牌硬件仍需实机确认。先使用可重复的小份素材核对分类与副本，再用于正式导入。

程序不格式化、不挂载或直接弹出存储卡。安全弹出请使用 NAS 系统。不同文件夹不代表独立磁盘备份。

## 授权与反馈

授权沿用 [LICENSE](LICENSE)，原版权和许可说明保留。公开源码供审阅与问题定位，不等同于 MIT 等开放源代码许可；第三方组件许可位于 `licenses/` 和 `THIRD-PARTY-NOTICES.md`。

[提交问题](https://github.com/xingyunshijie/carddock/issues)时请提供系统、版本、CPU架构和去掉密码后的日志，不要上传密码、密钥、私人素材或包含凭据的项目配置。
