# AI 规则开发指南：changedetection.io Product Extractors

> **给其他 AI 的独立说明**。目标是：基于用户提供的商品页 URL、完整 HTML/DOM（最好为浏览器渲染后的 HTML）及可选截图，输出可以直接导入本项目 `/product-extractors/` 的 **声明式 JSON**。本指南描述当前实际引擎能力，不允许自创字段、假造选择器或宣称未实际运行的测试已经通过。

## 0. 最短操作流程

1. 阅读本文件。收到真实商品页的 HTML/DOM 和 URL 后，先辨别**商品主售价**与分期价、划线价、会员价、其他商品/配件价格。
2. 在 HTML 中定位能稳定唯一匹配主商品的 CSS / XPath / JSON-LD 字段；库存识别要分清有货、无货和未知。**不要只凭截图猜 CSS 类名。**
3. 输出单个符合下文规范的完整 JSON。域名、路径和字段选择器必须来自真实依据；不确定的字段请说明，不要杜撰。
4. 在 **Product Extractors → Import JSON → Dry run** 粘贴 HTML 或输入可访问的测试 URL，检查真实提取结果、匹配数量、字段来源。无误后点击 **Validate & save**。
5. 把保存的规则绑定到 `Restock & Price Detection` Watch（`Auto` 或 `Selected rule only`）；规则存储在 Git 可追踪的 `extractor-rules/rules/<id>.json`。

**给 AI 的交付要求：** 提供 (a) 完整可解析 JSON，(b) 各选择器来自哪个 DOM 元素、为何不会选中分期/附加商品，(c) 库存判断的原始证据和适用条件，(d) 尚不能确定的字段、可能失效点，(e) Dry Run 预期结果及是否真的测试过。不要输出需要执行 Python/JavaScript 的规则。

## 1. 规则放哪、如何保存？

- `extractor-rules/rules/*.json`：**正式生效**、由 Git 跟踪。规则文件名必须是 `<id>.json`。通过 WebUI 保存会直接修改宿主机挂载的工作树；**不会自动执行 `git commit`**。
- `extractor-rules/examples/*.json`：教学示例，不会自动用于监控。
- `extractor-rules/schema/product-rule.schema.json`：JSON Schema。服务端实际还调用 `product_extraction/registry.py:validate()` 做运行时校验。
- Docker Compose 把 `./extractor-rules` 以可写卷挂载到 `/extractor-rules`。Watch 任务配置及商品历史属于 `datastore/`，不跟随 Git 提交。
- **禁止**在规则、测试 HTML、提交或发送给 AI 的材料里包含 Cookie、登录令牌、Telegram Bot Token、私密账户详情。

## 2. JSON 规范（schema_version=1）

最小规则：

```json
{
  "schema_version": 1,
  "id": "example-store",
  "name": "Example Store",
  "enabled": true,
  "match": {
    "domains": ["example.com"],
    "path_patterns": ["/product/*"]
  },
  "fields": {
    "price": {
      "selectors": [{"type":"css","value":"[data-testid='sale-price']","extract":"text"}]
    },
    "in_stock": {
      "selectors": [{"type":"css","value":"[data-testid='availability']","extract":"text"}],
      "mapping": {"in_stock":["In Stock"], "out_of_stock":["Out of Stock"]}
    }
  }
}
```

**此处的 example.com/选择器仅用于示意，不是实站规则**。可直接执行的离线示例在 `examples/sample-product.html` 和 `examples/sample-product-rule.json`。

### 顶层属性

| 属性 | 必需 | 含义和约束 |
| --- | --- | --- |
| `schema_version` | 是 | 当前只接受整数 `1`。 |
| `id` | 是 | 唯一 ID；2～64 字符，首字符小写英文字母，其余限小写字母、数字、`_`、`-`。对应文件名。 |
| `name` | 是 | 1～100 字符的人类可读名称。 |
| `enabled` | 否 | 布尔值，默认 `true`；禁用规则不参加 Watch 自动匹配，但可以用于 Dry Run。 |
| `match.domains` | 是 | 1～30 个域名，不带 scheme、路径、端口。匹配本域名及其子域名；不支持任意 `*` 域名。 |
| `match.path_patterns` | 否 | 对 URL **路径**进行 glob 匹配，如 `/product/*`；省略时相当于 `*`。不包括查询参数。 |
| `fields` | 是 | 一个或多个受支持的字段，不能包含任意自定义键。 |

字段仅支持：`price`、`currency`、`in_stock`、`stock_quantity`、`title`、`sku`。为了用于价格/库存监控，最终至少要提取到**有效价格或明确库存状态**之一；二者都没有时，Dry Run 会报错。`stock_quantity` 存在时，若 `in_stock` 未识别，引擎可由数量是否大于 0 推断库存状态。

### 字段选择器

推荐写法是 `"selectors": [{"type": ..., "value": ..., "extract": ...}]`，其中可有 **1～8 个有优先级的候选**。只有当前一个候选完全没有匹配数据时才用下一个；**如果第一个匹配到多个不同价格，不会自动退到第二个，而是报歧义错误**。

| `type` | 实际数据来源 | 备注 |
| --- | --- | --- |
| `css` | 使用 BeautifulSoup/lxml 解析输入 HTML，执行 CSS selector | 优先选择稳定的 `data-*`、`itemprop`、产品详情区域属性。 |
| `xpath` | 使用 lxml 在输入 HTML 上执行 XPath | 可用 `//...`、`normalize-space()` 等兼容语法；非 Node 值也能转文本。 |
| `jsonpath` | 只遍历 HTML 中最多 15 个 `script[type="application/ld+json"]` 的 JSON-LD 对象 | 基于 `jsonpath_ng.ext`；**不能查询任意 window.__INITIAL_STATE__ 或网络 API 响应**。 |
| `regex` | 在输入 HTML 文本上执行受约束的正则 | 默认使用第一个捕获组，否则返回完整匹配；表达式最大 160 字符，拒绝部分危险的嵌套量词，匹配数量有限。仅作最后手段。 |

`extract` 可写 `text`（默认）、`html`、`value`、`attr`；`attr` 必须提供 `attribute`，例如 `{"type":"css","value":"meta[itemprop='price']","extract":"attr","attribute":"content"}`。对于 `xpath`，若表达式返回文本/属性值，将直接转成字符串；不要假定所有模式与 CSS 完全等效。

`in_stock` 字段可有：

```json
"mapping": {
  "in_stock": ["Ready for Pickup", "In Stock"],
  "out_of_stock": ["Out of Stock", "Unavailable"],
  "unknown": ["Check Availability"]
}
```

匹配使用不区分大小写的**子串包含**，要防止诸如 `In Stock` 意外命中 `Not In Stock`，应先验证真实 DOM 和最终结果。对于不可靠的混合文本，尽量让选择器仅提取状态节点。`in_stock` 也可接受精确字符串 `true`/`false`。如果同时出现多个不同库存状态，系统报错；没有任何确定状态时返回 `null`，不能强行解释为缺货。

`price` 解析由现有 `money()` 实现：去掉货币符号、识别常见千位分隔符，转换为 Decimal；**多个不同数字值会直接报错**。不要让主价选择器包括分期付款、安装服务、折扣前原价、运费等旁支节点。

`currency` 必须是单个 3 字母币种代码（如 `USD`），不能直接提取 `$` 当作该字段。`title`、`sku`、`currency` 等字段如提取到多个不同字符串，也会报歧义。`stock_quantity` 会从匹配字符串中保留数字并转换为整数，请避免让同一节点同时包含门店编号、电话号码或日期。

**本版不支持：** 规则中的 JavaScript/Python、任意 HTTP 请求、自定义任意字段、通用 DOM `innerText` 执行时等待、CSS 中的浏览器运行态伪类、自定义模板代码或多门店库存模型。复杂页面交互仍用 Watch 现有 Browser Steps 或已有登录的 CloakBrowser 获取最终 DOM。

## 3. 根据真实网页制作规则：给 AI 的检查清单

1. **确认输入页面正确。** 网页如果显示登录页、Cloudflare/Google 验证、地区选择或网络错误，不能从这个页面猜商品规则。请用户用人工操作完成验证，再提供正常渲染的 DOM。
2. **定位主商品区域。** 优先查看 `Product`/`Offer` JSON-LD、带商品 SKU 的容器、固定 `data-testid` 或 `itemprop` 属性。记录至少一个可检验的产品标识。
3. **价格：** 明确截图上的实售价格对应 DOM 的哪一个节点；排除 `monthly`、`was`、`compare-at`、`trade-in`、配件以及“从 $x 起”这类文本。如果价格来自含多金额的大容器，应缩小选择器，而不是用一个宽泛的正则强行取第一个数字。
4. **库存：** 单独找 `in_stock` 或 `stock_quantity`；状态元素必须只与当前商品有关。没有可靠库存证据就先只生成价格规则，**不能因找不到元素认定无货**。
5. **选择器稳定性：** 优先稳定属性、商品详情局部路径，其次语义类名；避免哈希式 CSS 类、随机 ID、绝对 XPath 和易受广告插入影响的 `:nth-child()`。
6. **验证：** 利用 Dry Run 粘贴真实 HTML，检查价格、币种、数量、库存三态、字段匹配数量和实际选中值。再分别拿“有货 / 无货”样例测试库存映射；只有一张有货截图无法推断出无货页面的实际 DOM。
7. **记录限制：** 库存可能取决于账户、Cookie、分店或页面选项。第一版将这些视为不同 Watch/提取上下文，不在规则里假造门店存储模型。

## 4. 可重复的离线示例

配套文件：

- `examples/sample-product.html` —— 完全虚构的商品页面，不包含个人数据。
- `examples/sample-product-rule.json` —— **已针对该 HTML 示例实际验证** 的 JSON 规则。URL 示例：`https://demo.example.com/product/gpu-001`；该域名仅用于演示，不要尝试真实联网抓取。

在 Product Extractors 中导入 `sample-product-rule.json`；展开 **Test with pasted HTML**，粘贴整个 `sample-product.html`，然后 Dry Run。预期返回：`price=1499.99`、`currency=USD`、`in_stock=true`、`stock_quantity=1`、`title=Demo Graphics Card`、`sku=GPU-001`。离线测试不会写入 Watch 历史，也不会触发通知。

在仓库目录的 Python 环境里，也可以运行：

```bash
python -m unittest discover -s tests/product_extraction -v
```

若手头只有截图、没有真实 DOM 或 HTML：**AI 只能描述需要找的元素和提供示意规则，不能宣称给出了可直接用于真实网站的选择器。**

## 5. 常见错误和排查

| 症状 | 可能原因 / 改法 |
| --- | --- |
| `Ambiguous product price` | 选择器匹配多个不同价格；缩小到主售价节点，不要取第一个结果。 |
| `No usable price or stock data extracted` | 网页未渲染完整、抓取到验证页或选择器失效；先检查实时 HTML。 |
| `Ambiguous stock status` | 同时匹配有货/缺货文字；分离状态节点或修正 mapping。 |
| `Selected rule does not match Watch URL` | `domains`/`path_patterns` 不符合该 Watch 的真实 URL。 |
| `Multiple product rules match` | Auto 模式存在重叠；使用 Selected rule only，或调整 URL 匹配规则。 |
| `JSONPath` 没返回内容 | 页面数据不在 `application/ld+json` 中；请用 CSS/XPath 或经 DOM 渲染后的数据。 |
| 新规则已保存但未在编辑 Watch 的下拉框出现 | 重新加载 Watch 编辑页；选择列表不是在页面打开后持续热更新。 |

## 6. 可直接复制给其他 AI 的任务描述

> 请阅读我上传的 `AI_RULE_GUIDE.md`，严格按照 **schema_version=1** 和其中列出的当前引擎能力，基于我提供的商品网页 URL、实际渲染 HTML/DOM 和可选截图，生成 **一份完整的 JSON 商品提取规则**。重点提取准确的主商品价格、币种和有货/无货/未知状态，若 DOM 有可靠证据再提取库存数量、标题和 SKU。不要从截图编造 CSS/XPath，不要误选分期价、优惠说明或配件价格。结果请给出可导入的 JSON、每个字段的 DOM 证据、未确定事项和 Dry Run 验证方法；未经真实测试不得声称通过。

当你有修改建议时，请对照 **当前** `registry.py`、`evaluator.py` 和 JSON Schema；本指南与程序不一致时，以实际运行代码为准，并明确指出差异。
