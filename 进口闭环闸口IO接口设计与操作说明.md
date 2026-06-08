# 进口闭环闸口 IO 接口设计、操作说明与服务器端响应

## 1. 文档说明

本文档用于说明集装箱码头管理系统中“进口闭环管理”模块的前后端 IO 接口设计，重点覆盖以下业务：

- 海关/商检放行
- 创建提箱预约
- 车牌视觉识别自动进闸/出闸
- 人工备用进闸/出闸
- 堆场提箱
- 异常登记与关闭
- 页面数据刷新与闸口记录查询

本文档对应前端页面：

```text
pages/import-lifecycle.html
js/import-lifecycle.js
```

对应后端路由：

```text
Management/Container/routes/import_lifecycle_route.py
```

接口统一前缀：

```text
/api/import
```

默认服务地址：

```text
http://127.0.0.1:5000
```

如果前端页面通过 Flask 服务器访问，则前端会自动使用当前站点地址作为 `API_BASE`；如果直接打开 HTML，则默认请求 `http://127.0.0.1:5000`。

## 2. 总体业务流程

进口箱提箱与闸口业务按照如下顺序执行：

```text
集装箱在堆场
  ↓
海关/商检放行
  ↓
创建提箱预约，绑定车牌号与箱号
  ↓
车辆到达闸口
  ↓
方式 A：上传闸口图片，YOLOv5 检测车牌区域，LPRNet 识别车牌号
方式 B：自动识别失败时，人工输入预约号/车牌/箱号
  ↓
服务器根据车牌号查找预约单
  ↓
预约状态为“已确认”：允许进闸
  ↓
车辆进入堆场，完成堆场提箱
  ↓
预约状态为“已提箱”：允许出闸
  ↓
集装箱状态变为“离港”
```

关键规则：

- 视觉识别只识别车牌号，不识别集装箱号。
- 集装箱号来自预约单中绑定的箱号。
- 车辆进闸前，预约状态必须是 `已确认`。
- 车辆出闸前，预约状态必须是 `已提箱`。
- 集装箱必须为 `已放行`，否则闸口拦截。
- 自动识别失败时，可以通过人工备用进出闸接口继续处理业务。

## 3. 权限设计

后端在 `app.py` 中对 `/api/import` 接口做权限控制。

| 操作类型 | 请求路径/方法 | 所需权限 |
|---|---|---|
| 查看进口闭环数据 | `GET /api/import/**` | `import:read` |
| 创建预约 | `POST /api/import/appointments` | `appointment:write` |
| 取消预约 | `PUT /api/import/appointments/{id}/cancel` | `appointment:write` |
| 登记异常 | `POST /api/import/exceptions` | `exception:write` |
| 放行、闸口、提箱、关闭异常等操作 | 其他非 GET `/api/import/**` | `import:operate` |

典型角色：

- 管理员：拥有全部权限。
- 调度员：通常拥有进口业务读写和闸口操作权限。
- 客户：一般只允许查看与预约相关的部分功能。
- 财务人员：通常不直接操作进口闸口业务。

前端请求会携带登录 Cookie：

```js
credentials: 'include'
```

因此调用接口前需要先登录系统。

## 4. 通用请求与响应规范

### 4.1 JSON 请求

除视觉识别接口外，大部分接口使用 JSON 请求体：

```http
Content-Type: application/json
```

前端通用封装：

```js
fetch(`${API_BASE}${path}`, {
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  method: 'POST',
  body: JSON.stringify(payload)
})
```

### 4.2 图片上传请求

视觉闸口接口使用 `multipart/form-data`：

```js
const formData = new FormData();
formData.append('image', imageFile);
formData.append('gateType', 'auto');

fetch(`${API_BASE}/api/import/gate/vision`, {
  method: 'POST',
  credentials: 'include',
  body: formData
})
```

注意：上传图片时不要手动设置 `Content-Type`，浏览器会自动添加 boundary。

### 4.3 通用成功响应

成功时通常返回：

```json
{
  "message": "操作成功说明",
  "data": {}
}
```

部分接口还会返回：

```json
{
  "appointment": {},
  "container": {},
  "task": {},
  "ticketNo": "TICKET-..."
}
```

### 4.4 通用失败响应

失败时通常返回：

```json
{
  "message": "失败原因"
}
```

常见 HTTP 状态码：

| 状态码 | 含义 |
|---|---|
| `200` | 操作成功 |
| `201` | 创建成功 |
| `400` | 请求参数错误、业务校验失败、闸口拦截 |
| `401` | 未登录 |
| `403` | 无权限 |
| `404` | 资源不存在或未找到对应预约 |
| `500` | 服务器内部错误 |

## 5. 数据对象结构

### 5.1 集装箱对象 Container

典型返回结构：

```json
{
  "id": 1,
  "containerNo": "CONT000001",
  "containerType": "20GP",
  "status": "等待提箱",
  "customsStatus": "已放行",
  "appointmentStatus": "已预约锁定",
  "damageStatus": "正常",
  "yard": "普通堆场",
  "zone": "A区",
  "row": 1,
  "tier": 1,
  "isDangerous": false,
  "isReefer": false,
  "lockedByAppointmentId": 3
}
```

关键字段：

| 字段 | 说明 |
|---|---|
| `containerNo` | 集装箱号 |
| `status` | 箱子当前业务状态 |
| `customsStatus` | 海关/商检放行状态，常用值：`未放行`、`已放行` |
| `appointmentStatus` | 预约状态 |
| `damageStatus` | 残损状态 |
| `lockedByAppointmentId` | 当前锁定该箱的预约 ID |

### 5.2 预约对象 PickupAppointment

```json
{
  "id": 3,
  "appointmentNo": "APT-20260608120000123",
  "containerId": 1,
  "containerNo": "CONT000001",
  "truckPlate": "沪A12345",
  "driverName": "张三",
  "driverPhone": "13800000000",
  "customer": "某货代公司",
  "timeWindowStart": "2026-06-08 14:00",
  "timeWindowEnd": "2026-06-08 16:00",
  "status": "已确认",
  "createdAt": "2026-06-08 12:00:00",
  "updatedAt": "2026-06-08 12:00:00",
  "remark": "",
  "container": {}
}
```

预约状态流转：

```text
已确认 -> 已进闸 -> 已提箱 -> 已出闸
```

取消流程：

```text
待确认/已确认 -> 已取消
```

### 5.3 闸口记录 GateTransaction

```json
{
  "id": 10,
  "appointmentId": 3,
  "appointmentNo": "APT-20260608120000123",
  "gateType": "进闸",
  "truckPlate": "沪A12345",
  "containerNo": "CONT000001",
  "checkResult": "通过",
  "blockReason": "",
  "ticketNo": "TICKET-20260608142000123",
  "createdAt": "2026-06-08 14:20:00"
}
```

关键字段：

| 字段 | 说明 |
|---|---|
| `gateType` | `进闸`、`出闸`、`视觉闸口` |
| `checkResult` | `通过` 或 `拦截` |
| `blockReason` | 拦截原因 |
| `ticketNo` | 进闸/出闸小票号 |

### 5.4 异常记录 ExceptionRecord

```json
{
  "id": 5,
  "objectType": "gate",
  "objectId": null,
  "exceptionType": "视觉闸口拦截",
  "description": "未找到车牌 沪A12345 对应的有效预约",
  "status": "待处理",
  "handler": "",
  "resolution": "",
  "createdAt": "2026-06-08 14:20:00",
  "resolvedAt": null
}
```

## 6. 接口详细设计

### 6.1 获取进口闭环总览

```http
GET /api/import/overview
```

用途：

- 刷新页面 KPI。
- 获取最近预约列表。
- 获取最近闸口记录。
- 获取最近异常记录。

前端调用位置：

```js
loadOverview()
```

请求参数：无。

成功响应：

```json
{
  "stats": {
    "inYard": 12,
    "customsReleased": 8,
    "waitingRelease": 4,
    "activeAppointments": 3,
    "gateBlocks": 1,
    "openExceptions": 1
  },
  "appointments": [],
  "gateTransactions": [],
  "exceptions": []
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `inYard` | 当前在场可处理箱数量 |
| `customsReleased` | 已放行箱数量 |
| `waitingRelease` | 未放行箱数量 |
| `activeAppointments` | 有效预约数量 |
| `gateBlocks` | 闸口拦截记录数量 |
| `openExceptions` | 未关闭异常数量 |

### 6.2 获取可预约/可处理集装箱

```http
GET /api/import/containers/pickup-ready
```

用途：

- 页面“待放行/可预约集装箱”表格数据来源。
- 返回状态为 `堆场存储`、`在场`、`等待提箱` 的箱子。
- 排除已经被其他预约锁定的箱子。

成功响应：

```json
[
  {
    "id": 1,
    "containerNo": "CONT000001",
    "status": "等待提箱",
    "customsStatus": "已放行",
    "appointmentStatus": "未预约",
    "yard": "普通堆场",
    "zone": "A区",
    "row": 1,
    "tier": 1
  }
]
```

### 6.3 查询放行记录

```http
GET /api/import/customs/releases
```

用途：

- 查询海关/商检放行记录。

成功响应：

```json
[
  {
    "id": 1,
    "containerId": 1,
    "containerNo": "CONT000001",
    "customsStatus": "已放行",
    "inspectionStatus": "已通过",
    "releaseNo": "REL-20260608120000123",
    "releasedAt": "2026-06-08 12:00:00",
    "holdReason": "",
    "updatedAt": "2026-06-08 12:00:00"
  }
]
```

### 6.4 更新海关/商检放行状态

```http
POST /api/import/customs/release
Content-Type: application/json
```

用途：

- 将集装箱设置为 `已放行`。
- 或登记未放行原因。
- 同步更新 `container.customs_status`。

请求参数：

```json
{
  "containerId": 1,
  "containerNo": "CONT000001",
  "customsStatus": "已放行",
  "inspectionStatus": "已通过",
  "releaseNo": "REL-20260608120000123",
  "holdReason": ""
}
```

参数说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `containerId` | 否 | 集装箱数据库 ID，优先使用 |
| `containerNo` | 否 | 集装箱号；未传 `containerId` 时使用 |
| `customsStatus` | 否 | 默认 `已放行` |
| `inspectionStatus` | 否 | 默认 `已通过` |
| `releaseNo` | 否 | 不传则后端自动生成 |
| `holdReason` | 否 | 未放行原因 |

成功响应：

```json
{
  "message": "放行状态已更新",
  "data": {
    "id": 1,
    "containerId": 1,
    "containerNo": "CONT000001",
    "customsStatus": "已放行",
    "inspectionStatus": "已通过",
    "releaseNo": "REL-20260608120000123",
    "releasedAt": "2026-06-08 12:00:00",
    "holdReason": "",
    "updatedAt": "2026-06-08 12:00:00"
  },
  "container": {
    "id": 1,
    "containerNo": "CONT000001",
    "customsStatus": "已放行"
  }
}
```

失败响应：

```json
{
  "message": "集装箱不存在"
}
```

HTTP 状态码：

```text
404
```

### 6.5 查询全部预约

```http
GET /api/import/appointments
```

用途：

- 查询全部预约记录。

成功响应：

```json
[
  {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "containerNo": "CONT000001",
    "truckPlate": "沪A12345",
    "status": "已确认"
  }
]
```

### 6.6 创建提箱预约

```http
POST /api/import/appointments
Content-Type: application/json
```

用途：

- 绑定集装箱、车牌号、司机信息和预约时间窗。
- 创建成功后，集装箱被预约锁定。
- 如果集装箱状态为 `堆场存储` 或 `在场`，后端会将箱状态改为 `等待提箱`。

请求参数：

```json
{
  "containerNo": "CONT000001",
  "truckPlate": "沪A12345",
  "driverName": "张三",
  "driverPhone": "13800000000",
  "customer": "某货代公司",
  "timeWindowStart": "2026-06-08 14:00",
  "timeWindowEnd": "2026-06-08 16:00",
  "remark": "正常提箱"
}
```

参数说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `containerId` | 否 | 集装箱数据库 ID |
| `containerNo` | 是 | 集装箱号；未传 `containerId` 时必填 |
| `truckPlate` | 是 | 预约车牌号，视觉识别后会用它匹配预约 |
| `driverName` | 否 | 司机姓名 |
| `driverPhone` | 否 | 联系电话 |
| `customer` | 否 | 客户/货代 |
| `timeWindowStart` | 是 | 预约开始时间 |
| `timeWindowEnd` | 是 | 预约结束时间 |
| `remark` | 否 | 备注 |

成功响应：

```json
{
  "message": "提箱预约已创建",
  "data": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "containerId": 1,
    "containerNo": "CONT000001",
    "truckPlate": "沪A12345",
    "driverName": "张三",
    "driverPhone": "13800000000",
    "customer": "某货代公司",
    "timeWindowStart": "2026-06-08 14:00",
    "timeWindowEnd": "2026-06-08 16:00",
    "status": "已确认",
    "createdAt": "2026-06-08 12:00:00",
    "updatedAt": "2026-06-08 12:00:00"
  }
}
```

HTTP 状态码：

```text
201
```

常见失败响应：

```json
{
  "message": "海关未放行，禁止预约提箱"
}
```

```json
{
  "message": "该箱已有未完成预约：APT-20260608120000123"
}
```

```json
{
  "message": "车牌号不能为空"
}
```

```json
{
  "message": "预约时间窗不能为空"
}
```

```json
{
  "message": "预约开始时间必须早于结束时间"
}
```

失败状态码通常为：

```text
400
```

### 6.7 取消预约

```http
PUT /api/import/appointments/{appointment_id}/cancel
```

用途：

- 取消 `待确认` 或 `已确认` 状态的预约。
- 释放集装箱预约锁定。
- 如果箱状态是 `等待提箱`，则恢复为 `堆场存储`。

路径参数：

| 参数 | 说明 |
|---|---|
| `appointment_id` | 预约数据库 ID |

成功响应：

```json
{
  "message": "预约已取消",
  "data": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "status": "已取消"
  }
}
```

失败响应：

```json
{
  "message": "预约状态为“已进闸”，不能取消"
}
```

### 6.8 完成堆场提箱

```http
POST /api/import/appointments/{appointment_id}/pickup
```

用途：

- 车辆进闸后，由调度员确认堆场提箱完成。
- 创建一条 `堆场提箱` 类型的任务记录。
- 将预约状态更新为 `已提箱`。
- 将集装箱状态更新为 `已装车待出闸`。

前置条件：

```text
预约状态必须是：已进闸
```

成功响应：

```json
{
  "message": "堆场提箱已完成",
  "data": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "status": "已提箱"
  },
  "task": {
    "id": 8,
    "taskNo": "PICK-20260608143000123",
    "taskName": "堆场提箱",
    "status": "completed",
    "containerDbId": 1,
    "destination": "沪A12345"
  }
}
```

失败响应：

```json
{
  "message": "车辆未进闸，不能执行堆场提箱"
}
```

## 7. 闸口 IO 接口详细说明

### 7.1 人工进闸

```http
POST /api/import/gate/in
Content-Type: application/json
```

用途：

- 自动识别失败时，调度员手动输入预约号、车牌号和箱号进行进闸校验。
- 页面队列中的“人工进闸”按钮也调用该接口。

请求参数：

```json
{
  "appointmentNo": "APT-20260608120000123",
  "containerNo": "CONT000001",
  "truckPlate": "沪A12345"
}
```

参数说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `appointmentNo` | 否 | 预约号；传入后优先按预约号查找 |
| `containerNo` | 否 | 箱号；未传预约号时可用于辅助查询 |
| `truckPlate` | 否 | 车牌号；未传预约号时可用于辅助查询 |

建议：

- 人工备用表单最好同时填写 `appointmentNo`、`containerNo`、`truckPlate`。
- 队列按钮会自动带出三项参数。

后端校验规则：

| 校验项 | 通过条件 |
|---|---|
| 预约存在 | 能找到有效预约 |
| 预约状态 | 必须为 `已确认` |
| 车牌一致 | 请求车牌必须等于预约车牌 |
| 箱号一致 | 请求箱号必须等于预约绑定箱号 |
| 海关放行 | 集装箱 `customsStatus` 必须为 `已放行` |
| 时间窗 | 当前时间必须在预约时间窗前后 30 分钟宽限范围内 |

成功响应：

```json
{
  "message": "闸口进场通过",
  "ticketNo": "TICKET-20260608142000123",
  "data": {
    "id": 10,
    "appointmentId": 3,
    "appointmentNo": "APT-20260608120000123",
    "gateType": "进闸",
    "truckPlate": "沪A12345",
    "containerNo": "CONT000001",
    "checkResult": "通过",
    "blockReason": "",
    "ticketNo": "TICKET-20260608142000123",
    "createdAt": "2026-06-08 14:20:00"
  },
  "appointment": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "status": "已进闸"
  }
}
```

失败响应示例：

```json
{
  "message": "未找到有效预约",
  "appointment": null
}
```

```json
{
  "message": "预约状态为“已提箱”，不能进闸",
  "appointment": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "status": "已提箱"
  }
}
```

```json
{
  "message": "车牌与预约不一致",
  "appointment": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123"
  }
}
```

失败时，服务器会自动：

- 写入一条 `GateTransaction`，结果为 `拦截`。
- 写入一条 `ExceptionRecord`，用于异常闭环处理。

### 7.2 人工出闸

```http
POST /api/import/gate/out
Content-Type: application/json
```

用途：

- 自动识别失败时，调度员手动执行出闸。
- 页面队列中的“人工出闸”按钮也调用该接口。

请求参数：

```json
{
  "appointmentNo": "APT-20260608120000123",
  "containerNo": "CONT000001",
  "truckPlate": "沪A12345"
}
```

后端校验规则：

| 校验项 | 通过条件 |
|---|---|
| 预约存在 | 能找到有效预约 |
| 预约状态 | 必须为 `已提箱` |
| 车牌一致 | 请求车牌必须等于预约车牌 |
| 箱号一致 | 请求箱号必须等于预约绑定箱号 |
| 海关放行 | 集装箱 `customsStatus` 必须为 `已放行` |

成功响应：

```json
{
  "message": "闸口出场通过，集装箱已离港",
  "data": {
    "id": 11,
    "appointmentId": 3,
    "appointmentNo": "APT-20260608120000123",
    "gateType": "出闸",
    "truckPlate": "沪A12345",
    "containerNo": "CONT000001",
    "checkResult": "通过",
    "blockReason": "",
    "ticketNo": "OUT-20260608153000123",
    "createdAt": "2026-06-08 15:30:00"
  },
  "appointment": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "status": "已出闸"
  }
}
```

出闸成功后，服务器状态变更：

| 对象 | 字段 | 新值 |
|---|---|---|
| 预约 | `status` | `已出闸` |
| 集装箱 | `status` | `离港` |
| 集装箱 | `appointment_status` | `已出闸` |
| 集装箱 | `locked_by_appointment_id` | `null` |

失败响应示例：

```json
{
  "message": "预约状态为“已进闸”，必须完成堆场提箱后才能出闸",
  "appointment": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "status": "已进闸"
  }
}
```

### 7.3 视觉识别自动闸口

```http
POST /api/import/gate/vision
Content-Type: multipart/form-data
```

用途：

- 上传闸口摄像头图片。
- 后端保存图片。
- 使用 YOLOv5 检测车牌区域。
- 使用 LPRNet 识别车牌号。
- 用识别出的车牌号查找预约单。
- 由预约状态自动判断进闸或出闸。

请求参数：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `image` | File | 是 | 闸口摄像头图片 |
| `file` | File | 否 | 与 `image` 二选一 |
| `gateType` | String | 否 | `auto`、`in`、`out`，默认 `auto` |

`gateType` 说明：

| 值 | 说明 |
|---|---|
| `auto` | 后端根据预约状态自动判断进闸或出闸 |
| `in` | 强制按进闸处理 |
| `out` | 强制按出闸处理 |

前端发送示例：

```js
const formData = new FormData();
formData.append('image', visionImage.value);
formData.append('gateType', 'auto');

const resp = await fetch(`${API_BASE}/api/import/gate/vision`, {
  method: 'POST',
  credentials: 'include',
  body: formData
});
```

后端处理步骤：

```text
1. 校验 gateType 是否为 auto/in/out。
2. 校验是否上传图片。
3. 将图片保存到 instance/gate_vision。
4. 调用 YOLOv5 + LPRNet 识别车牌。
5. 根据识别出的车牌号查询有效预约。
6. 如果 gateType=auto：
   - 预约状态为“已确认”则进闸。
   - 预约状态为“已提箱”则出闸。
   - 其他状态不允许自动处理。
7. 写入闸口记录。
8. 成功或失败都返回 JSON 响应。
```

成功响应：自动进闸

```json
{
  "message": "闸口进场通过",
  "recognizedPlate": "沪A12345",
  "gateType": "进闸",
  "appointment": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "containerNo": "CONT000001",
    "truckPlate": "沪A12345",
    "status": "已进闸"
  },
  "containerNo": "CONT000001",
  "data": {
    "id": 10,
    "gateType": "进闸",
    "truckPlate": "沪A12345",
    "containerNo": "CONT000001",
    "checkResult": "通过",
    "ticketNo": "TICKET-20260608142000123"
  }
}
```

成功响应：自动出闸

```json
{
  "message": "闸口出场通过，集装箱已离港",
  "recognizedPlate": "沪A12345",
  "gateType": "出闸",
  "appointment": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "containerNo": "CONT000001",
    "truckPlate": "沪A12345",
    "status": "已出闸"
  },
  "containerNo": "CONT000001",
  "data": {
    "id": 11,
    "gateType": "出闸",
    "truckPlate": "沪A12345",
    "containerNo": "CONT000001",
    "checkResult": "通过",
    "ticketNo": "OUT-20260608153000123"
  }
}
```

失败响应：闸口类型错误

```json
{
  "message": "闸口类型只能是 auto、in 或 out"
}
```

HTTP 状态码：

```text
400
```

失败响应：未上传图片

```json
{
  "message": "请上传闸口识别图片"
}
```

HTTP 状态码：

```text
400
```

失败响应：视觉识别失败

```json
{
  "message": "车牌视觉识别失败：YOLOv5 + LPRNet 车牌识别失败：YOLOv5 未检测到车牌区域"
}
```

可能的识别失败原因：

| 原因 | 说明 |
|---|---|
| `图片文件不存在` | 上传保存路径不存在 |
| `图片文件为空` | 上传文件为空 |
| `图片解码失败` | 图片格式损坏或不支持 |
| `YOLOv5 未检测到车牌区域` | 检测模型未找到车牌 |
| `LPRNet 未识别出车牌号` | 检测到车牌，但字符识别失败 |
| 缺少依赖 | 未安装 `torch`、`opencv-python`、`numpy` 等 |
| 权重不存在 | `yolov5_best.pt` 或 `lprnet_best.pth` 路径错误 |

失败响应：识别到车牌但没有预约

```json
{
  "message": "未找到车牌 沪A12345 对应的有效预约",
  "recognizedPlate": "沪A12345"
}
```

HTTP 状态码：

```text
404
```

此时服务器会：

- 写入一条闸口拦截记录。
- 写入一条异常记录。

失败响应：预约状态不允许自动处理

```json
{
  "message": "预约状态为“已进闸”，当前不能自动进闸或出闸",
  "recognizedPlate": "沪A12345",
  "gateType": "自动闸口",
  "appointment": {
    "id": 3,
    "appointmentNo": "APT-20260608120000123",
    "status": "已进闸"
  },
  "containerNo": "CONT000001",
  "data": null
}
```

HTTP 状态码：

```text
400
```

## 8. 异常闭环接口

### 8.1 查询异常列表

```http
GET /api/import/exceptions
```

成功响应：

```json
[
  {
    "id": 5,
    "objectType": "gate",
    "objectId": null,
    "exceptionType": "视觉闸口拦截",
    "description": "未找到车牌 沪A12345 对应的有效预约",
    "status": "待处理",
    "handler": "",
    "resolution": "",
    "createdAt": "2026-06-08 14:20:00",
    "resolvedAt": null
  }
]
```

### 8.2 登记异常

```http
POST /api/import/exceptions
Content-Type: application/json
```

请求参数：

```json
{
  "objectType": "gate",
  "objectId": 10,
  "exceptionType": "车牌不符",
  "description": "现场车牌与预约车牌不一致"
}
```

参数说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `objectType` | 否 | `container`、`appointment`、`gate`、`manual` |
| `objectId` | 否 | 关联对象 ID |
| `exceptionType` | 否 | 异常类型，默认 `人工异常` |
| `description` | 是 | 异常描述 |

成功响应：

```json
{
  "message": "异常已登记",
  "data": {
    "id": 6,
    "objectType": "gate",
    "objectId": 10,
    "exceptionType": "车牌不符",
    "description": "现场车牌与预约车牌不一致",
    "status": "待处理",
    "createdAt": "2026-06-08 14:30:00"
  }
}
```

HTTP 状态码：

```text
201
```

### 8.3 关闭异常

```http
PUT /api/import/exceptions/{record_id}/resolve
Content-Type: application/json
```

请求参数：

```json
{
  "handler": "调度员",
  "resolution": "异常已核验并关闭"
}
```

成功响应：

```json
{
  "message": "异常已关闭",
  "data": {
    "id": 6,
    "status": "已关闭",
    "handler": "调度员",
    "resolution": "异常已核验并关闭",
    "resolvedAt": "2026-06-08 14:35:00"
  }
}
```

## 9. 前端操作说明

### 9.1 海关放行

操作路径：

```text
进口闭环管理 -> 放行与预约 -> 待放行/可预约集装箱 -> 放行
```

前端动作：

```text
点击“放行”
```

发送接口：

```http
POST /api/import/customs/release
```

发送数据：

```json
{
  "containerId": 1,
  "customsStatus": "已放行",
  "inspectionStatus": "已通过"
}
```

服务器响应：

```json
{
  "message": "放行状态已更新",
  "data": {},
  "container": {}
}
```

### 9.2 创建预约

操作路径：

```text
进口闭环管理 -> 放行与预约 -> 创建提箱预约
```

操作步骤：

1. 选择已放行集装箱。
2. 填写车牌号。
3. 填写司机、联系电话、客户、预约时间窗。
4. 点击“确认预约”。

发送接口：

```http
POST /api/import/appointments
```

服务器响应：

```json
{
  "message": "提箱预约已创建",
  "data": {
    "appointmentNo": "APT-...",
    "status": "已确认"
  }
}
```

### 9.3 视觉识别自动进闸

适用场景：

```text
预约状态 = 已确认
车辆到达闸口
```

操作路径：

```text
进口闭环管理 -> 闸口作业 -> 视觉识别自动闸口
```

操作步骤：

1. 闸口动作选择 `自动判断` 或 `进闸`。
2. 上传包含车辆车牌的图片。
3. 点击“识别并自动放行”。

发送接口：

```http
POST /api/import/gate/vision
```

服务器处理：

```text
识别车牌 -> 查找预约 -> 校验预约状态/车牌/箱号/放行/时间窗 -> 更新为已进闸
```

成功后：

```text
预约状态：已确认 -> 已进闸
集装箱 appointmentStatus：已进闸
生成 gate_transaction 记录
```

### 9.4 堆场提箱

适用场景：

```text
预约状态 = 已进闸
车辆已进入堆场
```

操作路径：

```text
进口闭环管理 -> 闸口作业 -> 预约作业队列 -> 提箱
```

发送接口：

```http
POST /api/import/appointments/{id}/pickup
```

成功后：

```text
预约状态：已进闸 -> 已提箱
集装箱状态：已装车待出闸
创建堆场提箱任务记录
```

### 9.5 视觉识别自动出闸

适用场景：

```text
预约状态 = 已提箱
车辆装箱后到达出闸口
```

操作路径：

```text
进口闭环管理 -> 闸口作业 -> 视觉识别自动闸口
```

操作步骤：

1. 闸口动作选择 `自动判断` 或 `出闸`。
2. 上传包含车辆车牌的图片。
3. 点击“识别并自动放行”。

发送接口：

```http
POST /api/import/gate/vision
```

成功后：

```text
预约状态：已提箱 -> 已出闸
集装箱状态：离港
集装箱预约锁定解除
生成出闸记录
```

### 9.6 人工备用进闸/出闸

适用场景：

- 车牌识别失败。
- 现场光线差。
- 图片模糊。
- 摄像头未拍到车牌。
- 模型依赖或权重异常。
- 调度员确认后需要人工放行。

操作路径：

```text
进口闭环管理 -> 闸口作业 -> 人工备用进出闸
```

方式一：队列按钮

```text
预约作业队列 -> 人工进闸 / 人工出闸
```

方式二：手动输入

```text
填写预约号、箱号、车牌号 -> 点击人工进闸/人工出闸
```

人工进闸接口：

```http
POST /api/import/gate/in
```

人工出闸接口：

```http
POST /api/import/gate/out
```

## 10. 典型完整调用链

### 10.1 正常自动进出闸链路

```text
1. GET /api/import/containers/pickup-ready
   获取可处理箱

2. POST /api/import/customs/release
   放行集装箱

3. POST /api/import/appointments
   创建预约，绑定车牌和箱号

4. POST /api/import/gate/vision
   上传进闸图片，识别车牌，自动进闸

5. POST /api/import/appointments/{id}/pickup
   堆场提箱

6. POST /api/import/gate/vision
   上传出闸图片，识别车牌，自动出闸

7. GET /api/import/overview
   刷新状态、记录和异常
```

### 10.2 自动识别失败后的人工兜底链路

```text
1. POST /api/import/gate/vision
   自动识别失败

2. 系统返回 message：
   车牌视觉识别失败：...

3. 调度员人工核验现场车辆、预约号、箱号

4. POST /api/import/gate/in
   或
   POST /api/import/gate/out

5. 服务器继续执行同样的业务校验

6. 成功则放行，失败则记录闸口拦截和异常
```

## 11. 服务器端状态变更汇总

### 11.1 创建预约

| 对象 | 字段 | 新值 |
|---|---|---|
| 预约 | `status` | `已确认` |
| 集装箱 | `appointment_status` | `已预约锁定` |
| 集装箱 | `locked_by_appointment_id` | 当前预约 ID |
| 集装箱 | `status` | `等待提箱`，如果原状态为 `堆场存储` 或 `在场` |

### 11.2 进闸成功

| 对象 | 字段 | 新值 |
|---|---|---|
| 预约 | `status` | `已进闸` |
| 预约 | `updated_at` | 当前时间 |
| 集装箱 | `appointment_status` | `已进闸` |
| 闸口记录 | `check_result` | `通过` |

### 11.3 堆场提箱成功

| 对象 | 字段 | 新值 |
|---|---|---|
| 预约 | `status` | `已提箱` |
| 集装箱 | `status` | `已装车待出闸` |
| 集装箱 | `appointment_status` | `已提箱` |
| 任务 | `task_type` | `堆场提箱` |
| 任务 | `status` | `completed` |

### 11.4 出闸成功

| 对象 | 字段 | 新值 |
|---|---|---|
| 预约 | `status` | `已出闸` |
| 集装箱 | `status` | `离港` |
| 集装箱 | `appointment_status` | `已出闸` |
| 集装箱 | `locked_by_appointment_id` | `null` |
| 闸口记录 | `check_result` | `通过` |

### 11.5 闸口拦截

| 对象 | 字段 | 新值 |
|---|---|---|
| 闸口记录 | `check_result` | `拦截` |
| 闸口记录 | `block_reason` | 拦截原因 |
| 异常记录 | `status` | `待处理` |

## 12. 车牌识别服务端设计

车牌识别封装文件：

```text
Management/Container/license_plate_recognizer.py
```

默认识别项目目录：

```text
detect/YOLOv5-LPRNet-Licence-Recognition-master/YOLOv5-LPRNet-Licence-Recognition-master
```

默认权重：

```text
weights/yolov5_best.pt
weights/lprnet_best.pth
```

可选环境变量：

| 环境变量 | 说明 |
|---|---|
| `CTMS_LPR_PROJECT_DIR` | 指定 YOLOv5-LPRNet 项目目录 |
| `CTMS_YOLOV5_PLATE_WEIGHTS` | 指定 YOLOv5 检测权重 |
| `CTMS_LPRNET_WEIGHTS` | 指定 LPRNet 识别权重 |
| `CTMS_PLATE_DEVICE` | 指定运行设备，如 `cpu`、`cuda:0` |
| `CTMS_PLATE_IMG_SIZE` | 指定检测输入尺寸，默认 `640` |
| `CTMS_PLATE_CONF_THRES` | 指定检测置信度阈值，默认 `0.4` |
| `CTMS_PLATE_IOU_THRES` | 指定 NMS IoU 阈值，默认 `0.5` |

图片读取说明：

- Windows 中文路径下不使用 `cv2.imread()`。
- 使用 `np.fromfile()` + `cv2.imdecode()` 读取图片。
- 可避免 `D:\管理信息系统课程设计\...` 这类中文路径读取失败。

## 13. 调试建议

### 13.1 自动识别失败

优先检查：

```text
1. 图片是否成功上传到 instance/gate_vision。
2. 图片是否包含清晰车牌。
3. 当前 Python 环境是否安装 torch、opencv-python、numpy、PyYAML。
4. yolov5_best.pt 是否存在。
5. lprnet_best.pth 是否存在。
6. 识别出的车牌是否与预约单车牌一致。
```

### 13.2 找不到预约

检查：

```text
1. 是否已经创建预约。
2. 预约状态是否属于有效状态：待确认、已确认、已进闸、已提箱。
3. 预约车牌是否与识别车牌完全一致。
4. 中文省份简称、字母大小写是否被规范化。
```

### 13.3 不能进闸

常见原因：

```text
1. 预约状态不是已确认。
2. 车牌与预约不一致。
3. 箱号与预约不一致。
4. 海关未放行。
5. 不在预约时间窗及 30 分钟宽限范围内。
```

### 13.4 不能出闸

常见原因：

```text
1. 预约状态不是已提箱。
2. 还没有执行堆场提箱。
3. 车牌与预约不一致。
4. 箱号与预约不一致。
5. 海关放行状态异常。
```

## 14. 接口总表

| 序号 | 接口 | 方法 | 请求类型 | 说明 |
|---|---|---|---|---|
| 1 | `/api/import/overview` | GET | - | 获取总览、预约、闸口、异常 |
| 2 | `/api/import/containers/pickup-ready` | GET | - | 获取可预约/可处理集装箱 |
| 3 | `/api/import/customs/releases` | GET | - | 查询放行记录 |
| 4 | `/api/import/customs/release` | POST | JSON | 更新放行状态 |
| 5 | `/api/import/appointments` | GET | - | 查询全部预约 |
| 6 | `/api/import/appointments` | POST | JSON | 创建提箱预约 |
| 7 | `/api/import/appointments/{id}/cancel` | PUT | JSON 可为空 | 取消预约 |
| 8 | `/api/import/appointments/{id}/pickup` | POST | JSON 可为空 | 完成堆场提箱 |
| 9 | `/api/import/gate/in` | POST | JSON | 人工进闸 |
| 10 | `/api/import/gate/out` | POST | JSON | 人工出闸 |
| 11 | `/api/import/gate/vision` | POST | multipart/form-data | 视觉识别自动闸口 |
| 12 | `/api/import/exceptions` | GET | - | 查询异常 |
| 13 | `/api/import/exceptions` | POST | JSON | 登记异常 |
| 14 | `/api/import/exceptions/{id}/resolve` | PUT | JSON | 关闭异常 |

