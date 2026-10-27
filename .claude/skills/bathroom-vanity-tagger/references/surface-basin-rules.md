# 台面与台盆：业务分类及推导规则（2026-10-24）

用户明确要求：台面、台盆分两列；SMC/树脂/Cultured Marble同材互推的观察；engineered marble top与engineered stone统一；Cultured Marble独立；石英石/岗石台面推陶瓷盆；亚克力盆并树脂盆。用户已于2026-10-24确认按本版本修正打标。以下是项目业务分类，非化学或天然石材鉴定。

## 已确定的结构与来源原则

- D8台面及盆材质已改为D8台面材质、D8台盆材质，各为自动文本，无下拉；原文、主业务类别、细分材质和直接/推导来源保留JSON。v2为正式拆列版本，v1原件留作溯源。
- 先识别部件，再归类，再有条件推导。明确的子体原文及参数优先于组合规律；父体线索及推导仍保留来源范围，不升级成已采集的子体事实。
- integrated/一体化等营销词可能指已装配台下盆，不能单凭该词证明台面与盆浇铸同体；优先one-piece、molded integral bowl、同材构造图/规格等明确证据。

## 用户提出的业务映射（保留细分类，不作为化学材料等同）

1. 陶瓷相关ceramic/porcelain/vitreous china归陶瓷主组；陶瓷盆单列。
2. 树脂、SMC、acrylic/亚克力可在主业务组归树脂类；盆统一树脂盆，细分保留SMC/亚克力/未细分树脂。SMC不是纯树脂同义词，不能从泛称resin反推SMC。
3. engineered marble top与engineered stone按用户业务归岗石/工程石主组；原英文细分照存。明确quartz/engineered quartz优先归石英石；不能见engineered就吞并石英石。
4. cultured marble独立为Cultured Marble（浇铸人造大理石），不与engineered marble合为同一旧“人造大理石”标签；用户拼写clutred marble规范到cultured marble，但保存原词。
5. synthetic marble、cast marble、artificial marble归岗石业务组，原词细分保留；不能当cultured marble。
6. 用户最新明确：大理石材料分支中有Carrara或Calacatta统一写“卡拉拉大理石”；其余未明确细分的marble写“岗石”。engineered marble在此分支，engineered stone仍归岗石。若明确写Quartz/Sintered Stone/树脂/Cultured Marble，则这些明确材质优先，Carrara/Calacatta只作纹理名称。无任何材质证据不默认岗石。所有该业务归类在JSON保存原词、规则ID与business_mapping，不代表天然石材已验证。
7. 玻璃盆有当前样本和厂家实物类型支持，应保留玻璃盆例外。不能把所有盆压为陶瓷/树脂；其他明确盆材也保留原词并复核。

## 已启用的有条件推导

- 已确认同材浇铸的一体盆台，且已知SMC/树脂/亚克力/Cultured Marble任一部件材质：可补另一部件同材；标同材结构推导、来源部件/原文/规则ID，不能当直接返回字段。
- 仅写resin sink、SMC sink、cultured marble top而无同材一体证据：不无条件互推。Cultured Marble厂家也提供另装台下陶瓷盆，不能写成必然同材。
- 石英石/岗石/工程石台面且盆明确随套装提供、盆材未知且无反证：可将陶瓷盆作为用户经验业务推导候选。该规则不是所有市场商品的硬事实；当前项目按用户经验启用，JSON记business_assumption而非direct_evidence；与文本支持值分开分析。
- 岩板、大理石、木质、玻璃台面与盆的搭配不自动互推；优先明确部件原文。
- 没有配盆/台面不包含/客户自配的商品不适用配套推导。明确的玻璃盆、树脂盆、金属盆等反证优先。

## v1问题与v2修复范围

原引擎以临近关键词作部件匹配，top锚点未覆盖单独Top，使下列台面词错误落到盆：

- B0GGZQ5V35：Carrara White Sintered Stone Top and Ceramic Basin。岩板是台面，陶瓷是盆。
- B0DFLRKRVL：Carrara Quartz Top and Undermount Porcelain Sink。石英石是台面，陶瓷是盆。
- B0DJVK9ZT5：Ceramic Basin and Marble Top。大理石是台面，陶瓷是盆。
- B0H3KKRWY3：CERAMIC & STAINLESS STEEL段落含ceramic sink；不锈钢须核验部件，不能凭章节材料列表当盆材。
- 反例B09PT97JLR明确Clear Boat Glass Sink，玻璃盆不是应当吞并的程序误配。

v1旧合并D8仅供溯源。v2已加入单独Top锚点及局部材料部件绑定，回原文区分engineered/cultured并拆列；存在冲突、父体候选、信息不足的字段仍按JSON状态限制使用。玻璃盆等明确例外保留。

## 市场证据（2026-10-24查阅，厂家/材料商原始资料）

- IDI Composites SMC & BMC：https://www.idicomposites.com/product/smc-bmc/ 。SMC含树脂、填料及纤维增强，支持树脂复合大组，不支持各产品与纯树脂材性等同。
- Corian材料技术公告：https://www.corian.com/sites/corian.com/IMG/pdf/k-30025-corian-solid-surface-material-composition-bulletin_sec.pdf 。亚克力树脂与矿物组成实例，支持保留亚克力细分。
- Avanity台面：https://www.avanity.com/collections/vanity-tops 。VersaStone为纯亚克力台面并有一体盆产品；对应原厂规格https://images.thdstatic.com/catalog/pdfImages/61/61c47f15-d25a-4439-b1a8-bf25290f9a78.pdf 。
- MarCraft Cultured Marble：https://marcraftusa.com/products/cultured-marble/ 。同类台面提供一体盆及Undermount Porcelain选项，直接说明不能把Cultured Marble台面一律推同材盆。
- Columbia Cultured Marble：https://columbiamarble.com/bathrooms/ 。提供同体模压盆，也允许客户自己的盆或台下盆。
- MSI Engineered Marble产品：https://www.msisurfaces.com/vanity-tops/calacatta-lumas/ 。明确Material Type Engineered Marble；用于保留原始名称，不将业务合并宣称为技术同义。
- KOHLER石英石台面配套资料：https://resources.kohler.com/webassets/kpna/brochures/QuartzTop_SellSheet.pdf 。可搭配指定盆型号，支持配套验证，不证明所有石英石台面都附陶瓷盆。
- KOHLER盆材料说明：https://assist.kohler.com/en/sinks/Sink-Material-Information 。Vitreous China属于陶瓷材料。
- VIGO玻璃盆：https://vigoindustries.com/collections/tempered-glass-sinks 。明确钢化玻璃浴室盆，不能强归陶瓷/树脂。

## 2026-10-27 用户追加的台面规则（v6）

1. **solid wood 不是台面**。单独出现的 solid wood / solid oak 指柜体或框架（走D7）。只有 wood / wooden / oak / walnut / bamboo / teak / MDF / plywood 直接接 top / countertop / tabletop 时才是木板台面，标签“木板”（原台面“实木”标签并入“木板”）。
2. **仿大理石纹 = 木板**：marble texture / look / pattern / grain / effect top，且子体自己的文本（标题、SKU、子体详情、子体五点、导出参数）里没有 stone / quartz / sintered / granite / cultured / engineered marble / marble top / Carrara / Calacatta 这些真石材词 → 木板，ruleID M-FAUX-MARBLE-WOOD，basisType business_mapping，rawMaterial 保留 marble texture。有石材词时不归木板，打标说明提示。
3. **未细分 stone countertop = 岗石**：stone 前面不是 sintered / engineered / cultured，后面直接接 top / countertop → 岗石，ruleID M-STONE-UNSPECIFIED。
4. **一体盆台同材**（用户确认 R1/R2/R6）：台面未知、盆材已知，且文本有 `<材质> sink top`、`integrated <材质> sink`、`sink and top in one`、`one-piece sink/top`，或 D4 已判一体盆 → 台面 = 盆材（陶瓷盆→陶瓷、玻璃盆→玻璃、树脂盆→树脂、岗石盆→岗石）。ruleID M-SINK-TOP-ONEPIECE，basisType business_inference；来源为父体时按父体补充口径。
5. **不含台面**：补 no top、vanity base only、cabinet only。

台面标签集现为：卡拉拉大理石 / 岗石 / 石英石 / 岩板 / 陶瓷 / 树脂 / Cultured Marble / 花岗岩 / 玻璃 / 不锈钢 / 木板 / 不适用（不含台面）/ 信息不足。
