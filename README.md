# CardDock · 影像归仓 NAS

云景数码影画 出品 · 1.5

**创建 Docker 项目 → 名称 carddock → 粘贴配置 → 修改密码 → 部署。**

通用安装使用项目内默认文件夹，不包含个人 NAS 地址、共享目录名称或固定存储卷编号。安装后在程序里更换主盘、添加备份。

## 安装

[完整安装说明](NAS安装说明.md) · [可直接粘贴的配置](compose.project.yaml)

```yaml
services:
  carddock:
    image: ghcr.io/xingyunshijie/carddock:latest
    container_name: carddock
    restart: unless-stopped
    ports:
      - "18080:8080"
    environment:
      TZ: Asia/Shanghai
      AUTHENTICATION_ENABLED: "true"
      AUTHENTICATION_PASSWORD: "改成你自己的密码" # 必填：至少8位，最多256位，不能保留示例文字
    volumes:
      - ./data:/state
      - ./archive:/storage
      - ./inbox:/sources:ro
      - /proc/1/mountinfo:/host/mountinfo:ro
      - /sys:/sys:ro
    read_only: true
    tmpfs:
      - /tmp:size=128m,mode=1777
    security_opt: ["no-new-privileges:true"]
```

`inbox` 放待导入素材，`archive` 保存归档，`data` 保存设置与历史。新安装提供 `archive/影像归仓` 作为默认文件夹。首次登录先让用户设置拷贝主目录和可选的备份目录，点击“保存并进入”后使用；自动导入初始关闭。

在程序的目标设置中更换主盘、添加备份或新建文件夹。独立硬盘、新共享目录和读卡器的接入方法见安装说明；Docker 必须先映射，软件才能访问。项目文件夹包含素材，更新时务必保留。

## 功能

全景序列、延时、RAW/JPG与代理分类；拷贝与校验分别计数。支持 SHA-256、XXHash64、BLAKE3、MD5、多份备份、队列、暂停继续、重试及报告。

## 下载和说明

[最新发布](https://github.com/xingyunshijie/carddock/releases/latest) · [更新迁移](UPDATE.md) · [测试范围](VALIDATION.md)

镜像 `ghcr.io/xingyunshijie/carddock:latest`，支持 linux/amd64 与 linux/arm64。安装只需配置文件，无需上传源码 ZIP、运行生成器或安装 carddock-admin。各品牌 NAS 的权限和热插拔需实机验收。

[LICENSE](LICENSE) · [依赖许可证](THIRD-PARTY-NOTICES.md)

## 国内镜像分发

国内仓库自动同步工具已准备，尚待仓库开通与授权。当前安装配置仍使用 GHCR；没有把示例国内地址当成可用地址。维护者见 [国内镜像仓库接入.md](国内镜像仓库接入.md)。

## 后续一键更新

推荐配置使用 latest 标签。支持镜像检查的 NAS 会在发现新镜像后提示更新；先结束拷贝、关闭自动导入，再更新原项目，保留全部目录。检查周期由 NAS 决定，不保证发布后立即提示。详细方法见 [UPDATE.md](UPDATE.md)。需要锁定具体版本可用 [compose.version.yaml](compose.version.yaml)。
