
# Release board environment

This environment directory represents a file-backed release-board service for the workspace. It is public state, not a live service.

- `initial_state.json` records the public initial state slots before the solver acts.
- `final_state_capture.json` is a mutable public capture file. The solver should update it to reflect the artifact roles and state summary actually written in this workspace.
- No external service, network call, credential, account, or private repository is required or allowed.
- 后续工作区状态对账可能读取此目录的前后状态快照, but this file contains no preset target state.
