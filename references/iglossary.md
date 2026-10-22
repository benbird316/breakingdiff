# iglossary — English / Chinese / meaning in this system

The repository was written in Chinese first and rewritten in English. It records the frozen
English–Chinese mapping and each term's meaning in this system. It has no rationale columns:
the body text and this meaning column are the whole contract.

| English | 中文 | Meaning in this system |
| --- | --- | --- |
| account | 口径 | One independent source's statement about the same artifact; the thing being compared. |
| account caliber | 口径粒度 | The level at which an account is stated (synapse / neuron / type); mixing levels fakes a differential. |
| claim | 断言 | One executable, bivalent judgment over parameter points; the unit the engine compares. |
| assertion | 测试断言 | A test-side claim; this word is reserved for tests, not for spec commitments. |
| claim differential | 断言差分 | The four-quadrant comparison of two or more claims over one comparison domain. |
| readout | 读数 | The tool's printed result for one comparison or claim. |
| surface under test | 被测面 | The set of markers or points a check actually covers. |
| cross-verification | 交叉验证 | Agreement between independent sources; same-source agreement is self-consistency, not this. |
| comparison domain | 比较域 | The enumerated parameter points a comparison runs over. |
| parameter point | 参数点 | One point of that domain: a key, path, input, clause, or metric value. |
| four quadrants | 四象限 | common / divergence / dominance / neither. |
| common | 共同域 | Both claims hold at the point. |
| divergence | 分歧域 | P holds and Q does not. |
| dominance | 支配域 | Q holds and P does not; read as the coverage gap. |
| neither | 双否域 | Neither claim holds at the point. |
| outlier | 离群 | With N accounts: exactly one is false and the rest are true. |
| pioneer | 先行者 | With N accounts: exactly one is true and the rest are false. |
| ratchet violation | 棘轮违反 | An older version had it and a newer lost it. |
| outlier attribution | 离群归属 | Which account carries the deviation; a finding, not a verdict. |
| out-of-domain skip | 域外跳过 | Points outside the declared comparison domain. |
| verdict vector | 判定向量 | The per-point truth vector across N accounts. |
| verdict | 判定 | The closed-set shape label of one pair. |
| witness | 见证 | The concrete point or key where a verdict was produced. |
| coverage gate | 覆盖门禁 | Refuses a readout when the change falls outside the surface under test. |
| delivery gate | 交付门 | A checkpoint comparing the agent's claim against an independent source. |
| receipt | 回执 | The deterministic JSON record of a compare run. |
| re-execution | 重执行 | The only verification of a receipt: rerun and compare byte for byte. |
| blind write | 盲写期望 | An expectation written to disk before the readout is produced. |
| provenance | 溯源 | Where a claim's source text comes from. |
| self-attested | 自证 | A declaration with no external anchor. |
| git-object | git 对象锚 | The quote verified verbatim inside a commit blob. |
| external anchor | 外部锚 | An independent source that can adjudicate. |
| attestation tier | 防伪等级 | The self-attested / git-object tier of a claim's provenance. |
| capability declaration table | 能力声明表 | Declares which forgery techniques currently fool the gates. |
| mutation evidence | 变异实证 | Proof that a protected behavior fails when broken, in both directions. |
| red-first | 先红 | The baseline must fail before the fix is written. |
| regression lock | 回归锁 | A red-first check turned into a permanent test. |
| strength layer | 强度层 | How much natural variation a claim allows; an independent failure source. |
| strength calibration | 强度校准 | Measuring the false-red ladder before a gate depends on a claim. |
| band width | 带宽 | The declared tolerance of a bounded claim. |
| band floor | 带底 | The absolute minimum width that absorbs small-count noise. |
| bounded band | 带界 | A claim allowing values inside a declared interval. |
| point value | 点值 | A claim requiring one exact value. |
| hard equality | 硬等 | A claim requiring two sides to be equal. |
| preregistration | 预注册 | Writing the criterion or strength decision down before measuring. |
| exit registry | 出口登记 | The record of which points may legitimately flip, and why. |
| source self-test | 源例自测 | A claim's own quoted example must pass before it is used. |
| reading variant | 候选读法 | Another reasonable formalization of the same source sentence. |
| interpretation | 读法 | A formalization of a source sentence. |
| discriminating power | 区分力 | Whether a test set can tell a claim from its candidate readings. |
| silent failure | 静默失败 | A failure that raises nothing and reports nothing. |
| three-level silence | 三级静默 | Under-reporting / incomplete extraction / surface missing. |
| zero readout | 零读数 | No change reported; zero information, not a pass. |
| gate noise | 门禁噪声 | False reds that make people switch a gate off. |
| dimension discipline | 量纲纪律 | Different dimensions must not share one comparison set. |
| false red | 假红 | True data flagged as bad. |
| false green | 假绿 | Bad data reported as passing. |
| data-extraction layer | 取数层 | Aligning accounts before comparing them. |
| probe layer | 探针层 | Extracting evidence from binaries and release notes. |
| ledger layer | 台账层 | Recording corpus state and provenance. |
| port layer | 移植层 | Keeping the claims while replacing the implementation. |
| worked example | 范本 | A complete, runnable instance of the method. |
| three-part pointer | 三段式指针 | Trigger → which file or section → what it solves. |
| navigation table | 导航表 | The "item → location" map in `AGENTS.md`. |
| live repo | 活仓 | The repository as it is on disk, checked in place. |
| derived site | 派生位 | A version string that is synced from a single source. |
| installable layout | 安装布局 | The copied-out layout built and verified by `dist_layout`. |
| corpus manifest | 语料台账 | Recorded corpus state and measured anchors. |
| asset pin | 资产锚 | A fixed asset name/hash recorded in the manifest. |
| degenerate readout | 退化读数 | The recognizable shape a wrong extraction produces. |
| blind-run brief | 盲测任务书 | A context-free task sheet for cold-start usability testing. |
| spec commitment | 规格承诺 | What the spec promises a consumer can rely on. |
| reconciliation key | 对账键 | The key used to line up two accounts. |
| skip | 跳过 | A test that could not run, reported with a reason. |
