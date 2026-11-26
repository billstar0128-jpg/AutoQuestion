# 模型 API 配置指南

AutoQuestion 在识题时会把网页中提取的题目文字或屏幕截图发给你选定的 AI 服务商。应用源码和安装包免费，实际调用模型时由服务商按用量计费。

## 1. 选择模型

Android 0.6.1 读取屏幕截图，需要能看图的模型。Windows 0.6.0 的截图模式和自动截图回退也需要图片能力。Windows 只读受支持网页的 DOM（页面中的文字和结构）时可以使用纯文本模型。

| 服务商 | API Base URL | Model ID | 图片输入 | 官方资料 |
| --- | --- | --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-flash` | 支持 | [图片输入](https://api-docs.deepseek.com/guides/vision/) · [模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) |
| OpenAI | `https://api.openai.com/v1` | `gpt-6-luna` | 支持 | [模型与接口](https://developers.openai.com/api/docs/models/gpt-6-luna) · [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) |

上表是首次配置的两个选项。`deepseek-v4-pro` 只支持文本。已发布的应用界面可能仍显示 `gpt-4.1-mini`。OpenAI 已将它标为弃用，计划在 2027 年 1 月 14 日停用。新配置请手动填写 `gpt-6-luna`，并确认自己的 API 账户有权限使用。 [OpenAI 弃用公告](https://developers.openai.com/api/docs/deprecations)

### Kimi 与智谱 GLM 的配置示例

已有 Kimi 或智谱 API 账户，也可按下表填入支持图片输入的模型。表中的地址与模型来自服务商文档，均支持 OpenAI 兼容的 Chat Completions 图片请求。具体账户可用性、识题效果和等待时间需实际验证。

| 服务商 | API Base URL | 支持图片的 Model ID | 官方资料 |
| --- | --- | --- | --- |
| Kimi / Moonshot（中国平台） | `https://api.moonshot.cn/v1` | `kimi-k3.1-pro` | [图片输入与型号](https://platform.kimi.com/docs/guide/use-kimi-vision-model) · [模型单价](https://platform.kimi.com/) |
| Kimi / Moonshot（国际平台） | `https://api.moonshot.ai/v1` | `kimi-k3.1-pro` | [图片输入与型号](https://platform.kimi.ai/docs/guide/use-kimi-vision-model) · [模型单价](https://platform.kimi.ai/) |
| 智谱 GLM（模型标准 API） | `https://open.bigmodel.cn/api/paas/v4/` | `glm-5.3-flash` | [图片输入与型号](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash) · [模型单价](https://docs.bigmodel.cn/cn/guide/start/pricing) |

Kimi 请在创建 Key 的平台核对对应地址和计费币种。早期的 `kimi-k2.6` 属于 K2 系列，官方已停止向新注册用户开放，计划于 2026 年 12 月底下线。智谱上表使用模型标准 API 的 Key 和按量计费地址，个人及团队编程套餐有各自的 Key 和专属地址。 [Kimi 模型计费说明](https://platform.kimi.com/docs/pricing/chat) · [智谱 API Key 说明](https://docs.bigmodel.cn/cn/guide/start/quick-start)

### 调用怎么收费

截至 2026 年 11 月 26 日，官方单价如下。Token 是平台计量模型输入及输出的单位。图片也会计入输入用量，图片大小会影响计量。缓存命中指服务商复用了先前请求中的一部分输入，由服务商判断和计费。

| 模型 | 每百万输入 Token | 每百万缓存命中输入 Token | 每百万输出 Token |
| --- | --- | --- | --- |
| DeepSeek `deepseek-flash` | 空闲 ¥1 / 高峰 ¥2 | 空闲 ¥0.02 / 高峰 ¥0.04 | 空闲 ¥4 / 高峰 ¥8 |
| OpenAI `gpt-6-luna`（标准档） | US$0.10 | US$0.01 | US$0.50 |
| Kimi `kimi-k3.1-pro`（中国平台） | ¥13 | ¥1.30 | ¥68 |
| Kimi `kimi-k3.1-pro`（国际平台） | US$2.00 | US$0.20 | US$10.00 |
| 智谱 `glm-5.3-flash`（模型标准 API） | ¥0.80 | ¥0.23 | ¥2.80 |

DeepSeek 的高峰为北京时间周一至周五 09:00–12:00、14:00–18:00，中国法定节假日按空闲时段计费。OpenAI 的长输入、缓存写入和其他处理档位有单独费率。充值前请核对官方价格，使用后在服务商控制台查看实际消费。识题准确率、等待时间和每百题费用留待实测。 [DeepSeek 计费](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) · [OpenAI 计费](https://developers.openai.com/api/docs/pricing) · [OpenAI 图片计量说明](https://developers.openai.com/api/docs/guides/images-vision)

## 2. 创建 API Key 并检查计费

**API Key** 是允许 AutoQuestion 调用模型并使用你账户额度的一串密钥。先在服务商的官方 API 平台登录并创建 Key，复制后粘贴到本机应用的 `API Key` 一栏。将它像密码一样保管。若误发到群聊、截图或 GitHub，请在平台撤销旧 Key，再创建新的并更新应用配置。

- **DeepSeek**。从官方入门页点“API key”进入开放平台，登录后打开「API keys」，创建并复制密钥。到同一平台查看余额，有调用需要时按页面提示充值。请求费用从赠送余额或充值余额扣除。 [DeepSeek 入门](https://api-docs.deepseek.com/zh-cn/) · [DeepSeek 扣费规则](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
- **OpenAI**。在支持的地区登录 API 平台，选择你有权限的项目，在「API keys」创建并复制 Key。到该项目所属组织的「Billing」检查可用额度，需要开通预付费时添加付款方式并购买额度。确认是否开启自动充值。ChatGPT 订阅与 API 计费分别管理。 [创建 Key](https://developers.openai.com/api/docs/quickstart) · [API 预付费](https://help.openai.com/en/articles/8264644-setting-up-and-managing-prepaid-api-billing) · [支持地区](https://help.openai.com/en/articles/7947663-chatgpt-and-openai-api-supported-countries-and-territories) · [订阅与 API 计费](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform)
- **Kimi**。登录自己的 Kimi API 开放平台，在「API Keys」创建并复制 Key，在同一平台查看余额和充值规则。模型 API 使用开放平台额度。 [中国平台入门](https://platform.kimi.com/docs/get-api-key) · [中国平台充值](https://platform.kimi.com/docs/pricing/limits) · [国际平台入门](https://platform.kimi.ai/docs/get-your-api-key) · [国际平台充值](https://platform.kimi.ai/docs/pricing/limits)
- **智谱 GLM**。登录智谱开放平台，在个人中心打开「API Keys」，创建模型标准 API 的 Key。在控制台查看用量及账户余额，按使用需要充值。 [智谱入门](https://docs.bigmodel.cn/cn/guide/start/quick-start)

## 3. 填写 AutoQuestion

- **API Base URL** 是提供模型接口的根地址。按上表复制对应地址，保留其中的 `/v1` 等路径，应用会自动拼接 `/chat/completions`。请填写 API 地址，避免粘贴聊天网页地址或完整请求地址。
- **Model ID** 是服务商用来区分模型的短名称，例如 `deepseek-flash`。按官方文档或账户控制台逐字填写。
- 使用自定义服务时，请同时确认该服务支持 OpenAI 兼容的 Chat Completions 和账户可用的 Model ID。用截图时，还须支持在对话请求里通过 `image_url` 传入嵌入式图片。只填写你信任的服务地址，Android 只接受 HTTPS 地址。

### Windows

1. 在本机 AutoQuestion 窗口打开「模型与配置」。在「AI 服务商」选择相应服务商，填入 `API Base URL`、`Model ID` 和 `API Key`。
2. 确认账户中的模型支持图片后，勾选「我确认这个模型支持图片输入」。「输入方式」可选「AUTO · 推荐」。如果只想发送网页提取的文本，可以选择「DOM · 网页结构」并按文档配置浏览器。 [DOM 配置](BROWSER_DOM_SETUP.md)
3. 在「保存方式」选择 Windows 安全凭据保存或仅本次使用，点「保存配置」。回到「工作台」点「启动答题」，打开完整的练习题后按 `F8`。运行时要先按 `Esc` 停止，才可修改模型设置。

### Android

1. 打开本机 AutoQuestion，找到「配置图片模型」。可用 DeepSeek 或 OpenAI 按钮预填示例，也可直接手动填写其他服务商的 `Base URL`。将 `Model` 改为上表中对应的图片模型，再填 `API Key`。
2. 点「保存配置」，再点「开启悬浮识题」，按提示允许悬浮窗。在练习页面轻点 `AQ` 开始识题。 [Android 操作与权限](ANDROID.md)

## 模型配置常见问题

| 遇到的情况 | 先检查什么 |
| --- | --- |
| 保存成功但首次识题失败 | 保存只检查本地配置格式及凭据保存情况。确认服务商控制台中的 Key、模型权限和余额，检查网络是否可以访问所填 API 地址。 |
| 认证失败、HTTP 401 / 403 | 确认 Key 来自同一服务商和正确的项目或账户，尚未被撤销，并有调用所填模型的权限。 |
| HTTP 429、限流或额度不足 | 查看服务商控制台的余额、用量和调用频率限制。余额不足时在服务商平台处理，限流时稍后重试。 |
| 找不到模型或服务商拒绝请求 | 核对 Base URL、Model ID 和账户权限。若只在截图时失败，再核对该模型是否能通过 Chat Completions 接收图片。 |
| 更换服务商后仍用旧 Key | 填写新地址所对应的 Key 后重新保存。Android 同一服务地址更新模型时可留空保留之前保存的 Key。 |

更多安装、识题及更新问题见 [常见问题](FAQ.md)。模型请求涉及的数据和本机保存方式见 [隐私说明](../PRIVACY.md)。
