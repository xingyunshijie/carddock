# NAS 构建5 更新与迁移

## 新安装

按 [NAS安装说明.md](NAS安装说明.md) 创建项目。默认使用项目内 inbox、archive、data，不依赖特定 NAS 的共享目录名称。新安装自动创建 archive/影像归仓 作为主盘，备份留空。

## 已有实例

关闭自动导入，等待任务结束，备份原项目配置和 state/data 后再更新。保持项目名、原状态映射、共享目录映射和容器内路径。不要把新的空 data 替换掉已有 state，不要让两个容器同时写一个状态目录。

若从构建3升级且原目标为 /storage/area1 与 /storage/area2，必须保留原映射，并在 environment 中显式设置：

```yaml
      TARGET_ROOTS: /storage/area1:/storage/area2
      MANUAL_SOURCE_ROOTS: /manual/area1:/manual/area2
```

保持原来的运行身份：构建3默认1000:10，可添加 `PUID: "1000"`、`PGID: "10"`，也可保留原 user 配置。实际身份以原项目为准。已有设置不被新默认目录覆盖。

## 更新、回退和删除

更新只修改镜像版本，保留所有目录和数据卷。回退时恢复原项目配置及必要的升级前状态备份；构建2还需要原上传程序目录。

删除项目文件夹会同时删除其中 inbox、archive 的素材和 data 的历史，不能当成普通程序卸载目录直接清理。旧版使用 Docker 数据卷时也应保留原卷，直到确认资料已迁移。
