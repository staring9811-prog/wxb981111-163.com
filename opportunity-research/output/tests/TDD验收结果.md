# TDD 验收结果 · 品类机会判定台

- contract_sha256: sha256:d7562c22b7d9aa871b025faaf40a3337335f6be6ecee0718e9a336e36e6573b3
- run_started_at: 2026-11-05T04:00:00Z

| TDD ID | 状态 | 实际验证动作 | 证据 |
| :--- | :--- | :--- | :--- |
| `SMOKE-01` | pending | 在干净副本运行启动.command：首次自动建虚拟环境并安装依赖，打印局域网地址；用该地址未登录跳登录页、初始密码登录进入工作台（本机侧已通过） | 缺：局域网另一台设备访问与 Windows 启动.bat，需 wen 在本人电脑实测 |
| `SMOKE-02` | pass | 空库经页面接口上传 2025-03 至 10 原始导出 8 个月→核对并入→打标→确认队列 11,990 组清空→扫描 0.09 秒→做决策卡 10.5 秒十节齐全；历史不足时重算给出原因；在第二轮全量历史库上经页面重算 30 秒完成 | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113; smoke2 脚本 exit_code=0 |
| `FLOW-01` | pass | 运行全量 pytest，对应用例：test_accounts::test_create_validation_and_reset、test_accounts::test_flow01_create_login_disable_last_operator | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-02` | pass | 运行全量 pytest，对应用例：test_settings::test_flow02_keys_mask_test_replace_delete、test_settings::test_flow02_llm_provider_switch、test_settings::test_real_clients_error_mapping | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-03` | pass | 运行全量 pytest，对应用例：test_settings::test_flow03_estimate_cancel_confirm_ledger | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-04` | pass | 运行全量 pytest，对应用例：test_data::test_abandon_paused_pull_keeps_raw_not_merged、test_data::test_abandon_running_pull、test_data::test_pull_fields_and_resume | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-05` | pass | 运行全量 pytest，对应用例：test_data::test_coverage_rule_frame_absolute_attr_drop、test_data::test_misdated_real_file、test_data::test_real_raw_month_not_misdated、test_data::test_unmerged_batch_with_old_coverage_rule_rechecked_on_start、test_data::test_upload_missing_column、test_data::test_verify_suspect_anomaly_normal | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-06` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-07` | pass | 运行全量 pytest，对应用例：test_tagging::test_group_confirm_single_override_exclude | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-08` | pass | 运行全量 pytest，对应用例：test_tagging::test_other_channel_image_sources_and_noimage_placeholder、test_tagging::test_other_channel_same_rules_and_filter | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-09` | pending | 本轮重验未通过（环境数据变化，非 revision 9 代码）：../input/data_v2/统一打标/统一打标_分析用.pkl 与子体流量词预估 2026-11-04 重建（并入 2026-10、重估子体月销），用例 test_models::test_rescore_matches_v9_backtest 与第二轮冻结结果文件对不上（b6 系数 0.3160 对第九版报告 +0.317，差 0.00096 > 容差 0.0006）；在 revision 9 之前的提交 693a58d 上同样失败。回归夹具已固定只导 2024-10 至 2026-09，仍差在子体月销重估。需按新表重生成第二轮对照结果（或 wen 确认改用新表为基准）后重验 | command=cd app && python -m pytest -q（2026-11-04 revision 9 全量）中该用例失败；原 2026-11-03 通过记录保留在 git 历史 |
| `FLOW-10` | pending | 本轮重验未通过（环境数据变化，非 revision 9 代码）：../input/data_v2/统一打标/统一打标_分析用.pkl 与子体流量词预估 2026-11-04 重建（并入 2026-10、重估子体月销），用例 test_models::test_rescore_matches_v9_backtest 与第二轮冻结结果文件对不上（同 FLOW-09）；在 revision 9 之前的提交 693a58d 上同样失败。回归夹具已固定只导 2024-10 至 2026-09，仍差在子体月销重估。需按新表重生成第二轮对照结果（或 wen 确认改用新表为基准）后重验 | command=cd app && python -m pytest -q（2026-11-04 revision 9 全量）中该用例失败；原 2026-11-03 通过记录保留在 git 历史 |
| `FLOW-11` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-12` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-13` | pass | 运行全量 pytest，对应用例：test_cards::test_flow13_sku_drawer_and_bigdata_layer | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-14` | pass | 运行全量 pytest，对应用例：test_cards::test_flow14_ai_draft_after_cost_confirm | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-15` | pass | 运行全量 pytest，对应用例：test_reviews::test_flow15_pull_merge_classify_and_override、test_reviews::test_sellersprite_review_without_id_and_ms_date | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-16` | pass | 运行全量 pytest，对应用例：test_tools::test_flow16_four_steps_pause_resume_and_same_export_as_original、test_tools::test_flow16_monthly_cap_stops_and_keeps_data、test_tools::test_flow16_project_budget_either_first、test_tools::test_flow16_vp_rules_unchanged_from_original | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-17` | pass | 运行全量 pytest，对应用例：test_tools::test_flow17_ai_quote_via_server_and_costgate、test_tools::test_flow17_profit_numbers_match_original_tool | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-18` | pass | 运行全量 pytest，对应用例：test_tools::test_flow18_card_prefill_and_writeback、test_tools::test_flow18_writeback_rejects_missing_inputs | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-19` | pass | 运行全量 pytest，对应用例：test_approval::test_flow19_submit_approve_reject_return | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-20` | pass | 运行全量 pytest，对应用例：test_approval::test_flow20_strategy_versions_and_verified_approval | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-21` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-22` | pass | 运行全量 pytest，对应用例：test_ledger::test_flow22_per_channel_success_lines | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-23` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-24` | pass | 运行全量 pytest，对应用例：test_channels::test_tracker_ingest_dedup_by_review_id、test_channels::test_upload_wen_vp_export | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-25` | pass | 运行全量 pytest，对应用例：test_channels::test_rank_method_and_min_anchors | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-26` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-27` | pass | 运行全量 pytest，对应用例：test_backfill::test_flow27_backfill_cancel_confirm_shard_resume、test_backfill::test_flow27_wayfair_backfill_two_step_fake_services、test_tools::test_design13_steps_single_number_and_nothing_to_collect | command=cd app && python -m pytest -q（2026-11-03 revision 8 全量，junit 存档）; exit_code=0; failed=0; passed=143 |
| `FLOW-28` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-29` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-30` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-31` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-32` | pass | 运行全量 pytest，对应用例：test_backfill::test_flow32_backfill_and_discount_params_versioned | command=cd app && python -m pytest -q（2026-11-03 revision 8 全量，junit 存档）; exit_code=0; failed=0; passed=143 |
| `FLOW-33` | pass | 运行全量 pytest，对应用例：test_research::test_flow33_five_bad_copies_rejected、test_research::test_flow33_real_sample_duplicate_rejected（先导入一版 Home Depot，5 组删改副本逐个上传：缺"装"列、"月"写 2026/03、12 行渠道 Amazon、HD pid 重复、3 个 Wayfair pid 对不上；每次 400 + "未导入，当前调研数据不变"、列出列名 / 行号与列 / 渠道值与行数 / 问题类型行数与示例；调研表、导入记录与渠道调研页 JSON 与上传前逐项相同。真实最终样本因 Lowe's pid 5018243355 在两个父体下被同样拒绝） | command=cd app && python -m pytest -q -s tests/test_research.py tests/test_home.py::test_rule01_all_routes（2026-11-04 revision 9，最终表）; exit_code=0; passed=12; failed=0 |
| `FLOW-34` | pass | 运行全量 pytest，对应用例：test_research::test_flow34_summary_abandon_confirm_replace_keep_confirm（真实样本 + 2026-11 行：摘要 Home Depot 1,545 商品 / 218 家族、2026-01 至 10、窗口 206,750、有月度 100%、已落框 99.3%、待确认 36、2026-11 只作参考行数；放弃 → 无版本、记录"已放弃"；只勾 HD 确认 → v1 当前、Wayfair / Lowe's 尚未导入；确认 1 个 HD 形态后重传 → v1 已替换 / v2 当前、该商品不再进队列） | command=cd app && python -m pytest -q -s tests/test_research.py tests/test_home.py::test_rule01_all_routes（2026-11-04 revision 9，最终表）; exit_code=0; passed=12; failed=0 |
| `FLOW-35` | pass | 运行全量 pytest，对应用例：test_research::test_flow35_conflict_needs_tick（库内构造已并入 Wayfair 2026-01 至 10 批次：2026-03 少 6.8%、其余 2%；HD 2026-05 已并入为 0：两渠道标"与已有数据不一致"、逐月表、默认不勾；只勾 Lowe's 时两者不导入，再传勾 Wayfair 才导入） | command=cd app && python -m pytest -q -s tests/test_research.py tests/test_home.py::test_rule01_all_routes（2026-11-04 revision 9，最终表）; exit_code=0; passed=12; failed=0 |
| `FLOW-36` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-37` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-38` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `FLOW-39` | pass | 运行全量 pytest，对应用例：test_research::test_flow39_history_label_and_backtest_mark（HD 回补 + 渠道回测"经回测（打折）"：分级单元另列"回测：经回测（打折）· 分级"并链到 /scan?channel=homedepot&frame=…；Wayfair 无回测内容；两渠道页有"历史观察"横幅与口径说明六项） | command=cd app && python -m pytest -q -s tests/test_research.py tests/test_home.py::test_rule01_all_routes（2026-11-04 revision 9，最终表）; exit_code=0; passed=12; failed=0 |
| `FLOW-40` | pass | 运行全量 pytest，对应用例：test_research::test_flow40_queue_confirm_recompute（Wayfair 分框待确认商品数与小试待人工确认表一致、按窗口销量降序；从渠道调研进入预筛渠道 + "分框未知（渠道调研）"、返回横幅；多尺寸未拆候选 = 选项段 + 不进框；一个指定 30″、一个不进框、一个形态确认为落地式 → 每次重算 ≤ 3 秒，待确认减 3、30″ 框更新、重算时间变化、不进框销量单列、确认值写入 Tag（机会扫描同用）） | command=cd app && python -m pytest -q -s tests/test_research.py tests/test_home.py::test_rule01_all_routes（2026-11-04 revision 9，最终表）; exit_code=0; passed=12; failed=0 |
| `DESIGN-01` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-01_PAGE-F15-01_登录_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-02` | pass | 独立视觉验收官（revision 9 共三轮；协调方代派子 Agent，只看截图、契约锚点与原型，未读实现）用 Read 实际查看真实运行成品截图（Chromium 1440 宽，验收库 = 第二轮数据 + HD 回补与渠道回测 + 调研样本真实导入）：第三轮 v9f_* 为 2026-11-04 最终表（Wayfair 全部逐月），估算 / 低估计与趋势不下结论两类状态最终表里已不存在，引用第二轮通过的 v9_*（同日上午版真实样本），核对 PAGE-F15-02 操作者 / 审批者 / 只读三角色与 v9 本月数据状态"渠道调研"行（窗口、分框待确认、各渠道可读 / 达标或数据不足、历史观察 · 不进机会扫描）及待确认构成含"分框未知（渠道调研）"；第一轮的阻断项均为其他行，本行两轮均无阻断；角色可见性另有 test_home、test_research::test_flow38 行为测试 | actual=tests/visual/v9f_DESIGN-02_PAGE-F15-02_工作台_操作者_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-03` | pending | 未复核：账号管理页按 wen 2026-11-03 要求暂缓 | 暂缓 |
| `DESIGN-04` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-04_PAGE-F16-01_密钥_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-05` | pass | 独立视觉验收官（第 5 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-05_PAGE-F16-02_预算_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-06` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-06_PAGE-F17-01_Amazon月度数据_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-07` | pass | 独立视觉验收官（revision 8 第二轮，DESIGN-12 第三轮）用 Read 实际查看真实运行成品截图，逐项核对原有与 v8 六类锚点并与原型比对；弹窗、页签、抽屉、审批者与已批准状态另行只读补拍（app/tests/visual/accept8/复核*） | actual=tests/visual/v8_DESIGN-07_PAGE-F28-01_其他渠道_历史重建_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-08` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `DESIGN-09` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `DESIGN-10` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `DESIGN-11` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-11_PAGE-F21-01_决策卡列表_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-12` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `DESIGN-13` | pass | 独立视觉验收官（revision 8 第二轮，DESIGN-12 第三轮）用 Read 实际查看真实运行成品截图，逐项核对原有与 v8 六类锚点并与原型比对；弹窗、页签、抽屉、审批者与已批准状态另行只读补拍（app/tests/visual/accept8/复核*） | actual=tests/visual/v8_DESIGN-13_PAGE-F23-01_评论VP追踪_历史回补_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-14` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-14_PAGE-F24-01_利润测算_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-15` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-15_PAGE-F25-01_审批_审批者_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-16` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-16_PAGE-F25-02_策略库_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-17` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `DESIGN-18` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `DESIGN-19` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `DESIGN-20` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `DESIGN-21` | pending | revision 10 通过标准已更新（分框口径 / 白话 / 渠道段等），待重新验证 | — |
| `RULE-01` | pass | 运行全量 pytest，对应用例：test_home::test_rule01_all_routes（遍历全部已注册路由，含 /research、/research/{channel}/frame/{key}、/data/research、/data/research/check、/{id}/confirm、/{id}/abandon、/data/research/log、/tagging/research/confirm：未登录 303 到登录页、只读与审批者修改请求 403"无权限"、各表行数不变） | command=cd app && python -m pytest -q -s tests/test_research.py tests/test_home.py::test_rule01_all_routes（2026-11-04 revision 9，最终表）; exit_code=0; passed=12; failed=0 |
| `RULE-02` | pass | 运行全量 pytest，对应用例：test_settings::test_rule02_keys_never_leak | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-03` | pass | 运行全量 pytest，对应用例：test_cards::test_rule03_snapshot_after_approval | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-04` | pass | 运行全量 pytest，对应用例：test_data::test_cap_resume_no_duplicate_calls_single_task | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-05` | pass | 运行全量 pytest，对应用例：test_scan::test_frames_scanned_separately | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-06` | pass | 运行全量 pytest，对应用例：test_scan::test_scan_open_within_10s；实测：机会扫描打开 0.09–0.20 秒（≤10 秒），决策卡生成 1.6–10.5 秒（≤30 秒） | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-07` | pass | 运行全量 pytest，对应用例：test_data::test_history_replay | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-08` | pending | 未执行：需 wen 在设置页填入真实密钥后对四类服务点测试并拉一个真实分片 | 卖家精灵评论接口格式已用 MCP 实测并据此修正客户端；HTTP 接口地址与鉴权待 wen 提供文档 |
| `RULE-09` | pass | 运行全量 pytest，对应用例：test_backfill::test_rule09_blocked_pauses_channel、test_backfill::test_rule09_polite_rate_limit_retry_and_resume | command=cd app && python -m pytest -q（2026-11-03 revision 8 全量，junit 存档）; exit_code=0; failed=0; passed=143 |
| `RULE-10` | pass | 运行全量 pytest，对应用例：test_research::test_rule10_timing（真实样本 2,741 + 9,439 行，各 3 次取最大：上传到核对摘要 6.4 秒、框列表 0.04 秒、框详情 0.05 秒、确认分框到重算完成 2.8 秒） | command=cd app && python -m pytest -q -s tests/test_research.py tests/test_home.py::test_rule01_all_routes（2026-11-04 revision 9，最终表）; exit_code=0; passed=12; failed=0 |
| `RULE-11` | pass | 运行全量 pytest，对应用例：test_research::test_rule11_import_leaves_analysis_and_permissions（v2 库：导入并确认三渠道后 batch、snapshot、opportunity、unit_score、model_run、card、forecast、channel_model_run、product、tag 各表内容哈希不变、Amazon 机会扫描主区相同；只读与审批者对检查、确认、放弃、分框确认 403"无权限"、调研表不变；三类角色都能打开渠道调研与框详情） | command=cd app && python -m pytest -q -s tests/test_research.py tests/test_home.py::test_rule01_all_routes（2026-11-04 revision 9，最终表）; exit_code=0; passed=12; failed=0 |
| `FLOW-41` | pending | revision 10 新增，待验证 | — |
| `FLOW-42` | pending | revision 10 新增，待验证 | — |
| `FLOW-43` | pending | revision 10 新增，待验证 | — |
| `FLOW-44` | pending | revision 10 新增，待验证 | — |
| `FLOW-45` | pending | revision 10 新增，待验证 | — |
| `FLOW-46` | pending | revision 10 新增，待验证 | — |
| `FLOW-47` | pending | revision 10 新增，待验证 | — |
| `FLOW-48` | pending | revision 10 新增，待验证 | — |
| `DESIGN-22` | pending | revision 10 新增，待验证 | — |
