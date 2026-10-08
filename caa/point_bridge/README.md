# Point-only CAA source contribution

本目录只包含 `catia_caa_demo_create_point` 的原生源码及必需加载/通信资源。
`CatiaPyBridgeCore.cpp` 只分发该方法，其他 CAA 业务源码没有纳入。

| 目录 | 内容 |
| --- | --- |
| `caa_workspace/CatiaPyBridgeFramework/` | 点算法、坐标参数、RunOnce 通信、命令加载源码和资源 |
| `caa_workspace/CatiaPyBridgeRuntime/code/dictionary/` | 源码注册字典 |
| `scripts/` | 本机配置、从源码构建、runtime 同步、CATIA 启动 |
| `validation/native-evidence.json` | 原生验收摘要及源码哈希，省略原机器路径 |

遵循维护者要求，Git 和源码包不提交 DLL、CATPart、官方 SDK 或本机配置。
DLL、productIC、runtime manifest 和 CATEnv 由本机构建生成并忽略。
Python 协议位于仓库 `catia_mcp/caa/`；样件创建步骤位于 `examples/caa_point/`。
点接口及必需桥接源码按 [MIT](LICENSE) 公开，其他私有内容不在授权范围内。

完整构建、配置、调用及 Draft 限制见 [接入说明](../../docs/caa-point.md)。
[生产规范](../../docs/production-development-guide.md)描述生产目标，当前 Draft 尚未全部达到。
原生实现沿用已有验收；本仓库新接入路径和调整后的构建脚本仍需 B30 实机验证。
