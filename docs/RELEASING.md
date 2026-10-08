# 维护与发布

仓库 main 分支每次提交和 Pull Request 运行 Python、JavaScript 测试，并在原生 AMD64 / ARM64 runner 上构建镜像、执行容器内检查和合成文件主备 SHA256 验证。硬件热插拔由实机补充。

发布新版本：

1. 更新 VERSION、网页版本/更新说明、CHANGELOG，以及安装助手和 Compose/脚本中的镜像版本。
2. 本地跑测试，执行 `python3 packaging/release.py`，检查安装包不含私有配置。提交并推送 main，等待 CI 成功。
3. 创建与 VERSION 相同的 `v版本` 标签并推送。tag 工作流测试通过后，上传两个架构的固定版本镜像、组合多架构清单，创建 GitHub Release，并附安装包、离线镜像、SHA256SUMS。
4. 含 `-` 的版本作为 prerelease，不设置 latest 镜像标签。发布后确认下载可用、镜像包对公众可读。首次 GitHub Packages 可能需在包设置调整可见性；如镜像私有，用户仍可下载 Release 离线镜像。

Actions 使用仓库自身 GITHUB_TOKEN，无需把个人 token 写入源码。官方说明：[GitHub 镜像发布](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)、[Docker 多架构构建](https://docs.docker.com/build/ci/github-actions/multi-platform/)。

更新/回退必须在手动模式、没有拷贝任务时进行。GUI 用户只换镜像版本，保留原配置及状态；deploy.py 用户使用 update/rollback。不要覆盖部署文件中的随机密钥。旧版本标签和下载文件保留，发现问题发布修正版本，不覆盖原标签。

授权不是开源协议，接收他人修改或分发许可前应由作者确认授权条款。
