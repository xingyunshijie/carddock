# 依赖说明

校验使用原生 xxhash 4.0.2 与 blake3 1.0.11；typing_extensions 4.15.0；IANA 时区数据 tzdata 2026.6。精确依赖、适用架构和 SHA-256 见 requirements.lock 与 wheelhouse。许可文本按原始 wheel 提取，保存在 licenses。

完整容器镜像基于 Docker 官方 Python 镜像构建，包含 Python、Debian 运行库与 ExifTool，遵循各自的上游许可证。容器中的系统软件许可证位于 /usr/share/doc；Python 及随包依赖许可证见相应发行内容。源码 ZIP 不包含基础镜像层。
