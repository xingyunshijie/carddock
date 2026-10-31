# 影像归仓 NAS：创建 Docker 项目，开始素材归档

V1.0 · 构建3 · 云景数码影画 出品

全景序列、照片、RAW、视频与声音分别归档；拷贝后校验。主盘和备份进入软件后再设置。

## 01 容器部署

DEPLOY · 一段配置拉起容器

### STEP 01 创建 Docker 项目

打开 NAS 的 **Docker → 项目 → 创建**，项目名称填写 `carddock`，把下面的配置完整粘贴进去。

不需要下载或上传程序文件夹，不需要配置生成器，也不需要安装 carddock-admin 认证服务。

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

### 端口

容器内部固定 `8080`，左侧主机端口默认 `18080`。被占用时改为 `18081:8080`，访问时也使用新端口。

### 认证（务必设置）

保持 `AUTHENTICATION_ENABLED` 为 `true`，将 `AUTHENTICATION_PASSWORD` 改成自己的12–256位登录密码。不是 NAS 管理员密码，也不需要生成密钥。密码含 `$` 时，每个 `$` 在配置中写成 `$$`，登录时输入原密码。

### 存储目录

上面的路径已按你的 NAS 核对：`/volume2/NASgutai` 和 `/volume3/NAS02`。换到其他 NAS 时，只修改冒号左边的真实共享目录；相同目录在配置中出现两次，要一起修改。右侧 `/storage/area1`、`/storage/area2`、`/manual/area1`、`/manual/area2` 保持不变。

`/mnt/@usb` 是这台绿联 NAS 的 USB 挂载父目录，存储卡以只读方式接入。两条 `/manual/…` 映射用于手动添加 NAS 中的素材来源，也是只读。`/proc/1/mountinfo` 和 `/sys` 用于识别外接设备。

配置和历史自动保存在 Docker 数据卷 `carddock_carddock-data`，无需手动创建 state 文件夹。镜像默认使用 `1000:10`，该账户需对目标共享文件夹有写入权限。其他 NAS 的账户不同，可在 `restart` 下补充 `user: "实际UID:实际GID"`，并为数据卷设置相同的写入权限。

核对密码和目录后，点击 **立即部署**。NAS 自动下载程序镜像，支持 Intel/AMD 和 ARM64，无需选择处理器版本。下载或启动失败时查看 Docker 日志；不能把“创建成功”当作“已经正常运行”。

## 02 使用指南

USER GUIDE · 设置一次，日常直接使用

### 首次访问

容器运行后，在浏览器打开 `http://NAS_IP:18080`。你的 NAS 地址为 `http://192.168.1.168:18080`。

输入刚才设置的登录密码。进入软件后选择来源、主盘目录和归档规则。

### 主盘与备份

在目录选择器中，`/storage/area1` 对应 NASgutai，`/storage/area2` 对应 NAS02。

备份目录留空就是主盘版；添加备份目录就是主盘加备份版。支持多份备份，随时在程序内修改，无需重装。备份应放在独立磁盘或存储设备上。

### 日常使用

1. 插入存储卡，选择来源；也可手动添加 `/manual/area1` 或 `/manual/area2` 中的源目录。
2. 选择主盘，按需要添加备份，保存设置。
3. 核对预览，开始拷贝。拷贝数量随写入增加，校验数量单独显示。
4. 检查结果和报告，再通过 NAS 安全弹出存储卡。

大疆 `PANORAMA` 归入“全景序列”，保留拍摄组与组内 DNG/JPG，不再拆分。延时序列、普通 RAW/JPG、视频代理继续按原规则处理。支持 SHA-256、XXHash64、BLAKE3、MD5、暂停继续、队列、重试和报告。

### 更新

等待传输结束并关闭自动导入，修改镜像版本后重新部署原项目。保留项目名、目录映射和数据卷，不要勾选删除数据卷。详细迁移与回退说明见 [UPDATE.md](UPDATE.md)。

## 写在最后

首次用少量素材检查路径、分类与备份结果，再开始正式归档。程序不会格式化存储卡。

首次安装和更新需要 NAS 能访问 `ghcr.io` 下载镜像。局域网外访问建议使用 NAS 的 HTTPS 反向代理或 VPN。
