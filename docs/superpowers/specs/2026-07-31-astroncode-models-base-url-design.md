# AstronCode models_base_url 配置设计

## 背景

AstronCode 0.0.13 运行时需要在所选模型 provider 中配置模型目录地址：

```toml
models_base_url = "https://astroncode-api-prod.xf-yun.com/api/v1/astroncode_webserver/config-v1"
```

当前 Harness 仅生成 provider 的鉴权和推理 API 配置，遗漏了该字段。该模型目录地址不区分模型或 provider，MaaS、GPT 和 OpenRouter 模型均使用同一配置。

## 配置契约

- 环境变量名沿用 `ASTRON_MODELS_BASE_URL`。
- 默认值为 `https://astroncode-api-prod.xf-yun.com/api/v1/astroncode_webserver/config-v1`。
- 环境变量为空或仅包含空白时使用默认值。
- Agent 构造时读取并保存配置，保持与现有密钥、provider 和 API 地址相同的运行时快照语义。

## 配置生成

AstronCode 生成的 `config.toml` 必须在当前激活的 provider 表中写入同一个 `models_base_url`：

- `[model_providers.astron-spark]`，适用于 Astron/MaaS 模型。
- `[model_providers.one-iflytek]`，适用于 GPT 模型。
- `[model_providers.openrouter]`，适用于其他 OpenRouter 模型。

该地址不是密钥，无需在宿主机调试配置中脱敏。镜像内容不包含运行时配置，因此不修改 `docker/astroncode/v3/Dockerfile`，也不需要重建镜像。

## 文档与测试

- 在 `.env.example` 中增加 `ASTRON_MODELS_BASE_URL`，说明默认值和覆盖方式。
- 配置测试覆盖默认值、自定义环境变量、构造后环境变化不影响快照，以及三类 provider 均包含正确字段。
- 保留现有 provider 路由、鉴权回退和配置脱敏行为。

## 验收标准

1. 未设置环境变量时，三类 provider 均使用生产环境默认模型目录地址。
2. 设置 `ASTRON_MODELS_BASE_URL` 后，三类 provider 均使用覆盖值。
3. Agent 构造后修改环境变量，不改变该 Agent 后续生成的配置。
4. AstronCode 配置测试和相关回归测试全部通过。
