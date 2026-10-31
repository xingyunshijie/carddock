# NAS V1.0 构建3 · 验证记录

日期：2026-10-31。所有传输测试采用临时合成素材，不使用用户照片。

## 验证范围

- 86项 Python 自动测试：全景与延时分类、代理、RAW/JPG伴随文件、多目标、队列、暂停取消、重试、报告、认证和路径保护。
- 原生 Linux amd64 与 arm64 分别构建完整镜像，运行镜像内的程序及启动检查，没有挂载宿主程序目录。
- 镜像默认 UID 1000/GID 10 能写入首次创建的专用数据卷。
- 非 root、只读容器根目录、只读源、临时目录及实际目标权限检查。
- 未登录请求拒绝；正确密码登录、退出失效。
- 全景 DNG/JPG 同组保存、代理归档、主盘接力备份；SHA-256、XXHash64、BLAKE3、MD5 均实际执行并检查结果。
- 重复导入重新复核已有内容；容器重启后主盘、备份设置保留。
- Docker Compose 语法、JavaScript、启动脚本及源码安装包完整性检查。
- 离线安装说明已用浏览器打开检查，代码块与安装用配置一致，共27行，无程序目录映射。

构建与测试记录：[GitHub Actions](https://github.com/xingyunshijie/carddock/actions/runs/41163236828)。失败的检查会阻止镜像发布；具体结果以该次运行页面为准。

## 尚需 NAS 实机验收

尚未在用户 NAS 上启动本次构建3。真实读卡器热插拔、宿主子挂载只读、共享目录权限、断网、断电及不同品牌 NAS 兼容性不能由云端容器测试代替。

首次安装先用少量可重复素材确认识别、拷贝、分类与备份哈希，再开启自动导入。完成后在 NAS 中安全弹出设备。

## 维护者复验

```sh
python -m unittest discover -s tests -v
docker compose -f compose.project.yaml config --quiet
docker build -t carddock:ci .
python packaging/smoke.py
```
