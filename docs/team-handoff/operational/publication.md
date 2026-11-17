# 打包、传输与恢复

表中选取每份文件的关键读数。JSONL 保留所有已识别事件的源行号和完整 SHA-256。复制路径在同一条记录中列举。

[JSONL](publication.jsonl) · [全部阶段](README.md)

| 代表来源 | SHA-256 前 12 位 | 源行 / 导出事件 | 关键读数 |
|---|---|---:|---|
| `early-course/release-dependencies-install.log` | `56eccea27b86` | 186 / 0 | 仅有指纹与行数 |
| `early-course/release-final-install.log` | `8b59f81d9db4` | 18 / 0 | 仅有指纹与行数 |
| `early-course/release-source-install.log` | `7182cdca79aa` | 11 / 0 | 仅有指纹与行数 |
| `outputs/full_acceptance/publication-download-verification.json` | `19fce8ac8c1b` | 12 / 0 | 仅有指纹与行数 |
| `outputs/full_acceptance/source-archive-verification.json` | `a2b96676d719` | 82 / 1 | {"status":"passed"} |
| `work/acceptance/handoff/data-verification.json` | `0e091d822249` | 97 / 0 | 仅有指纹与行数 |
| `work/acceptance/offline/handoff_crypto_01.json` | `398cf275220d` | 13 / 1 | {"started_at_hong_kong":"2026-11-15T13:32:59.428114+08:00","finished_at_hong_kong":"2026-11-15T13:33:00.407889+08:00","elapsed_seconds":0.979,"returncode":0} |
| `work/acceptance/offline/handoff_crypto_01.log` | `d70aee994da3` | 17 / 2 | {"check":"unittest","tests":11,"seconds":0.315}；{"check":"unittest_ok"} |
| `work/acceptance/offline/handoff_crypto_02.json` | `f131c9f241cb` | 13 / 1 | {"started_at_hong_kong":"2026-11-15T13:37:38.325684+08:00","finished_at_hong_kong":"2026-11-15T13:37:38.861667+08:00","elapsed_seconds":0.536,"returncode":0} |
| `work/acceptance/offline/handoff_crypto_02.log` | `69a673b01c32` | 19 / 2 | {"check":"unittest","tests":13,"seconds":0.35}；{"check":"unittest_ok"} |
| `work/acceptance/offline/handoff_large_decrypt.json` | `8756866acdec` | 20 / 1 | {"started_at_hong_kong":"2026-11-15T14:58:27.065718+08:00","finished_at_hong_kong":"2026-11-15T14:58:36.959326+08:00","elapsed_seconds":9.893,"returncode":0} |
| `work/acceptance/offline/handoff_large_decrypt.log` | `56f6dc95ac14` | 2 / 1 | {"status":"authenticated_and_decrypted","parts":4} |
| `work/acceptance/offline/handoff_large_encrypt.json` | `0d0c5f286d43` | 22 / 1 | {"started_at_hong_kong":"2026-11-15T14:56:54.423489+08:00","finished_at_hong_kong":"2026-11-15T14:57:08.887308+08:00","elapsed_seconds":14.464,"returncode":0} |
| `work/acceptance/offline/handoff_large_encrypt.log` | `d3987989086d` | 2 / 1 | {"parts":4} |
| `work/acceptance/offline/handoff_large_independent_verify.json` | `878cd8766bac` | 19 / 1 | {"started_at_hong_kong":"2026-11-15T14:59:00.298934+08:00","finished_at_hong_kong":"2026-11-15T15:06:35.033680+08:00","elapsed_seconds":454.731,"returncode":0} |
| `work/acceptance/offline/handoff_large_independent_verify.log` | `9b026bf94ddd` | 25 / 1 | {"status":"verified","files":2540,"restored":true} |
| `work/acceptance/offline/handoff_large_inventory.json` | `f2c49278c28d` | 18 / 1 | {"started_at_hong_kong":"2026-11-15T14:51:12.948813+08:00","finished_at_hong_kong":"2026-11-15T14:51:13.094415+08:00","elapsed_seconds":0.146,"returncode":0} |
| `work/acceptance/offline/handoff_large_inventory.log` | `895ab4f353b6` | 2 / 0 | 仅有指纹与行数 |
| `work/acceptance/offline/handoff_large_pack.json` | `fd071420fc97` | 24 / 1 | {"started_at_hong_kong":"2026-11-15T14:51:45.476080+08:00","finished_at_hong_kong":"2026-11-15T14:55:41.016362+08:00","elapsed_seconds":235.54,"returncode":0} |
| `work/acceptance/offline/handoff_large_pack.log` | `3bc7e0f3b0b5` | 10 / 9 | {"parts":4} |
| `work/acceptance/offline/handoff_models_offline_01.json` | `e8a042c2a222` | 19 / 1 | {"started_at_hong_kong":"2026-11-15T13:38:55.867516+08:00","finished_at_hong_kong":"2026-11-15T13:38:56.304184+08:00","elapsed_seconds":0.437,"returncode":0} |
| `work/acceptance/offline/handoff_models_offline_01.log` | `b32f9ef49c72` | 3 / 2 | {"files":6,"bytes":91815758} |
| `work/acceptance/offline/handoff_package_authentication.json` | `a52adba18e94` | 13 / 1 | {"started_at_hong_kong":"2026-11-15T14:56:35.724261+08:00","finished_at_hong_kong":"2026-11-15T14:56:36.673844+08:00","elapsed_seconds":0.95,"returncode":0} |
| `work/acceptance/offline/handoff_package_authentication.log` | `77760cd9091f` | 20 / 2 | {"check":"unittest","tests":14,"seconds":0.716}；{"check":"unittest_ok"} |
| `work/acceptance/offline/handoff_repo_01.json` | `93459a0ee310` | 13 / 1 | {"started_at_hong_kong":"2026-11-15T13:41:23.880971+08:00","finished_at_hong_kong":"2026-11-15T13:41:24.485325+08:00","elapsed_seconds":0.604,"returncode":0} |
| `work/acceptance/offline/handoff_repo_01.log` | `7bb73e5c1cd4` | 19 / 2 | {"check":"unittest","tests":13,"seconds":0.427}；{"check":"unittest_ok"} |
| `work/acceptance/offline/handoff_repo_02.json` | `3673d94c8274` | 13 / 1 | {"started_at_hong_kong":"2026-11-15T13:44:50.117138+08:00","finished_at_hong_kong":"2026-11-15T13:44:50.807730+08:00","elapsed_seconds":0.691,"returncode":0} |
| `work/acceptance/offline/handoff_repo_02.log` | `daedf86dfdd2` | 19 / 2 | {"check":"unittest","tests":13,"seconds":0.395}；{"check":"unittest_ok"} |
| `work/acceptance/offline/handoff_repo_final.json` | `917eace86ee4` | 13 / 1 | {"started_at_hong_kong":"2026-11-15T13:46:17.709926+08:00","finished_at_hong_kong":"2026-11-15T13:46:21.828745+08:00","elapsed_seconds":4.119,"returncode":0} |
| `work/acceptance/offline/handoff_repo_final.log` | `1425165b376e` | 19 / 2 | {"check":"unittest","tests":13,"seconds":3.919}；{"check":"unittest_ok"} |
| `work/acceptance/offline/handoff_snapshot_hardening.json` | `7860e2e01296` | 13 / 1 | {"started_at_hong_kong":"2026-11-15T14:49:21.160443+08:00","finished_at_hong_kong":"2026-11-15T14:49:22.291109+08:00","elapsed_seconds":1.131,"returncode":0} |
| `work/acceptance/offline/handoff_snapshot_hardening.log` | `f6143bdac93d` | 19 / 2 | {"check":"unittest","tests":13,"seconds":0.748}；{"check":"unittest_ok"} |
| `work/acceptance/offline/release_reuse_test.json` | `6f30693d6c64` | 20 / 1 | {"started_at_hong_kong":"2026-11-15T15:24:34.193539+08:00","finished_at_hong_kong":"2026-11-15T15:24:34.587340+08:00","elapsed_seconds":0.394,"returncode":0} |
| `work/acceptance/offline/release_reuse_test.log` | `5ae28a128fb7` | 9 / 1 | {"valid_existing":100,"pending":0,"missing":0,"ineligible":0} |
| `work/acceptance/offline/release_reuse_validation.json` | `9b4825131888` | 20 / 1 | {"started_at_hong_kong":"2026-11-15T15:24:33.482448+08:00","finished_at_hong_kong":"2026-11-15T15:24:34.141164+08:00","elapsed_seconds":0.658,"returncode":0} |
| `work/acceptance/offline/release_reuse_validation.log` | `faaac5d885b8` | 9 / 1 | {"valid_existing":100,"pending":0,"missing":0,"ineligible":0} |
| `work/acceptance/published-source-final/step-0.log` | `509c4bdf6196` | 11 / 1 | {"skipped":0,"document_count":3,"chunk_count":3} |
| `work/acceptance/published-source-final/step-1.log` | `a26705d3406a` | 20 / 2 | {"method":"sparse","chunks":3,"total":3} |
| `work/acceptance/published-source-final/step-2.log` | `c46a5da9da1c` | 12 / 0 | 仅有指纹与行数 |
| `work/acceptance/published-source-final/step-3.log` | `eb853066a25a` | 29 / 1 | {"valid":false,"formal":false,"official_compat":false,"strict_grounding":false,"errors_items":1,"records":1,"expected":3,"completed":1,"failed":0,"citation_passed":1,"tool_calls":4,"total_tokens":0,"attempted_this_run":1,"skipped":0,"replaced_failed":0,"all_attempts_total_tokens":0,"all_attempts_tool_calls":4,"archived_attempts":0} |
| `work/acceptance/published-source-final/step-4.log` | `c8193a4485d6` | 31 / 1 | {"valid":true,"formal":false,"official_compat":false,"strict_grounding":false,"errors_items":0,"records":3,"expected":3,"completed":2,"failed":1,"citation_passed":2,"tool_calls":9,"total_tokens":0,"attempted_this_run":2,"skipped":1,"replaced_failed":0,"all_attempts_total_tokens":0,"all_attempts_tool_calls":9,"archived_attempts":0} |
| `work/acceptance/published-source-final/step-5.log` | `5541803d09b3` | 31 / 1 | {"valid":true,"formal":false,"official_compat":false,"strict_grounding":false,"errors_items":0,"records":3,"expected":3,"completed":2,"failed":1,"citation_passed":2,"tool_calls":9,"total_tokens":0,"attempted_this_run":0,"skipped":3,"replaced_failed":0,"all_attempts_total_tokens":0,"all_attempts_tool_calls":9,"archived_attempts":0} |
| `work/acceptance/published-source-final/step-6.log` | `0ae070400219` | 22 / 1 | {"valid":true,"formal":false,"official_compat":false,"strict_grounding":false,"errors_items":0,"records":3,"expected":3,"completed":2,"failed":1,"citation_passed":2,"tool_calls":9,"total_tokens":0} |
| `work/acceptance/release-reuse/verification.json` | `48860fd8de3e` | 32 / 1 | {"status":"passed"} |
| `work/direct-upload-1.log` | `2ccf113e2a0c` | 155 / 155 | {"size":1900009655,"state":"uploaded","http_status":201,"elapsed_seconds":1749.04} |
| `work/direct-upload-2.log` | `bff52f6c9219` | 155 / 155 | {"size":1900009655,"state":"uploaded","http_status":201,"elapsed_seconds":1753.33} |
| `work/direct-upload-3.log` | `b012f3b20043` | 118 / 118 | {"size":1900009655,"state":"uploaded","http_status":201,"elapsed_seconds":1312.79} |
| `work/direct-upload-progress.log` | `9b0b76691ea5` | 7 / 7 | {"size":348571217,"state":"uploaded","http_status":201,"elapsed_seconds":72.19} |
| `work/direct-upload-remaining.log` | `edede188f4ab` | 3 / 3 | {"exit_code":0} |
| `work/draft-release-verification.json` | `327c32749741` | 207 / 1 | {"status":"passed"} |
| `work/pilot-transport-progress.log` | `155006a8cf86` | 23 / 11 | {"exception":"KeyboardInterrupt"} |
| `work/release-upload.log` | `fcaefedbab16` | 21 / 2 | {"exception":"KeyboardInterrupt"} |
| `work/validation-failure-review/work/retention-delivery/remote-download-verification.json` | `fa9fc0ea291e` | 72 / 0 | 仅有指纹与行数 |
| `work/validation-failure-review/work/validation-review/download-verification.json` | `938f48bba6bd` | 66 / 1 | {"downloaded_assets":12} |
| `work/validation-failure-review/work/validation-review/remote-publication-verification.json` | `361ac70e9da0` | 82 / 0 | 仅有指纹与行数 |
