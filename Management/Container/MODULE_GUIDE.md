# Container 后端模块说明

这个项目是一个基于 Flask + Flask-SQLAlchemy 的集装箱管理后端，数据库使用 SQLite，数据库文件位于 `Container/instance/database.db`。

## 整体运行流程

1. 运行 `app.py` 启动 Flask 应用。
2. `app.py` 读取 `config.py` 中的 SQLite 配置。
3. `app.py` 初始化 `models/container_model.py` 中定义的 SQLAlchemy 数据库对象 `db`。
4. `app.py` 注册 `routes/container_route.py` 中定义的接口蓝图 `container_bp`。
5. 启动时执行 `db.create_all()`，如果 SQLite 中还没有对应表，会自动创建 `containers` 表。
6. 启动时执行 `seed_data()`，如果数据库为空，会插入 3 条示例集装箱数据。

## app.py

`app.py` 是项目入口文件，负责创建和启动 Flask 后端应用。

主要内容：

- `create_app()`
  - 创建 Flask 应用对象。
  - 加载 `Config` 配置。
  - 确保 `instance` 目录存在。
  - 初始化数据库连接。
  - 注册集装箱接口蓝图。
  - 创建数据库表。
  - 初始化示例数据。

- `seed_data()`
  - 用于插入测试数据。
  - 只有当 `containers` 表中没有任何数据时才会插入。
  - 插入的数据包括箱号、箱型、堆场和状态。

- `app = create_app()`
  - 创建全局 Flask 应用实例。
  - 方便直接运行，也方便后续被其他工具或测试引用。

- `if __name__ == '__main__':`
  - 当你直接执行 `python app.py` 时，启动 Flask 开发服务器。

## config.py

`config.py` 是项目配置文件，目前主要用于配置 SQLite 数据库地址。

主要内容：

- `BASE_DIR`
  - 表示 `Container` 项目目录。

- `DB_PATH`
  - 表示 SQLite 数据库文件路径。
  - 当前路径是 `Container/instance/database.db`。

- `Config.SQLALCHEMY_DATABASE_URI`
  - Flask-SQLAlchemy 使用的数据库连接地址。
  - 当前值等价于使用本地 SQLite 文件作为数据库。

- `Config.SQLALCHEMY_TRACK_MODIFICATIONS`
  - 设置为 `False`，关闭 SQLAlchemy 的对象修改追踪功能。
  - 这样可以减少额外性能开销，也避免启动时出现警告。

## models/container_model.py

`models/container_model.py` 是数据库模型文件，负责定义数据库连接对象和集装箱表结构。

主要内容：

- `db = SQLAlchemy()`
  - 创建 Flask-SQLAlchemy 数据库对象。
  - 它不会在这里直接连接数据库，而是在 `app.py` 中通过 `db.init_app(app)` 和 Flask 应用绑定。

- `class Container(db.Model)`
  - 表示一条集装箱记录。
  - 对应 SQLite 中的 `containers` 表。

字段说明：

- `id`
  - 主键，自增整数。

- `container_no`
  - 箱号。
  - 字符串，最多 30 个字符。
  - 必填。
  - 唯一，不能重复。

- `container_type`
  - 箱型，例如 `20GP`、`40HQ`。
  - 字符串，最多 10 个字符。
  - 必填。

- `is_full`
  - 是否重箱。
  - 布尔值。
  - 默认 `False`。

- `is_dangerous`
  - 是否危险品。
  - 布尔值。
  - 默认 `False`。

- `is_refrigerated`
  - 是否冷藏箱。
  - 布尔值。
  - 默认 `False`。

- `yard`
  - 堆场名称。

- `area`
  - 堆场区域。

- `column`
  - 堆场列号。

- `layer`
  - 堆场层号。

- `status`
  - 集装箱状态。
  - 默认状态是“在船中”。

- `to_dict()`
  - 把数据库模型对象转换成普通字典。
  - 路由返回 JSON 时会使用这个方法。

## routes/container_route.py

`routes/container_route.py` 是接口路由文件，负责处理前端或 API 客户端发来的 HTTP 请求。

主要内容：

- `container_bp = Blueprint('container_bp', __name__)`
  - 创建 Flask 蓝图。
  - 蓝图用于把一组相关接口集中管理。
  - 在 `app.py` 中通过 `app.register_blueprint(container_bp)` 注册到应用。

- `STATUS_FLOW`
  - 定义集装箱状态流转顺序。
  - 当前流转链路：
    - 在船中 -> 已卸船
    - 已卸船 -> 堆场存储
    - 堆场存储 -> 等待提箱
    - 等待提箱 -> 离港

接口说明：

### POST /containers

新增一个集装箱。

必填字段：

- `container_no`
- `container_type`

可选字段：

- `is_full`
- `is_dangerous`
- `is_refrigerated`
- `yard`
- `area`
- `column`
- `layer`
- `status`

处理逻辑：

- 读取请求 JSON。
- 检查必填字段。
- 创建 `Container` 对象。
- 写入 SQLite 数据库。
- 如果箱号重复，返回 409。
- 成功时返回新建后的集装箱数据。

### GET /containers

查询所有集装箱。

处理逻辑：

- 从数据库中按 `id` 排序查询全部记录。
- 每条记录调用 `to_dict()` 转成字典。
- 返回 JSON 数组。

### GET /containers/<id>

查询指定 ID 的集装箱。

处理逻辑：

- 根据 URL 中的 `id` 查询数据库。
- 如果找不到，Flask 会返回 404。
- 如果找到，返回该集装箱数据。

### PUT /containers/<id>

修改指定 ID 的集装箱基础信息。

可修改字段：

- `container_no`
- `container_type`
- `is_full`
- `is_dangerous`
- `is_refrigerated`
- `status`

处理逻辑：

- 先根据 `id` 找到集装箱。
- 用请求 JSON 中提供的字段更新对象。
- 没提供的字段保持原值。
- 提交数据库事务。
- 如果箱号重复，返回 409。

### PUT /containers/<id>/location

修改指定 ID 的集装箱位置。

可修改字段：

- `yard`
- `area`
- `column`
- `layer`

处理逻辑：

- 先根据 `id` 找到集装箱。
- 更新位置字段。
- 提交数据库事务。
- 返回更新后的数据。

### PUT /containers/<id>/next_status

让指定 ID 的集装箱进入下一个状态。

处理逻辑：

- 读取当前状态。
- 根据 `STATUS_FLOW` 找到下一个状态。
- 更新并保存到数据库。
- 如果当前状态已经不能继续流转，返回 400。

### DELETE /containers/<id>

删除指定 ID 的集装箱。

处理逻辑：

- 先根据 `id` 找到集装箱。
- 从数据库中删除。
- 提交数据库事务。
- 返回删除成功消息。

## SQLite 数据库说明

数据库文件：

```text
Container/instance/database.db
```

当前表：

```text
containers
```

项目使用 `db.create_all()` 自动建表。也就是说，只要模型存在、数据库文件可写，启动应用时会自动创建缺失的数据表。

注意：`db.create_all()` 只会创建不存在的表，不会自动修改已经存在的表结构。如果以后你修改了模型字段，并且数据库中已有旧表，可能需要手动迁移数据库或删除旧数据库文件重新生成。

## 推荐启动方式

进入项目目录：

```powershell
cd E:\Github\Management\Container
```

启动后端：

```powershell
python app.py
```

默认接口地址：

```text
http://127.0.0.1:5000
```

例如查询所有集装箱：

```text
GET http://127.0.0.1:5000/containers
```

## 当前检查结果

- SQLite 配置已经指向 `Container/instance/database.db`。
- `containers` 表已经存在。
- `containers` 表字段和 `Container` 模型字段匹配。
- 路由文件中包含新增、查询、修改、位置更新、状态流转、删除接口。
- 代码中的中文返回值使用 Unicode 转义保存，运行时仍会返回正常中文，这样可以避免 Windows 控制台编码导致源码乱码。
