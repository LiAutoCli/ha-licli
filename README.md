# LiAuto CLI for Home Assistant

Home Assistant custom integration for LiAuto (理想汽车) vehicles via [licli](https://pypi.org/project/liauto).

## Features

- 双模式支持：HTTP API (`licli serve`) 或本地 CLI (`uvx liauto`)
- 车辆状态：电量、续航、里程、空调、车门状态
- GPS 定位：实时位置追踪
- 远程控制：门锁、空调、寻车、唤醒
- 多车辆：自动识别账号下所有车辆

## Installation

### HACS (推荐)

1. HACS → 自定义存储库 → 添加 `https://github.com/licli/licli`
2. 下载并重启 Home Assistant

### 手动安装

```bash
cd config/custom_components
git clone https://github.com/licli/licli.git licli
```

重启 Home Assistant。

## 配置

设置 → 设备与服务 → 添加集成 → **LiAuto CLI**

### 模式 1: HTTP (推荐)

需要运行 `licli serve`：

```bash
export LICLI_CODE=<你的激活码>
licli serve --addr 0.0.0.0:18001 --allow-control
```

配置：
- **Host**: `http://192.168.x.x:18001`
- **Token**: (可选) 如果设置了 `--token`

### 模式 2: 本地 CLI

配置：
- **激活码**: `eyJ...` (你的 LICLI_CODE)

需要确保 `uvx liauto` 或 `licli` 在 HA 容器/宿主机可用。

## 激活码

运行 `licli` 需要有效激活码，绑定到 VIN。

获取方式：联系 licli 发布者 (`license-keygen --vin <VIN>`)。

## 实体

| 实体 | 说明 |
|------|------|
| `sensor.*_电量` | 电池百分比 |
| `sensor.*_纯电续航` | 纯电续航 km |
| `sensor.*_燃油续航` | 燃油续航 km |
| `sensor.*_总里程` | 总里程 km |
| `device_tracker.*_位置` | GPS 位置 |
| `lock.*_门锁` | 车门锁 |
| `climate.*_空调` | 空调控制 |
| `button.*_寻车` | 闪灯鸣笛 |
| `button.*_唤醒` | 唤醒车辆 |
| `binary_sensor.*_在线` | 在线状态 |
| `binary_sensor.*_充电中` | 充电状态 |
| `binary_sensor.*_主驾门` | 车门开关 |

## 调试

```yaml
logger:
  logs:
    custom_components.licli: debug
```
