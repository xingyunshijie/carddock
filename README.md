# CardDock · 影像归仓

**星云视界 出品** · 摄影存储卡安全导入工具 · 中文网页 · Docker

<img src="app/static/icon.svg" width="96" alt="仓库守护存储卡">

存储卡 → 主文件夹复制与校验 → 可选备份文件夹复制与校验。支持自动插卡导入、手动导入、重复文件复核、冲突文件保留，以及 RAW、JPG、视频、声音、视频代理分类。

**当前版本：0.12.0-beta.1，公开测试版。** 支持构建 Linux AMD64 / ARM64 镜像；不能把镜像能启动等同于所有 NAS 的读卡器、权限和热插拔都已验证。先用测试卡验证，再用于正式素材。

完整中文手册：[安装与使用帮助](docs/HELP.md)，程序底部也有帮助入口；安装包内 `CardDock-help.html` 可双击离线阅读。

## 下载与安装

到 [Releases](https://github.com/xingyunshijie/carddock/releases) 下载版本安装包及匹配架构的镜像。若尚无 Release，表示首轮构建尚未完成，源码不等于已验证镜像。

- **绿联 Docker 图形界面安装**：[安装指南](docs/UGREEN.md)。使用包内 `setup.html` 离线生成你的 Compose 配置，输入实际路径、UID/GID；不收集数据。
- **终端安装、启动前检查、更新与回退**：[通用安装指南](PORTABLE-INSTALL.md)。
- **后续版本与维护**：[更新发布流程](docs/RELEASING.md)、[更新记录](CHANGELOG.md)。

项目不是绿联官方应用，与绿联无隶属关系。需要 NAS 自己挂载读卡器；应用不格式化、不挂载、不弹出存储卡。主程序不需要特权模式、Docker socket 或主机网络。

## 功能

- Sony、Canon、Nikon、Panasonic、ARRI、DJI 常见目录识别；ExifTool 尝试读取机型，也可手动指定。
- 内置/USB 读卡器来源、按接口记忆 SD 编号；证据不足时允许手动设置。
- 自动或手动模式，默认手动。主文件夹必选，最多一个可选备份。
- 默认 SHA256；可选 MD5、快速数量/体积核对。快速模式不能发现等长内容损坏。
- 已有文件仍核对内容；同名不同内容保留两份，完整文件经校验后原子发布。
- 进度、粗略平均速度、暂停、继续、终止，逐文件 JSON 校验报告。
- 浏览已授权映射的存储区和子目录；不会自动开放整个 NAS。
- 每次新安装生成独立随机密钥，配置与任务记录保存在状态目录。

主文件夹校验完成后才提示可拔卡，此时备份可能尚未完成；仍需在 NAS 中安全弹出。所有副本核对前不要格式化原卡。不同文件夹不代表独立硬盘；主备建议在不同存储设备。

完整目录模式会保留普通伴随文件，但始终跳过隐藏文件、回收站、符号链接与特殊文件。需要摄影机工程的完整副本时请检查这些规则。代理按目录与文件名识别，不会生成代理或转码。

## 开发与验证

Python 3.9+，主服务仅依赖 Python 标准库；Docker 标准镜像额外安装 ExifTool。

```sh
python3 -m unittest discover -s tests -v
node --check app/static/app.js
python3 packaging/release.py
```

提交触发测试和双架构 Docker 构建；`v` 版本标签在测试通过后发布镜像及安装附件。实际硬件兼容记录见 [兼容性与验证](docs/COMPATIBILITY.md)。

## 授权

免费供个人非商业使用，保留“星云视界 出品”署名；修改、再发布和商用须另行授权。详见 [LICENSE](LICENSE)。这是公开源码的免费软件，不是 MIT 开源项目。分享时请链接到本仓库或 Releases。

问题反馈请使用 [Issues](https://github.com/xingyunshijie/carddock/issues)，说明 NAS 型号、系统版本、CPU 架构和去除密钥后的错误日志。不要上传访问密钥、账号密码、私人素材或包含密钥的 Compose 文件。
