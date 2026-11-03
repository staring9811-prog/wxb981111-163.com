# TDD 验收结果 · 品类机会判定台

- contract_sha256: sha256:c0655e0c1643cdd614bb16d7713d4cdcc62aba4082ff59426134f8bad1f43ddf
- run_started_at: 2026-11-03T09:47:15Z

| TDD ID | 状态 | 实际验证动作 | 证据 |
| :--- | :--- | :--- | :--- |
| `SMOKE-01` | pending | 在干净副本运行启动.command：首次自动建虚拟环境并安装依赖，打印局域网地址；用该地址未登录跳登录页、初始密码登录进入工作台（本机侧已通过） | 缺：局域网另一台设备访问与 Windows 启动.bat，需 wen 在本人电脑实测 |
| `SMOKE-02` | pass | 空库经页面接口上传 2025-03 至 10 原始导出 8 个月→核对并入→打标→确认队列 11,990 组清空→扫描 0.09 秒→做决策卡 10.5 秒十节齐全；历史不足时重算给出原因；在第二轮全量历史库上经页面重算 30 秒完成 | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113; smoke2 脚本 exit_code=0 |
| `FLOW-01` | pass | 运行全量 pytest，对应用例：test_accounts::test_create_validation_and_reset、test_accounts::test_flow01_create_login_disable_last_operator | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-02` | pass | 运行全量 pytest，对应用例：test_settings::test_flow02_keys_mask_test_replace_delete、test_settings::test_flow02_llm_provider_switch、test_settings::test_real_clients_error_mapping | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-03` | pass | 运行全量 pytest，对应用例：test_settings::test_flow03_estimate_cancel_confirm_ledger | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-04` | pass | 运行全量 pytest，对应用例：test_data::test_abandon_paused_pull_keeps_raw_not_merged、test_data::test_abandon_running_pull、test_data::test_pull_fields_and_resume | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-05` | pass | 运行全量 pytest，对应用例：test_data::test_coverage_rule_frame_absolute_attr_drop、test_data::test_misdated_real_file、test_data::test_real_raw_month_not_misdated、test_data::test_unmerged_batch_with_old_coverage_rule_rechecked_on_start、test_data::test_upload_missing_column、test_data::test_verify_suspect_anomaly_normal | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-06` | pass | 运行全量 pytest，对应用例：test_tagging::test_rule_tags_and_queue_without_llm、test_tagging::test_vision_with_llm | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-07` | pass | 运行全量 pytest，对应用例：test_tagging::test_group_confirm_single_override_exclude | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-08` | pass | 运行全量 pytest，对应用例：test_tagging::test_other_channel_image_sources_and_noimage_placeholder、test_tagging::test_other_channel_same_rules_and_filter | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-09` | pass | 运行全量 pytest，对应用例：test_models::test_rescore_blocked_when_newer_batch_unmerged、test_models::test_rescore_matches_v9_backtest、test_models::test_rescore_needs_tags_confirmed | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-10` | pass | 运行全量 pytest，对应用例：test_models::test_invalid_run_flag、test_models::test_rescore_matches_v9_backtest、test_models::test_validity_rule | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-11` | pass | 运行全量 pytest，对应用例：test_scan::test_scan_matches_v2_csv_and_filters | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-12` | pass | 运行全量 pytest，对应用例：test_cards::test_flow12_ten_sections_numbers_sources_readonly | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-13` | pass | 运行全量 pytest，对应用例：test_cards::test_flow13_sku_drawer_and_bigdata_layer | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-14` | pass | 运行全量 pytest，对应用例：test_cards::test_flow14_ai_draft_after_cost_confirm | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-15` | pass | 运行全量 pytest，对应用例：test_reviews::test_flow15_pull_merge_classify_and_override、test_reviews::test_sellersprite_review_without_id_and_ms_date | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-16` | pass | 运行全量 pytest，对应用例：test_tools::test_flow16_four_steps_pause_resume_and_same_export_as_original、test_tools::test_flow16_monthly_cap_stops_and_keeps_data、test_tools::test_flow16_project_budget_either_first、test_tools::test_flow16_vp_rules_unchanged_from_original | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-17` | pass | 运行全量 pytest，对应用例：test_tools::test_flow17_ai_quote_via_server_and_costgate、test_tools::test_flow17_profit_numbers_match_original_tool | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-18` | pass | 运行全量 pytest，对应用例：test_tools::test_flow18_card_prefill_and_writeback、test_tools::test_flow18_writeback_rejects_missing_inputs | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-19` | pass | 运行全量 pytest，对应用例：test_approval::test_flow19_submit_approve_reject_return | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-20` | pass | 运行全量 pytest，对应用例：test_approval::test_flow20_strategy_versions_and_verified_approval | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-21` | pass | 运行全量 pytest，对应用例：test_ledger::test_flow21_reconcile_amazon_and_unlinked | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-22` | pass | 运行全量 pytest，对应用例：test_ledger::test_flow22_per_channel_success_lines | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-23` | pass | 运行全量 pytest，对应用例：test_category::test_flow23_preview_then_save_new_version、test_category::test_flow23_validation、test_category::test_flow23_view_defaults_only_bathroom_vanity | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-24` | pass | 运行全量 pytest，对应用例：test_channels::test_tracker_ingest_dedup_by_review_id、test_channels::test_upload_wen_vp_export | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-25` | pass | 运行全量 pytest，对应用例：test_channels::test_rank_method_and_min_anchors | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `FLOW-26` | pass | 运行全量 pytest，对应用例：test_cards::test_flow26_card_channels_side_by_side、test_scan::test_channel_scan_uses_own_data | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `DESIGN-01` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-01_PAGE-F15-01_登录_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-02` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-02_PAGE-F15-02_工作台_操作者_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-03` | pending | 未复核：账号管理页按 wen 2026-11-03 要求暂缓 | 暂缓 |
| `DESIGN-04` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-04_PAGE-F16-01_密钥_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-05` | pass | 独立视觉验收官（第 5 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-05_PAGE-F16-02_预算_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-06` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-06_PAGE-F17-01_Amazon月度数据_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-07` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-07_PAGE-F28-01_其他渠道_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-08` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-08_PAGE-F18-01_打标确认_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-09` | pass | 独立视觉验收官（第 5 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-09_PAGE-F19-01_模型与回测_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-10` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-10_PAGE-F20-01_机会扫描_Amazon_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-11` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-11_PAGE-F21-01_决策卡列表_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-12` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-12_PAGE-F21-02_决策卡_草稿_操作者_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-13` | pass | 独立视觉验收官（第 5 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-13_PAGE-F23-01_评论VP追踪_有采集结果_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-14` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-14_PAGE-F24-01_利润测算_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-15` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-15_PAGE-F25-01_审批_审批者_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-16` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-16_PAGE-F25-02_策略库_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-17` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-17_PAGE-F26-01_预测台账_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `DESIGN-18` | pass | 独立视觉验收官（第 4 轮）用 Read 实际查看真实运行成品截图，逐项核对契约六类锚点并与原型比对，弹窗/页签/抽屉另行只读补拍 | actual=tests/visual/DESIGN-18_PAGE-F27-01_品类配置_视口.png; reviewer=independent-visual; review=pass; blocking=0 |
| `RULE-01` | pass | 运行全量 pytest，对应用例：test_category::test_category_operator_only、test_home::test_rule01_all_routes | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-02` | pass | 运行全量 pytest，对应用例：test_settings::test_rule02_keys_never_leak | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-03` | pass | 运行全量 pytest，对应用例：test_cards::test_rule03_snapshot_after_approval | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-04` | pass | 运行全量 pytest，对应用例：test_data::test_cap_resume_no_duplicate_calls_single_task | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-05` | pass | 运行全量 pytest，对应用例：test_scan::test_frames_scanned_separately | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-06` | pass | 运行全量 pytest，对应用例：test_scan::test_scan_open_within_10s；实测：机会扫描打开 0.09–0.20 秒（≤10 秒），决策卡生成 1.6–10.5 秒（≤30 秒） | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-07` | pass | 运行全量 pytest，对应用例：test_data::test_history_replay | command=cd app && python -m pytest -q（2026-11-03 全量，junit 存档）; exit_code=0; failed=0; passed=113 |
| `RULE-08` | pending | 未执行：需 wen 在设置页填入真实密钥后对四类服务点测试并拉一个真实分片 | 卖家精灵评论接口格式已用 MCP 实测并据此修正客户端；HTTP 接口地址与鉴权待 wen 提供文档 |
