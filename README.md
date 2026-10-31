# CardDock · 影像归仓 NAS

云景数码影画 出品 · V1.0 构建3

**Docker → 项目 → 创建 → 名称 carddock → 粘贴配置 → 修改密码 → 部署。**

无需上传程序文件夹，无需配置生成器，无需安装后台认证服务。主盘与备份进入程序后选择。

## 安装

[完整安装说明](NAS安装说明.md) · [可直接粘贴的配置](compose.project.yaml)

```yaml
services:
  carddock:
    image: ghcr.io/xingyunshijie/carddock:1.0.0-nas.3
    container_name: carddock
    restart: unless-stopped
    ports:
      - "18080:8080"
    environment:
      TZ: Asia/Shanghai
      AUTHENTICATION_ENABLED: "true"
      AUTHENTICATION_PASSWORD: "改成你自己的密码"
    volumes:
      - carddock-data:/state
      - /mnt/@usb:/sources:ro,rslave
      - /volume2/NASgutai:/storage/area1
      - /volume3/NAS02:/storage/area2
      - /volume2/NASgutai:/manual/area1:ro
      - /volume3/NAS02:/manual/area2:ro
      - /proc/1/mountinfo:/host/mountinfo:ro
      - /sys:/sys:ro
    read_only: true
    tmpfs:
      - /tmp:size=128m,mode=1777
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
volumes:
  carddock-data:
```

上面两组共享目录按当前 NAS 填写。其他 NAS 修改冒号左侧路径，密码至少12位；详细端口和目录说明见安装说明。

访问 `http://NAS_IP:18080`，输入自设密码。主盘、备份、归档规则在软件内设置。

## 功能

- 大疆全景序列保留拍摄组，组内 DNG/JPG 不拆分。
- 延时、普通 RAW/JPG、视频代理分类；拷贝和校验分别计数。
- SHA-256、XXHash64、BLAKE3、MD5；多份备份、主盘接力、暂停继续、队列和重试。
- JSON/TXT、日志与校验清单；兼容算法 MHL 和可打印报告。

## 下载和更新

[构建3发布页](https://github.com/xingyunshijie/carddock/releases/tag/v1.0.0-nas.3) · [升级说明](UPDATE.md) · [测试范围](VALIDATION.md)

程序镜像 `ghcr.io/xingyunshijie/carddock:1.0.0-nas.3`，支持 linux/amd64 和 linux/arm64。安装只需配置文件；完整 ZIP 用于源码备份和离线构建，无需上传到 NAS。

源码及随包依赖许可证见 [LICENSE](LICENSE) 和 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
