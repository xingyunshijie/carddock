# 影像归仓 NAS：创建 Docker 项目，开始素材归档

V1.0 · 构建5 · 云景数码影画 出品

面向支持 Docker Compose 的 Linux NAS。程序与依赖均在镜像内，主盘与备份安装后在程序内设置。

## 01 容器部署

DEPLOY · 一段配置拉起容器

### STEP 01 创建 Docker 项目

打开 NAS 的 **Docker → 项目 → 创建**，项目名称填写 `carddock`。不同品牌可能称为 Container Manager 或 Compose 项目。按 NAS 提示选择或创建项目文件夹，然后把下面的配置完整粘贴进去：

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
      AUTHENTICATION_PASSWORD: "改成你自己的密码"
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

无需上传程序文件夹、运行配置生成器或安装后台认证服务。

### 端口

容器内部固定 `8080`，左侧主机端口默认 `18080`。被占用时改为 `18081:8080`，访问时也使用修改后的端口。

### 认证（务必设置）

保持 `AUTHENTICATION_ENABLED` 为 `true`，将 `AUTHENTICATION_PASSWORD` 改成自己的8–256位登录密码。不是 NAS 管理员密码，也不需要生成密钥。密码含 `$` 时，每个 `$` 在配置中写成 `$$`，登录时输入原密码。

### 默认目录

配置使用相对路径，不写死任何用户的共享文件夹名称或 `/volume1`、`/volume2`。NAS 在项目文件夹下使用以下目录：

- `inbox`：待导入素材，可放入存储卡素材或拍摄文件夹；程序以只读方式访问。
- `archive`：归档存储空间，新安装默认主盘为其中的“影像归仓”文件夹。
- `data`：设置与历史，更新时保留。

通常由 Docker 自动创建。若 NAS 不自动创建，请通过文件管理器在项目文件夹内新建这三个空文件夹。相对路径以 NAS 为此项目保存的 Compose 文件所在目录为准；不要删除整个项目文件夹，它包含素材和历史。

点击 **立即部署**。NAS 自动拉取匹配 Intel/AMD 或 ARM64 的镜像。程序检查目录权限后启动。初始化仅处理空的 root 所有应用目录，随后以非 root 身份运行；不会递归更改已有共享目录权限。

## 02 使用指南

USER GUIDE · 安装后再设置主盘与备份

### 首次访问

容器运行后，在浏览器打开 `http://NAS_IP:18080`，将 `NAS_IP` 换成自己的 NAS 地址。

输入刚才设置的登录密码。首次登录先显示“先设置拷贝目录”：默认文件夹可直接使用，也可以点击“选择目录”更改主目录，按需添加备份，最后点击“保存并进入”。备份留空就是只拷贝主目录；自动导入初始关闭。将待导入素材放入项目的 `inbox` 后，可在程序中选择来源并开始拷贝。

### 更换主盘、添加备份

进入 **数据拷贝目标设置**：点击主文件夹旁的“选择”更换目录；点击“添加备份目录”选择或新建备份文件夹，再保存设置。无需重装。备份目录留空就是只拷贝主盘，最多支持八个备份目录。

程序中的 `/storage` 对应项目的 `archive`。在此范围内可自由新建、更换主盘和备份目录。同一磁盘中的第二份文件不能防范磁盘损坏；正式备份应选择独立磁盘或设备。

### 新增其他共享目录或硬盘（按需）

不同品牌 NAS 的真实共享目录和 USB 路径不同，没有通用的初始共享路径。Docker 不能访问尚未映射的目录；更改程序设置不能代替宿主机授权。

需要把备份放到项目外的共享目录时，在原项目 `volumes` 中增加一行，将左侧替换为真实路径：

```yaml
      - /实际备份共享目录:/backups
```

同时在 `environment` 中增加：

```yaml
      TARGET_ROOTS: /storage:/backups
```

等待任务结束，关闭自动导入，再重新部署原项目。之后可在程序中直接选择 `/backups` 及其子目录作为主盘或备份。保留原 `data` 映射，不安装不同版本，也无需更改源卡。

使用读卡器直接导入时，将 `./inbox:/sources:ro` 的左侧改为 NAS 显示的读卡器目录。若该 NAS 支持父目录挂载传播，可用 `/该NAS的USB父目录:/sources:ro,rslave`，并在程序里添加具体卡目录。品牌间路径与热插拔机制不同，先用少量素材验收后再开启自动导入。

### 权限设置（按需）

默认非 root 运行身份为 `1000:1000`。如果现有共享文件夹只允许指定账户写入，在 `environment` 中填写该账户的数字身份，例如：

```yaml
      PUID: "实际用户UID"
      PGID: "实际用户GID"
```

替换为 NAS 管理界面或管理员确认的数字，不能填用户名，也不要填 `0`。为该账户授予目标目录和 data 的写入权限。程序不会为修复权限而递归更改共享目录所有权。

### 归档与校验

大疆 `PANORAMA` 进入“全景序列”，保留拍摄组和组内 DNG/JPG，不拆分。延时、普通 RAW/JPG、视频代理继续按规则归档。

拷贝数量随写入增加，校验阶段单独计数。保留四种内容校验算法、多份备份、队列、暂停继续、重试和报告。检查完成结果后，在 NAS 中安全弹出设备。

### 更新

等待任务结束并关闭自动导入，再更新原项目的镜像版本。保留 `data`、`archive` 和 `inbox`，不要删除项目文件夹。已有用户的主盘、备份和手动设置不被默认目录覆盖；具体迁移见 [UPDATE.md](UPDATE.md)。

## 写在最后

首次用少量素材检查目录、分类和备份结果。各品牌的目录权限、读卡器热插拔需要实机验收；本版不代表所有 NAS 型号都经过认证。

首次安装和更新需要 NAS 能访问 `ghcr.io`。跨网络访问建议使用 NAS 的 HTTPS 反向代理或 VPN。

## 后续一键更新

推荐配置使用 latest 标签。支持镜像检查的 NAS 会在发现新镜像后提示更新；先结束拷贝、关闭自动导入，再更新原项目，保留全部目录。检查周期由 NAS 决定，不保证发布后立即提示。详细方法见 [UPDATE.md](UPDATE.md)。需要锁定具体版本可用 [compose.version.yaml](compose.version.yaml)。
