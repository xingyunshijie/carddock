# 影像归仓 V0.12.0-beta.1 · 通用 NAS 安装

本包包含主程序源码、Dockerfile、安装工具及可选 PAM/systemd 认证扩展。Releases 另提供双架构镜像下载；不能将容器测试视为所有 NAS 的实机认证。

## 1. 安装前准备

目标为 Linux NAS，CPU 为 x86_64/AMD64 或 aarch64/ARM64；安装 Docker Engine、Compose V2（支持顶层 name 与 bind.create_host_path）及 Python 3.8+。需要 Linux 原生 bind 挂载传播。Docker Desktop 的 USB 透传不属于本安装方案。

由管理员准备四类独立目录：

| 目录 | 应用权限 | 要求 |
|---|---|---|
| 外接卡的自动挂载父目录 | 读取、进入 | 由 NAS 负责挂载和安全弹出，不能把整个系统根目录映射进来 |
| 主文件夹 | 读写、进入 | 专用导入目录 |
| 备份文件夹（可选） | 读写、进入 | 建议位于独立存储设备 |
| 状态目录 | 读写、进入 | 保存配置、历史和密钥；不能位于源或目标内部 |

使用 NAS 界面给专用普通账户授予上述目录权限，用 `id 账户名` 确认 UID/GID。不要给所有人开放读写，也不要递归更改整个共享盘的属主。路径必须已存在；安装程序不会自动创建拼错的宿主目录。

主程序不需要 privileged、宿主网络、Docker socket 或块设备写权限。只读 `/proc/1/mountinfo` 和 `/sys` 用于排除系统盘及识别设备。安装/更新需要 Docker 管理权限；日常容器使用指定的非 root UID/GID。

## 2. 配置与启动

解压后进入 `carddock` 目录。在以下命令中替换全部示例路径、UID/GID；不要直接复制示例值到未知 NAS。

```sh
python3 deploy.py configure \
  --source /实际外接存储挂载父目录 \
  --primary /实际主文件夹 \
  --state /实际状态目录 \
  --uid 1000 --gid 1000 --port 8080
```

需要备份时额外添加 `--backup /实际备份文件夹`；省略时不会要求或映射备份目录。配置输出到 `deployment/compose.json`（Compose 支持 JSON），权限为 0600。配置已存在时拒绝覆盖。可用 `--bind NAS局域网IP` 限定监听地址；默认所有网卡。自定义项目名使用 `--project carddock-work`，容器名称由 Compose 管理。

```sh
sudo python3 deploy.py start
```

默认在 NAS 本机从 Dockerfile 构建对应 CPU 的镜像，需要网络拉取基础镜像和 ExifTool 软件包。启动前以实际容器身份检查路径权限、已有源子挂载是否只读、宿主设备信息；失败会停止。首次打开 `http://NAS地址:8080/`，密钥位于 `deployment/compose.json` 的 `ACCESS_TOKEN` 字段，由安装时随机生成。在网页选择 `/destinations/primary`，需要备份时选择 `/destinations/backup`，保存设置后再开始拷贝。安装不会自动开始导入。

源、目标、状态目录不能重合或相互包含。不同路径仍可能指向相同存储，应用还会在任务提交时检查目录别名；不同文件夹不代表独立硬盘。

### 已有镜像或离线安装

导入匹配架构的镜像后，在 configure 命令增加 `--image carddock:0.12.0-beta.1-amd64` 或 `--image carddock:0.12.0-beta.1-arm64`：

```sh
sudo docker load -i carddock-0.12.0-beta.1-amd64.tar
```

指定镜像后不会本机构建；本地没有该镜像时尝试拉取。发布镜像应使用版本标签或 digest，避免同名标签被覆盖后更新结果不明确。

### 直接使用 Compose

熟悉 Docker 的管理员也可复制 `.env.example` 为 `.env`、填写路径和 UID/GID、创建并授权 `state` 目录，再执行 `docker compose up -d --build`。需要备份则执行 `docker compose -f compose.yaml -f compose.backup.yaml up -d --build`。直接 Compose 不会自动运行本项目的启动前检查；应先用相同 Compose 文件组合执行 `run --rm --no-deps --entrypoint python carddock /app/preflight.py`（先构建）。`deploy.py` 的更新/回退要求由该工具创建的配置快照，不能直接接管其他 Compose 项目。

## 3. NAS 管理员认证扩展（可选）

没有扩展也能使用拷贝和校验。点击“密钥管理”会显示终端操作说明。管理员可在安装目录执行：

```sh
sudo python3 access-key.py reset --compose-file deployment/compose.json
# 自定义密钥，交互式隐藏输入：
sudo python3 access-key.py reset --compose-file deployment/compose.json --custom
```

密钥即时生效，不中断拷贝，旧密钥失效；更新读取状态目录内已有密钥。

需要网页验证 NAS 管理员账号时，宿主必须具备 systemd、Python3、PAM、OpenSSL，并明确实际管理员组及 PAM 服务。扩展不是所有品牌通用的 NAS 账号 API。没有这些机制或启用特殊 MFA 的系统须另做厂商适配；不能随意选择普通用户组或跳过认证。

在 **首次 configure 前** 安装扩展，示例中的组、服务、GID及地址必须核实替换：

```sh
sudo sh admin/install.sh \
  --app-gid 1000 \
  --admin-group 实际管理员组 \
  --pam-service 实际PAM服务 \
  --host NAS实际IP或域名
```

随后 configure 增加 `--admin-host NAS实际IP或域名 --https-port 8443`，`--gid` 与 `--app-gid` 一致。访问 `https://NAS地址:8443/access-key`。首次生成自签名证书；也可由管理员安装可信证书。详见 [认证扩展说明](admin/README.md)。只安装此扩展需要宿主 root 服务；它仅验证身份，不执行外部命令、不记录密码。

已安装主程序再增加扩展会改变端口和卷映射，不属于普通镜像更新：先切手动、等任务结束，备份部署配置与状态，按同一项目名和原状态目录重新配置后由管理员执行 Compose 部署并记录新的部署快照。

## 4. 更新和回退

先在网页切换手动模式并保存，等待任务结束。将新版源码覆盖程序文件，保留 `deployment` 与独立状态目录；用外部镜像时仅修改生成配置中的 `image`。

```sh
sudo python3 deploy.py update
# 更新失败且没有任务运行时：
sudo python3 deploy.py rollback
```

更新会保存旧镜像标签与上一版部署配置，构建/拉取后先检查，再次确认无任务和自动导入关闭，最后替换容器。检查失败不替换服务。健康检查失败不会自动覆盖状态，应查看日志并决定回退。更新期间其他管理员不要提交新任务。仅支持镜像/构建更新，目录、账户、端口等变更会拒绝，需单独迁移。回退恢复镜像和 Compose 配置，不还原已拷贝素材或状态数据；跨数据库格式升级需使用对应备份。

## 5. 从当前绿联 V0.10 迁移

本工具不自动替换当前运行实例。现有实例有专用共享盘映射、密钥和状态路径，不能拿新生成的空配置直接覆盖。

1. 切手动、等待任务结束，保存当前 Compose 文件、镜像及状态目录备份。
2. 保留原状态目录，以及原 `ACCESS_TOKEN`（如未曾重置，旧密钥可能仍只存在旧 `.env`）；在新配置中填入原值，不要重置为 CardDock。
3. 保持已有配置所引用的容器内路径。例如原目标是 `/volume1/Media`，只改成 `/destinations/primary` 会导致旧配置不可访问，需保留映射或手动重新选目录。
4. 不要同时启动两个容器读写同一状态目录。新实例确认无误后再停止保留旧实例的回退准备。

私人部署脚本不放入通用发布包。

## 6. 构建发布与实机验收

在具备 Buildx 的构建机执行 `sh packaging/build-images.sh`，分别输出 AMD64、ARM64 的 Docker 镜像 tar 到 `dist/`。跨架构构建需构建机配置好模拟器或原生 builder。本脚本不会发布远端镜像。

发布到自有仓库时先登录，由管理员显式运行 `sh packaging/publish-images.sh 仓库/命名空间/carddock:0.12.0-beta.1`。源码包不包含登录凭据、生产状态、私钥或实际访问密钥。

每台 NAS 安装后至少验证：插卡前启动服务→插卡→设备出现；`sudo python3 deploy.py check` 检查新子挂载只读；单副本及可选备份 SHA256；拔卡重插；重启保留配置与密钥；系统盘和虚拟镜像不出现在自动来源中。网页认证扩展还需验证管理员成功、普通账户拒绝、新旧密钥切换。

热插拔传播依赖宿主挂载配置，老内核对子挂载的只读语义也有差异。检查失败时处理宿主设置，不能通过 privileged 绕开；未完成真实插拔测试前不标记该型号已支持。

官方参考：[多架构构建](https://docs.docker.com/build/building/multi-platform/)、[bind 挂载与传播](https://docs.docker.com/engine/storage/bind-mounts/)。
