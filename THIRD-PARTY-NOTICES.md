# 依赖说明

校验使用原生 xxhash 4.0.2 与 blake3 1.0.11；typing_extensions 4.15.0；IANA 时区数据 tzdata 2026.6。精确依赖、适用架构和 SHA-256 见 requirements.lock 与 wheelhouse。许可文本按原始 wheel 提取，保存在 licenses。

Docker 官方 Python 基础镜像由 Docker Hub 单独提供，未重打包在本ZIP中。可选源码构建路线会安装 ExifTool，由其上游许可约束。
