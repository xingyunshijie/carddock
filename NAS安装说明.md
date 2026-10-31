# 影像归仓 NAS：创建 Docker 项目，开始素材归档

V1.0 · 构建2 · 云景数码影画 出品

影像归仓用于把存储卡中的照片、RAW、视频与声音拷贝到 NAS，保留目录规则和校验记录。大疆全景、延时摄影、视频代理分别归档；主盘与备份进入程序后再选择。

**温馨提示**

本版使用 Docker 官方 Python 镜像运行安装包中的程序。请先把完整 `carddock-nas-1.0-b2` 文件夹上传、解压到 `/volume1/docker/carddock-nas-1.0-b2`，其中须直接包含 `app`、`runtime`、`wheelhouse`、`state`。程序和依赖已随包提供，首次部署需联网拉取官方运行镜像。

下面的共享目录、读卡器路径和 `1000:10` 用户身份参考既有绿联配置。安装人员按当前 NAS 实际路径和账户权限核对；路径严格区分大小写。示例同时开放两个共享文件夹，主盘和备份角色在软件中设置。

## 01 容器部署

DEPLOY · 一段配置拉起容器

### STEP 01 创建 Docker 项目

打开 NAS 的 **Docker** 应用，进入 **项目** 页面，点击 **创建**。项目名称填写 `carddock`，然后把下面这段配置完整粘贴进去：

```yaml
# 影像归仓 NAS V1.0 构建2
# 修改路径与 AUTHENTICATION_PASSWORD 后完整粘贴到 Docker 项目。
services:
  carddock:
    image: "python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337"
    restart: "unless-stopped"
    user: "1000:10"
    ports:
      - "18080:8080"
    environment:
      TZ: "Asia/Shanghai"
      AUTHENTICATION_ENABLED: "true"
      AUTHENTICATION_PASSWORD: "改成你自己的密码"
      SOURCE_ROOTS: "/sources"
      MANUAL_SOURCE_ROOTS: "/manual/area1:/manual/area2"
      TARGET_ROOTS: "/storage/area1:/storage/area2"
      TARGET_LABELS: "{\"/storage/area1\": \"存储区1 · Media\", \"/storage/area2\": \"存储区2 · Archive\"}"
      STATE_DIR: "/state"
      HOST_MOUNTINFO: "/host/mountinfo"
      PYTHONUNBUFFERED: "1"
      PYTHONDONTWRITEBYTECODE: "1"
      PYTHONPATH: "/opt/carddock-deps:/opt/carddock/app"
    command:
      - "/bin/sh"
      - "/opt/carddock/runtime/start.sh"
    volumes:
      -
        type: "bind"
        source: "/volume1/docker/carddock-nas-1.0-b2"
        target: "/opt/carddock"
        read_only: true
        bind:
          create_host_path: false
      -
        type: "bind"
        source: "/volume1/docker/carddock-nas-1.0-b2/state"
        target: "/state"
        read_only: false
        bind:
          create_host_path: false
      -
        type: "bind"
        source: "/mnt/@usb"
        target: "/sources"
        read_only: true
        bind:
          create_host_path: false
          propagation: "rslave"
      -
        type: "bind"
        source: "/volume2/Media"
        target: "/storage/area1"
        read_only: false
        bind:
          create_host_path: false
      -
        type: "bind"
        source: "/volume2/Media"
        target: "/manual/area1"
        read_only: true
        bind:
          create_host_path: false
      -
        type: "bind"
        source: "/volume3/Archive"
        target: "/storage/area2"
        read_only: false
        bind:
          create_host_path: false
      -
        type: "bind"
        source: "/volume3/Archive"
        target: "/manual/area2"
        read_only: true
        bind:
          create_host_path: false
      -
        type: "bind"
        source: "/proc/1/mountinfo"
        target: "/host/mountinfo"
        read_only: true
        bind:
          create_host_path: false
      -
        type: "bind"
        source: "/sys"
        target: "/sys"
        read_only: true
        bind:
          create_host_path: false
    read_only: true
    tmpfs:
      - "/tmp:size=128m,mode=1777"
      - "/opt/carddock-deps:rw,exec,nosuid,nodev,size=32m,mode=1777"
    cap_drop:
      - "ALL"
    security_opt:
      - "no-new-privileges:true"
    healthcheck:
      test:
        - "CMD"
        - "python"
        - "-c"
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/',timeout=3)"
      interval: "30s"
      timeout: "5s"
      start_period: "90s"
      retries: 3
    container_name: "carddock"
    working_dir: "/opt/carddock/app"
```

### 端口

容器内部固定 `8080`，左边主机端口默认使用 `18080`。如果被占用，把左边改成其他空闲端口，例如 `18081:8080`，后面访问时使用改后的端口。

只改左侧主机端口，保留容器内部的 `8080`。配置中的健康检查也继续使用内部端口。

### 认证（务必设置）

本配置已将 `AUTHENTICATION_ENABLED` 设置为 `true`，保持认证开启，并把 `AUTHENTICATION_PASSWORD` 的占位内容 **改成自己的登录密码**。不能保留“改成你自己的密码”，也不使用 `admin` 等默认弱密码。

登录密码为12–256个字符，可使用中文、字母、数字和符号。填写包含 `$` 的密码时，在 Compose 中将每个 `$` 写成 `$$`；登录时输入原来的单个 `$`。修改 YAML 字符串时保留正确的引号。

打开软件后，输入这里设置的密码即可登录，单用户模式无需用户名。忘记或要更换密码时，修改原 Docker 项目的 `AUTHENTICATION_PASSWORD`，重新部署容器后用新密码登录；任务、设置和素材仍保留，已有登录会失效。更新前先关闭自动导入并等任务结束。

**进阶提示**：局域网可使用本文的 HTTP 地址；需要跨网络访问时，使用 NAS 支持的 HTTPS 反向代理或 VPN。

确认配置、路径、端口和密码无误后，点击部署。启动时会从安装包加载校验依赖，并检查源目录只读、状态和目标目录权限；等待容器运行并通过健康检查即可。

## 02 使用指南

USER GUIDE · 选择来源 · 设置主盘和备份 · 拷贝与校验

### 首次访问

容器运行后，点击 NAS 提供的快速访问入口，或者在浏览器地址栏输入：

```text
http://NAS_IP:18080
```

把 `NAS_IP` 换成 NAS 的实际局域网地址，可在 NAS 的网络设置中查看。若前面将端口改成 `18081`，这里就访问 `http://NAS_IP:18081`。

首次打开会出现登录框，输入配置中设置的 `AUTHENTICATION_PASSWORD` 即可进入主界面。单用户模式，没有用户名。密码只用于影像归仓，不是 NAS 管理员密码。

### 日常拷贝

1. 在左侧选择存储卡，或手动添加已映射范围内的源目录。
2. 在右侧选择主盘归档目录。需要新目录时，可直接在选择器中新建文件夹。
3. 备份目录留空就是只拷贝主盘；需要备份时再添加目录，支持多份备份。
4. 选择校验方式和归档规则，保存设置，核对文件预览后开始拷贝。

程序中的 `/storage/area1` 对应配置里的 `/volume2/Media`，`/storage/area2` 对应 `/volume3/Archive`；存储区选择器会显示共享目录名称和容量。主盘、备份都在程序里决定，不需要安装不同版本。

新安装默认手动运行。确认测试素材拷贝正常后，可开启自动导入；自动导入由 NAS 后台处理，不要求浏览器保持打开。

### 全景、延时与普通照片

大疆 `PANORAMA` 进入“全景序列”，保留 `001_0061` 等拍摄组和原文件名，DNG 与 JPG 放在同一组内，不再拆分。

明确的延时摄影目录保留组号，再按 RAW/JPG 分开；普通 RAW/JPG 分存。LRF/LRV 等代理平铺到“视频代理”，也可选择不拷贝；索尼专用视频缩略图自动忽略。

### 看懂拷贝与校验进度

拷贝阶段每写完一个文件就增加拷贝数量，校验阶段单独统计校验数量。默认推荐 SHA-256，也可使用 XXHash64、BLAKE3、MD5；快速模式只检查大小，不表示内容校验通过。

主盘接力模式先完成主盘校验，再按本次清单生成备份。全部目标完成后再核对报告，在 NAS 系统中安全弹出设备；部分范围、快速模式、失败或取消不会被当作整卡内容校验成功。

### 队列、重试与报告

多张卡可加入队列，每项任务保存自己的目录和规则，按顺序执行。支持暂停、继续、终止和按原规则重试；重试先复核已有文件，再补拷缺失项。

可导出 JSON、TXT、传输日志与校验清单。兼容算法可生成基础 MHL 1.1；“打印 / PDF”导出的报告可通过浏览器存储为 PDF。配置、历史、预设与报告保存在 `state` 中，删除队列记录不会删除素材。

### 更换存储位置

如果目标已经在开放的共享文件夹内，直接在程序中选择新目录并保存。新增未映射的硬盘或共享文件夹时，编辑原 Docker 项目补充映射，并加入 `TARGET_ROOTS`；保留已有映射与状态目录。不同文件夹不一定是独立磁盘，备份位置由安装人员确认。

## 写在最后

影像归仓负责拷贝、归档和校验，不格式化源卡，也不直接挂载或卸载 NAS 的块设备。首次建议用可重复的小份素材确认路径、权限、分类与备份结果，再用于正式工作流。

本包经过自动测试、网页操作和 Compose 配置校验；当前开发机没有 Docker Engine，Linux 容器启动、NAS 权限和 USB 热插拔仍需实机验收。已有实例升级前阅读 [UPDATE.md](UPDATE.md)，避免新旧容器同时使用一个状态目录。

说明结构参照你提供的 [绿联 NAS Docker 项目部署教程](https://mp.weixin.qq.com/s/e6ri-olmQ0JOZRsIuUDMhQ)，配置按影像归仓的真实运行方式编写。
