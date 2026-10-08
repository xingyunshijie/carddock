# 可选 Linux PAM 管理员认证扩展

主程序的素材拷贝、校验和访问密钥不依赖此扩展。只有需要在网页中使用 NAS 管理员账号验证后修改密钥，才需在 **NAS 宿主机** 安装本组件。未适配的 NAS 可继续使用主程序的终端密钥重置功能。

本适配器要求 Linux、运行中的 systemd、Python 3、OpenSSL、libpam，以及宿主机真实可用的 PAM 密码认证服务。不宣称跨品牌通用：某些 NAS 的网页账户、管理员角色或多因素认证不属于 Linux PAM，必须由该平台另行实现认证适配器。

## 安装

先由管理员确认应用容器使用的宿主机 GID、具有管理权限的真实 Linux 用户组、以及支持密码认证和账户有效性检查的 `/etc/pam.d/` 服务。参数没有品牌默认值；以下值仅为示例，需要替换：

```sh
sudo sh admin/install.sh \
  --app-gid 1000 \
  --admin-group nas-operators \
  --pam-service login \
  --host nas.example.local \
  --host 192.0.2.10
```

`--host` 可重复，填写 IP 或 DNS 名，不带协议或端口。安装器检查组、PAM 配置、系统依赖后生成配置和服务；它不会修改管理员组成员，也不会创建或改写 PAM 服务。指定组的成员才允许认证，root 也没有隐式绕过。上线前必须用目标 NAS 的真实管理员和普通账号分别验证成功及拒绝行为。

首次安装生成自签 TLS 证书。已有完整证书保持不变；域名/IP 改变时明确传 `--replace-certificate` 重新生成，或提供自行签发的证书。`--no-start` 仅安装文件并重载 systemd，不启用或重启服务。安装器不更新或重启主应用、不调用 `update.sh`。

## 主应用接口和权限

- Unix socket：`/run/carddock-admin/auth.sock`，容器映射整个 `/run/carddock-admin` 目录；服务启动后再启动需要该挂载的容器。
- 请求：单行 JSON `{"username":"alice","password":"..."}`；响应：单行 JSON `{"ok":true}` 或 `{"ok":false}`。
- 配置：`/etc/carddock/admin.json`，root 所有，权限 `0600`，保存 `app_gid`、`admin_group`、`pam_service`。
- 服务使用 root 执行 PAM；运行目录为 `root:<app-gid>`、`0750`，socket 为 `root:<app-gid>`、`0660`。
- 证书：`/etc/carddock/tls/server.crt`、`server.key`；目录 `root:<app-gid>`、`0750`，私钥 `0640`，证书 `0644`。容器只读挂载 TLS 目录，其运行用户的主组或附加组必须包含此 GID。
- 单进程全局每分钟最多 10 次认证请求；不记录密码、不执行传入命令、不直接修改应用访问密钥。

调整参数后重新执行安装器。诊断使用 `systemctl status carddock-admin.service` 与 `journalctl -u carddock-admin.service`。停用可执行 `sudo systemctl disable --now carddock-admin.service`，并移除主应用的认证及 TLS 挂载配置（如仍使用 TLS，应保留证书挂载）。
