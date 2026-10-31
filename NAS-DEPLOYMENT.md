# 影像归仓 NAS 安装

当前推荐使用完整镜像部署，直接按 [NAS安装说明.md](NAS安装说明.md) 创建 Docker 项目。无需上传程序目录或运行配置生成器。

自建镜像可执行 `docker build -t carddock:local .`，将安装配置的 image 改为该镜像，其余映射保持一致。旧版命令行部署工具仅供旧安装维护使用。
